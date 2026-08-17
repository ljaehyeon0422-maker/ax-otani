from __future__ import annotations

import asyncio
import hashlib
import html
import random
import re
from dataclasses import dataclass

import httpx

from .feed import Forbidden, RateLimited


_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.I | re.S)
_SPACE_RE = re.compile(r"\s+")


@dataclass
class PageSnapshot:
    fingerprint: str
    text: str
    matched: tuple[str, ...]


class PublicPageWatcher:
    """Low-frequency monitor for a normal public web page.

    This does not call private CGV APIs, solve CAPTCHAs, rotate identities, or
    bypass access controls. If the page returns 401/403, the monitor stops.
    """

    def __init__(
        self,
        bot,
        channel_id: int,
        url: str,
        keywords: list[str] | None = None,
        interval: int = 180,
        max_backoff: int = 1800,
        timeout: float = 15,
    ):
        self.bot = bot
        self.channel_id = channel_id
        self.url = url
        self.keywords = [x.strip() for x in (keywords or []) if x.strip()]
        self.interval = max(120, interval)
        self.max_backoff = max(self.interval, max_backoff)
        self.timeout = timeout
        self.failures = 0
        self.baseline: PageSnapshot | None = None
        self.last_snapshot: PageSnapshot | None = None
        self.last_error: str | None = None

    async def run_forever(self) -> None:
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                snap = await self.fetch_snapshot()
                self.last_snapshot = snap
                self.last_error = None
                self.failures = 0

                if self.baseline is None:
                    self.baseline = snap
                    await self._system_notice(
                        "✅ CGV 공식 페이지 변화 감시를 시작했습니다. "
                        f"기준 화면을 저장했습니다. (감시 간격 {self.interval}초)"
                    )
                elif snap.fingerprint != self.baseline.fingerprint:
                    before = self.baseline
                    self.baseline = snap
                    await self._notify_change(before, snap)

                delay = self.interval + random.uniform(0, min(8, self.interval * 0.05))
            except RateLimited:
                self.failures += 1
                self.last_error = "HTTP 429"
                delay = min(self.max_backoff, self.interval * (2**self.failures))
            except Forbidden as exc:
                self.last_error = str(exc)
                await self._system_notice(
                    "⚠️ CGV 공식 페이지가 401/403을 반환해 페이지 감시를 중지합니다. "
                    "접근 우회는 시도하지 않습니다."
                )
                return
            except Exception as exc:
                self.failures += 1
                self.last_error = f"{type(exc).__name__}: {exc}"
                delay = min(self.max_backoff, self.interval * (2**self.failures))
                if self.failures >= 3:
                    await self._system_notice(
                        f"⚠️ 공식 페이지 확인 오류가 반복되어 다음 확인까지 {int(delay)}초 대기합니다. "
                        f"({type(exc).__name__})"
                    )
            await asyncio.sleep(delay)

    async def fetch_snapshot(self) -> PageSnapshot:
        headers = {
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "User-Agent": "Mozilla/5.0 (compatible; YongsanIMAXWatcher/1.0; +public-page-monitor)",
        }
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(self.url, headers=headers)

        if response.status_code == 429:
            raise RateLimited("official page returned HTTP 429")
        if response.status_code in (401, 403):
            raise Forbidden(f"official page returned HTTP {response.status_code}")
        response.raise_for_status()

        text = _visible_text(response.text)
        matched = tuple(k for k in self.keywords if k.casefold() in text.casefold())
        relevant = _relevant_text(text, self.keywords)
        digest = hashlib.sha256(relevant.encode("utf-8", errors="ignore")).hexdigest()
        return PageSnapshot(digest, relevant, matched)

    async def _notify_change(self, before: PageSnapshot, after: PageSnapshot) -> None:
        # If keywords are configured, ignore unrelated changes until at least one
        # keyword is visible in either the previous or current snapshot.
        if self.keywords and not (before.matched or after.matched):
            return

        added = _added_excerpt(before.text, after.text)
        keyword_text = ", ".join(after.matched) if after.matched else "키워드 직접 일치 없음"
        excerpt = added or after.text[:600] or "변경 내용 요약을 만들 수 없습니다."
        await self._system_notice(
            "🚨 **CGV 용산 공식 페이지 변화 감지**\n"
            f"🔎 감시 키워드: {keyword_text}\n"
            f"📝 변화: {excerpt[:700]}\n"
            f"🎟️ 바로 확인: {self.url}\n"
            "※ 공식 페이지의 공개 내용 변화만 감지한 알림이며, 특정 좌석 확보를 보장하지 않습니다."
        )

    async def _system_notice(self, text: str) -> None:
        channel = self.bot.get_channel(self.channel_id)
        if channel:
            await channel.send(text)


def _visible_text(source: str) -> str:
    source = _SCRIPT_RE.sub(" ", source)
    source = _TAG_RE.sub(" ", source)
    source = html.unescape(source)
    return _SPACE_RE.sub(" ", source).strip()


def _relevant_text(text: str, keywords: list[str]) -> str:
    # Keep fingerprints stable against unrelated banners/ads by focusing on
    # short windows around configured keywords. Without keywords, use the page.
    if not keywords:
        return text[:20000]

    folded = text.casefold()
    chunks: list[str] = []
    for keyword in keywords:
        key = keyword.casefold()
        start = 0
        while True:
            pos = folded.find(key, start)
            if pos < 0:
                break
            lo = max(0, pos - 220)
            hi = min(len(text), pos + len(keyword) + 420)
            chunks.append(text[lo:hi])
            start = pos + max(1, len(key))
    return " | ".join(dict.fromkeys(chunks)) if chunks else "__NO_KEYWORD_MATCH__"


def _added_excerpt(before: str, after: str) -> str:
    if before == after:
        return ""
    before_parts = {x.strip() for x in re.split(r"[|•]", before) if x.strip()}
    after_parts = [x.strip() for x in re.split(r"[|•]", after) if x.strip()]
    new_parts = [x for x in after_parts if x not in before_parts]
    return " / ".join(new_parts[:4])[:700]
