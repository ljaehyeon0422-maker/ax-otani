from __future__ import annotations
import os, asyncio
from dotenv import load_dotenv
import discord
from discord import app_commands
from discord.ext import commands
from .models import Preferences
from .store import Store
from .feed import JsonFeed
from .watcher import Watcher
from .page_watcher import PublicPageWatcher

load_dotenv()
TOKEN=os.getenv("DISCORD_BOT_TOKEN","")
GUILD_ID=int(os.getenv("DISCORD_GUILD_ID","0") or 0)
CHANNEL_ID=int(os.getenv("DISCORD_ALERT_CHANNEL_ID","0") or 0)
POLL=int(os.getenv("POLL_SECONDS","60")); MAX_BACKOFF=int(os.getenv("MAX_BACKOFF_SECONDS","900"))
FEED=JsonFeed(os.getenv("CGV_FEED_URL"))
PUBLIC_PAGE_URL=os.getenv("CGV_PUBLIC_PAGE_URL","").strip()
PUBLIC_PAGE_KEYWORDS=[x.strip() for x in os.getenv("CGV_PUBLIC_PAGE_KEYWORDS","IMAX,아이맥스").split(",") if x.strip()]
PUBLIC_PAGE_POLL=int(os.getenv("CGV_PUBLIC_PAGE_POLL_SECONDS","180"))
PUBLIC_PAGE_MAX_BACKOFF=int(os.getenv("CGV_PUBLIC_PAGE_MAX_BACKOFF_SECONDS","1800"))
PAGE_WATCHER=None

intents=discord.Intents.default()
bot=commands.Bot(command_prefix="!", intents=intents)
store=Store()

SCOPE_LABEL={"prime":"명당만","good":"좋은 자리","okay":"웬만하면 OK","wide":"최대한 넓게"}
ADJ_LABEL={"all_together":"전원 연석","min_two":"최소 2연석","prefer_together":"연석 우선","any":"상관없음"}
SCOPE_CHOICES=[app_commands.Choice(name=v,value=k) for k,v in SCOPE_LABEL.items()]
ADJ_CHOICES=[app_commands.Choice(name=v,value=k) for k,v in ADJ_LABEL.items()]

class SetupView(discord.ui.View):
    def __init__(self,user_id:int):
        super().__init__(timeout=180); self.user_id=user_id; self.party_size=2; self.scope="okay"; self.adj="prefer_together"
        self.add_item(PartySelect(self)); self.add_item(ScopeSelect(self)); self.add_item(AdjSelect(self))

    @discord.ui.button(label="기본 설정 저장",style=discord.ButtonStyle.success,row=3)
    async def save(self,interaction:discord.Interaction,button:discord.ui.Button):
        if interaction.user.id!=self.user_id: return await interaction.response.send_message("본인의 설정만 변경할 수 있습니다.",ephemeral=True)
        p=Preferences(self.party_size,self.adj,self.scope); store.save_profile(self.user_id,p)
        await interaction.response.edit_message(content=f"✅ 기본 설정 저장\n👥 {p.party_size}명 · {ADJ_LABEL[p.adjacency_mode]} · {SCOPE_LABEL[p.seat_scope]}",view=None)

class PartySelect(discord.ui.Select):
    def __init__(self,parent):
        self.parent_view=parent
        super().__init__(placeholder="기본 관람 인원",options=[discord.SelectOption(label=f"{n}명",value=str(n),default=n==2) for n in range(1,9)],row=0)
    async def callback(self,interaction):
        self.parent_view.party_size=int(self.values[0]); await interaction.response.defer()

class ScopeSelect(discord.ui.Select):
    def __init__(self,parent):
        self.parent_view=parent
        super().__init__(placeholder="좌석 허용 범위",options=[discord.SelectOption(label=v,value=k,default=k=="okay") for k,v in SCOPE_LABEL.items()],row=1)
    async def callback(self,interaction):
        self.parent_view.scope=self.values[0]; await interaction.response.defer()

class AdjSelect(discord.ui.Select):
    def __init__(self,parent):
        self.parent_view=parent
        super().__init__(placeholder="연석 조건",options=[discord.SelectOption(label=v,value=k,default=k=="prefer_together") for k,v in ADJ_LABEL.items()],row=2)
    async def callback(self,interaction):
        self.parent_view.adj=self.values[0]; await interaction.response.defer()

class MovieView(discord.ui.View):
    def __init__(self,user_id:int,showings):
        super().__init__(timeout=180); self.user_id=user_id; self.showings=showings
        unique={s.movie_id:s.movie_name for s in showings}
        opts=[discord.SelectOption(label=name[:100],value=mid) for mid,name in list(unique.items())[:25]]
        select=discord.ui.Select(placeholder="용산 IMAX 영화 선택",options=opts)
        select.callback=self.movie_selected; self.add_item(select)
    async def movie_selected(self,interaction):
        if interaction.user.id!=self.user_id: return await interaction.response.send_message("본인의 메뉴만 사용할 수 있습니다.",ephemeral=True)
        mid=interaction.data["values"][0]; movie_name=next(s.movie_name for s in self.showings if s.movie_id==mid)
        dates=sorted({s.date for s in self.showings if s.movie_id==mid})
        await interaction.response.edit_message(content=f"🎬 **{movie_name}**\n감시할 날짜를 선택하세요.",view=DateView(self.user_id,self.showings,mid,movie_name,dates))

class DateView(discord.ui.View):
    def __init__(self,user_id,showings,movie_id,movie_name,dates):
        super().__init__(timeout=180); self.user_id=user_id; self.showings=showings; self.movie_id=movie_id; self.movie_name=movie_name
        opts=[discord.SelectOption(label=d,value=d) for d in dates[:25]]
        select=discord.ui.Select(placeholder="날짜 선택",options=opts); select.callback=self.date_selected; self.add_item(select)
    async def date_selected(self,interaction):
        if interaction.user.id!=self.user_id: return await interaction.response.send_message("본인의 메뉴만 사용할 수 있습니다.",ephemeral=True)
        date=interaction.data["values"][0]; wid=store.add_watch(self.user_id,self.movie_id,self.movie_name,date,{})
        p=store.resolved_preferences(store.conn.execute("SELECT * FROM watches WHERE id=?",(wid,)).fetchone())
        await interaction.response.edit_message(content=f"✅ 감시 #{wid} 시작\n🎬 {self.movie_name}\n📅 {date}\n👥 {p.party_size}명 · {ADJ_LABEL[p.adjacency_mode]} · {SCOPE_LABEL[p.seat_scope]}\n\n이 영화/날짜만 다르게 보려면 `/watch`로 같은 영화·날짜에 세부 조건을 지정하세요.",view=None)

@bot.tree.command(name="setup",description="기본 관람 인원·좌석 범위·연석 조건을 설정합니다")
async def setup(interaction:discord.Interaction):
    await interaction.response.send_message("⚙️ **용산 IMAX 기본 설정**\n세 항목을 고르고 저장하세요. 기본값은 2명 / 연석 우선 / 웬만하면 OK 입니다.",view=SetupView(interaction.user.id),ephemeral=True)

@bot.tree.command(name="watch_menu",description="현재 피드의 영화와 날짜를 골라 감시를 시작합니다")
async def watch_menu(interaction:discord.Interaction):
    await interaction.response.defer(ephemeral=True,thinking=True)
    try: showings=await FEED.fetch()
    except Exception as e: return await interaction.followup.send(f"현재 영화 목록을 불러오지 못했습니다: {type(e).__name__}",ephemeral=True)
    if not showings: return await interaction.followup.send("현재 연결된 좌석 피드에 상영정보가 없습니다. 실제 개별좌석 데이터 소스는 아직 연결하지 않았습니다.",ephemeral=True)
    await interaction.followup.send("🎬 감시할 용산 IMAX 영화를 선택하세요.",view=MovieView(interaction.user.id,showings),ephemeral=True)

@bot.tree.command(name="official_watch_status",description="CGV 공식 페이지 변화 감시 상태를 확인합니다")
async def official_watch_status(interaction:discord.Interaction):
    if not PUBLIC_PAGE_URL:
        return await interaction.response.send_message("⛔ 공식 페이지 감시 URL이 설정되지 않았습니다.",ephemeral=True)
    watcher=PAGE_WATCHER
    if watcher is None:
        return await interaction.response.send_message("⏳ 공식 페이지 감시가 아직 시작되지 않았습니다.",ephemeral=True)
    matched=", ".join(watcher.last_snapshot.matched) if watcher.last_snapshot and watcher.last_snapshot.matched else "없음"
    error=watcher.last_error or "없음"
    await interaction.response.send_message(
        f"✅ **CGV 공식 페이지 감시 상태**\n"
        f"🔗 {PUBLIC_PAGE_URL}\n"
        f"⏱️ {watcher.interval}초 간격\n"
        f"🔎 키워드: {', '.join(PUBLIC_PAGE_KEYWORDS) or '없음'}\n"
        f"🎯 현재 일치: {matched}\n"
        f"⚠️ 최근 오류: {error}",
        ephemeral=True,
    )

@bot.tree.command(name="official_watch_test",description="CGV 공식 페이지를 지금 한 번 확인합니다")
async def official_watch_test(interaction:discord.Interaction):
    if PAGE_WATCHER is None:
        return await interaction.response.send_message("⛔ 공식 페이지 감시가 활성화되어 있지 않습니다.",ephemeral=True)
    await interaction.response.defer(ephemeral=True,thinking=True)
    try:
        snap=await PAGE_WATCHER.fetch_snapshot()
        PAGE_WATCHER.last_snapshot=snap
        matched=", ".join(snap.matched) if snap.matched else "없음"
        await interaction.followup.send(f"✅ 공식 페이지 응답 정상\n🔎 현재 키워드 일치: {matched}",ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ 공식 페이지 확인 실패: {type(e).__name__}: {e}",ephemeral=True)

@bot.tree.command(name="watch",description="영화/날짜별 조건을 직접 지정해 감시를 추가합니다")
@app_commands.choices(seat_scope=SCOPE_CHOICES, adjacency=ADJ_CHOICES)
async def watch(interaction:discord.Interaction,movie_id:str,movie_name:str,date:str,party_size:app_commands.Range[int,1,8]=2,seat_scope:app_commands.Choice[str]|None=None,adjacency:app_commands.Choice[str]|None=None):
    override={"party_size":party_size,"seat_scope":seat_scope.value if seat_scope else None,"adjacency_mode":adjacency.value if adjacency else None}
    wid=store.add_watch(interaction.user.id,movie_id,movie_name,date,override)
    p=store.resolved_preferences(store.conn.execute("SELECT * FROM watches WHERE id=?",(wid,)).fetchone())
    await interaction.response.send_message(f"✅ 감시 #{wid} 추가\n🎬 {movie_name}\n📅 {date}\n👥 {p.party_size}명 · {ADJ_LABEL[p.adjacency_mode]} · {SCOPE_LABEL[p.seat_scope]}",ephemeral=True)

@bot.tree.command(name="movie_override",description="특정 영화의 기본 조건을 덮어씁니다")
@app_commands.choices(seat_scope=SCOPE_CHOICES, adjacency=ADJ_CHOICES)
async def movie_override(interaction:discord.Interaction,movie_id:str,party_size:app_commands.Range[int,1,8]=2,seat_scope:app_commands.Choice[str]|None=None,adjacency:app_commands.Choice[str]|None=None):
    store.save_movie_override(interaction.user.id,movie_id,{"party_size":party_size,"seat_scope":seat_scope.value if seat_scope else None,"adjacency_mode":adjacency.value if adjacency else None})
    await interaction.response.send_message("✅ 영화별 기본 설정을 저장했습니다.",ephemeral=True)

@bot.tree.command(name="watches",description="내 감시 목록을 봅니다")
async def watches(interaction:discord.Interaction):
    rows=store.list_watches(interaction.user.id)
    if not rows: return await interaction.response.send_message("감시 중인 항목이 없습니다.",ephemeral=True)
    lines=[]
    for w in rows:
        p=store.resolved_preferences(w)
        lines.append(f"#{w['id']} {'🟢' if w['enabled'] else '⏸️'} {w['movie_name']} / {w['watch_date']} / {p.party_size}명 / {ADJ_LABEL[p.adjacency_mode]} / {SCOPE_LABEL[p.seat_scope]}")
    await interaction.response.send_message("\n".join(lines),ephemeral=True)

@bot.tree.command(name="pause",description="감시를 일시정지합니다")
async def pause(interaction:discord.Interaction,watch_id:int):
    store.set_enabled(watch_id,False); await interaction.response.send_message(f"⏸️ #{watch_id} 중지",ephemeral=True)

@bot.tree.command(name="resume",description="감시를 재개합니다")
async def resume(interaction:discord.Interaction,watch_id:int):
    store.set_enabled(watch_id,True); await interaction.response.send_message(f"▶️ #{watch_id} 재개",ephemeral=True)

@bot.event
async def on_ready():
    global PAGE_WATCHER
    if not getattr(bot,"_synced",False):
        if GUILD_ID:
            guild=discord.Object(id=GUILD_ID); bot.tree.copy_global_to(guild=guild); await bot.tree.sync(guild=guild)
        else: await bot.tree.sync()
        bot._synced=True
    if CHANNEL_ID and FEED.url and not getattr(bot,"_watcher_started",False):
        bot._watcher_started=True
        asyncio.create_task(Watcher(bot,store,FEED,CHANNEL_ID,POLL,MAX_BACKOFF).run_forever())
    if CHANNEL_ID and PUBLIC_PAGE_URL and not getattr(bot,"_page_watcher_started",False):
        bot._page_watcher_started=True
        PAGE_WATCHER=PublicPageWatcher(
            bot,
            CHANNEL_ID,
            PUBLIC_PAGE_URL,
            PUBLIC_PAGE_KEYWORDS,
            PUBLIC_PAGE_POLL,
            PUBLIC_PAGE_MAX_BACKOFF,
        )
        asyncio.create_task(PAGE_WATCHER.run_forever())
    print(f"Logged in as {bot.user}")

def main():
    if not TOKEN: raise SystemExit("DISCORD_BOT_TOKEN is required")
    if not CHANNEL_ID: raise SystemExit("DISCORD_ALERT_CHANNEL_ID is required")
    bot.run(TOKEN)

if __name__ == "__main__": main()
