from __future__ import annotations
import asyncio, random
from .feed import JsonFeed, RateLimited, Forbidden
from .seat_policy import qualifying_sets, signature

class Watcher:
    def __init__(self, bot, store, feed:JsonFeed, channel_id:int, base_interval:int=60, max_backoff:int=900):
        self.bot=bot; self.store=store; self.feed=feed; self.channel_id=channel_id
        self.base=max(30,base_interval); self.max_backoff=max(self.base,max_backoff); self.failures=0

    async def run_forever(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                showings=await self.feed.fetch(); self.failures=0
                await self.evaluate(showings)
                delay=self.base + random.uniform(0,min(5,self.base*.1))
            except RateLimited:
                self.failures+=1; delay=min(self.max_backoff,self.base*(2**self.failures))
            except Forbidden:
                await self._system_notice("⚠️ 데이터 소스가 401/403을 반환해 모니터링을 중지합니다. 접근 우회는 시도하지 않습니다.")
                return
            except Exception as e:
                self.failures+=1; delay=min(self.max_backoff,self.base*(2**self.failures))
                if self.failures>=4:
                    await self._system_notice(f"⚠️ 모니터링 오류가 반복되어 호출 간격을 {int(delay)}초로 늘렸습니다: {type(e).__name__}")
            await asyncio.sleep(delay)

    async def evaluate(self, showings):
        by_key={}
        for s in showings: by_key.setdefault((s.movie_id,s.date),[]).append(s)
        channel=self.bot.get_channel(self.channel_id)
        if channel is None: return
        for w in self.store.list_watches():
            for s in by_key.get((w["movie_id"],w["watch_date"]),[]):
                if not s.seats: continue
                prefs=self.store.resolved_preferences(w)
                groups=qualifying_sets(s.seats,prefs); now=signature(groups)
                before=self.store.get_seen(w["id"],s.key)
                newly=now-before
                if newly:
                    names=", ".join(sorted(newly)[:12])
                    await channel.send(f"🚨 **용산 IMAX 좌석 알림**\n🎬 {s.movie_name}\n📅 {s.date}  ⏰ {s.start_time}\n💺 {names}\n👥 {prefs.party_size}명 · {prefs.adjacency_mode} · {prefs.seat_scope}")
                self.store.set_seen(w["id"],s.key,now)

    async def _system_notice(self,text):
        ch=self.bot.get_channel(self.channel_id)
        if ch: await ch.send(text)
