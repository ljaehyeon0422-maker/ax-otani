from __future__ import annotations

import asyncio
import os

import discord

from . import bot as base
from .browser_bridge import BrowserSeatBridge

BRIDGE_HOST=os.getenv("BROWSER_BRIDGE_HOST","127.0.0.1")
BRIDGE_PORT=int(os.getenv("BROWSER_BRIDGE_PORT","8765"))
BRIDGE_KEYWORDS=[x.strip() for x in os.getenv("BROWSER_REQUIRED_KEYWORDS","오디세이,IMAX").split(",") if x.strip()]
BRIDGE=None


async def _bridge_ready():
    global BRIDGE
    if getattr(base.bot,"_browser_bridge_started",False):
        return
    base.bot._browser_bridge_started=True
    BRIDGE=BrowserSeatBridge(
        base.bot,
        base.store,
        base.CHANNEL_ID,
        host=BRIDGE_HOST,
        port=BRIDGE_PORT,
        required_keywords=BRIDGE_KEYWORDS,
    )
    try:
        await BRIDGE.start()
    except OSError as exc:
        print(f"Browser bridge failed to start: {exc}")


base.bot.add_listener(_bridge_ready,"on_ready")


@base.bot.tree.command(name="browser_bridge_status",description="Chrome 취소표 감지 연결 상태를 확인합니다")
async def browser_bridge_status(interaction:discord.Interaction):
    if BRIDGE is None:
        return await interaction.response.send_message("⏳ Chrome 브리지 서버가 아직 시작되지 않았습니다.",ephemeral=True)
    last=BRIDGE.last_received
    if last:
        detail=f"최근 수신: {last.get('accepted',0)}개 회차 / 알림 {last.get('alerts',0)}건\n최근 페이지: {last.get('title','')}"
    else:
        detail="아직 Chrome 확장프로그램에서 받은 데이터가 없습니다."
    await interaction.response.send_message(
        f"✅ **Chrome 취소표 브리지**\n"
        f"🖥️ http://{BRIDGE_HOST}:{BRIDGE_PORT}\n"
        f"🔎 필수 키워드: {', '.join(BRIDGE_KEYWORDS) or '없음'}\n"
        f"{detail}",
        ephemeral=True,
    )


def main():
    base.main()
