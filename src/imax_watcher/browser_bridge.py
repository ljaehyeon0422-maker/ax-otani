from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from aiohttp import web


@dataclass
class BrowserObservation:
    showing_key: str
    movie_name: str
    watch_date: str
    start_time: str
    remaining: int
    context: str
    page_url: str


class BrowserSeatBridge:
    """Receives visible seat-count observations from a local Chrome extension.

    The extension reads only what is rendered in the user's normal browser page.
    This bridge does not call CGV APIs and does not handle cookies, auth headers,
    CAPTCHAs, or other access-control material.
    """

    def __init__(
        self,
        bot,
        store,
        channel_id: int,
        host: str = "127.0.0.1",
        port: int = 8765,
        required_keywords: list[str] | None = None,
    ):
        self.bot = bot
        self.store = store
        self.channel_id = channel_id
        self.host = host
        self.port = port
        self.required_keywords = [x.casefold() for x in (required_keywords or []) if x.strip()]
        self.runner: web.AppRunner | None = None
        self.last_received: dict[str, Any] | None = None

    async def start(self) -> None:
        app = web.Application(client_max_size=128 * 1024)
        app.router.add_get("/health", self.health)
        app.router.add_post("/observe", self.observe)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        print(f"Browser seat bridge listening on http://{self.host}:{self.port}")

    async def health(self, request: web.Request) -> web.Response:
        return web.json_response({"ok": True, "service": "yongsan-imax-browser-bridge"})

    async def observe(self, request: web.Request) -> web.Response:
        if request.remote not in ("127.0.0.1", "::1", None):
            raise web.HTTPForbidden(text="localhost only")

        payload = await request.json()
        page_text = str(payload.get("page_text", ""))[:12000]
        title = str(payload.get("title", ""))[:300]
        page_url = str(payload.get("url", ""))[:1000]
        haystack = f"{title}\n{page_text}".casefold()

        if self.required_keywords and not all(k in haystack for k in self.required_keywords):
            return web.json_response({"ok": True, "accepted": 0, "reason": "required keywords not present"})

        accepted = 0
        alerts = 0
        for item in payload.get("observations", [])[:50]:
            try:
                obs = BrowserObservation(
                    showing_key=str(item.get("showing_key") or "").strip(),
                    movie_name=str(item.get("movie_name") or "").strip(),
                    watch_date=str(item.get("watch_date") or "").strip(),
                    start_time=str(item.get("start_time") or "").strip(),
                    remaining=int(item["remaining"]),
                    context=str(item.get("context") or "")[:1500],
                    page_url=page_url,
                )
            except (KeyError, TypeError, ValueError):
                continue
            if not obs.showing_key or obs.remaining < 0:
                continue

            before = self.store.get_browser_remaining(obs.showing_key)
            self.store.set_browser_remaining(
                obs.showing_key,
                obs.movie_name,
                obs.watch_date,
                obs.start_time,
                obs.remaining,
                obs.context,
            )
            accepted += 1
            if before is not None and obs.remaining > before:
                alerts += 1
                await self._send_alert(before, obs)

        self.last_received = {
            "accepted": accepted,
            "alerts": alerts,
            "title": title,
            "url": page_url,
        }
        return web.json_response({"ok": True, "accepted": accepted, "alerts": alerts})

    async def _send_alert(self, before: int, obs: BrowserObservation) -> None:
        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            return
        movie = obs.movie_name or "감시 영화"
        date = obs.watch_date or "날짜 확인 필요"
        time = obs.start_time or "시간 확인 필요"
        await channel.send(
            "🚨 **용산 IMAX 취소표 가능성 감지**\n"
            f"🎬 {movie}\n"
            f"📅 {date}  ⏰ {time}\n"
            f"💺 잔여좌석 {before} → **{obs.remaining}석**\n"
            f"🎟️ 바로 확인: {obs.page_url}\n"
            "※ Chrome에 정상 표시된 공개 화면의 잔여좌석 숫자 증가를 감지한 알림입니다."
        )

    async def stop(self) -> None:
        if self.runner:
            await self.runner.cleanup()
            self.runner = None
