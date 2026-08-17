from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

import httpx

from .models import Showing, Seat


class FeedError(RuntimeError):
    pass


class RateLimited(FeedError):
    pass


class Forbidden(FeedError):
    pass


class JsonFeed:
    """Consumes a permitted JSON seat feed; never bypasses access controls."""

    def __init__(self, url: str | None, timeout: float = 10):
        self.url = url
        self.timeout = timeout

    async def fetch(self, dates: Iterable[str] | None = None) -> list[Showing]:
        if not self.url:
            return []
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            r = await client.get(self.url, headers={"Accept": "application/json"})
        _raise_for_status(r)
        raw = r.json()
        items = raw.get("showings", raw if isinstance(raw, list) else [])
        out = []
        wanted = {normalize_date(d) for d in dates} if dates else None
        for x in items:
            item_date = normalize_date(str(x["date"]))
            if wanted and item_date not in wanted:
                continue
            seats = [
                Seat(str(s["row"]).upper(), int(s["number"]), bool(s.get("available", True)))
                for s in x.get("seats", [])
            ]
            out.append(
                Showing(
                    key=str(x["key"]),
                    movie_id=str(x["movie_id"]),
                    movie_name=x["movie_name"],
                    date=item_date,
                    start_time=str(x["start_time"]),
                    total_seats=x.get("total_seats"),
                    remaining_seats=x.get("remaining_seats"),
                    seats=seats or None,
                )
            )
        return out


class CgvTimetableFeed:
    """Live CGV timetable/remaining-seat adapter via a public read-only facade.

    It intentionally uses only documented/publicly reachable data and does not
    attempt to bypass CGV security controls. The current upstream CGV facade
    exposes remaining seat counts, not individual seat labels.
    """

    def __init__(
        self,
        theater_code: str = "0013",
        api_base: str = "https://mcp.aka.page/api/cgv/timetable",
        timeout: float = 15,
        imax_min_total_seats: int = 500,
        discovery_days: int = 7,
    ):
        self.theater_code = theater_code
        self.api_base = api_base
        self.timeout = timeout
        self.imax_min_total_seats = imax_min_total_seats
        self.discovery_days = max(1, min(discovery_days, 14))

    async def fetch(self, dates: Iterable[str] | None = None) -> list[Showing]:
        target_dates = list(dict.fromkeys(normalize_date(d) for d in dates)) if dates else self.discovery_dates()
        out: list[Showing] = []
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            for play_date in target_dates:
                r = await client.get(
                    self.api_base,
                    params={"playDate": play_date, "theaterCode": self.theater_code, "limit": 100},
                    headers={"Accept": "application/json", "Accept-Language": "ko-KR"},
                )
                _raise_for_status(r)
                raw = r.json()
                for x in _extract_timetable(raw):
                    total = _to_int(x.get("totalSeats"))
                    remaining = _to_int(x.get("remainingSeats"))
                    # Yongsan IMAX is the very large auditorium. The public facade
                    # currently omits screen-format metadata, so this conservative
                    # capacity threshold keeps regular screens out of the live feed.
                    if total is not None and total < self.imax_min_total_seats:
                        continue
                    movie_id = str(x.get("movieCode") or x.get("movieId") or x.get("movNo") or "")
                    movie_name = str(x.get("movieName") or x.get("movNm") or "").strip()
                    start_time = _format_time(x.get("startTime") or x.get("scnsrtTm") or "")
                    item_date = normalize_date(str(x.get("playDate") or x.get("scnYmd") or play_date))
                    schedule_id = str(
                        x.get("scheduleId")
                        or x.get("scnSseq")
                        or f"{self.theater_code}:{item_date}:{movie_id}:{start_time}"
                    )
                    if not movie_id or not movie_name or not start_time:
                        continue
                    out.append(
                        Showing(
                            key=schedule_id,
                            movie_id=movie_id,
                            movie_name=movie_name,
                            date=item_date,
                            start_time=start_time,
                            total_seats=total,
                            remaining_seats=remaining,
                            seats=None,
                        )
                    )
        return out

    def discovery_dates(self) -> list[str]:
        today = date.today()
        return [(today + timedelta(days=i)).strftime("%Y%m%d") for i in range(self.discovery_days)]


def normalize_date(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits[:8] if len(digits) >= 8 else value


def _format_time(value: object) -> str:
    s = str(value or "").strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) >= 4:
        return f"{digits[:2]}:{digits[2:4]}"
    return s


def _to_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_timetable(raw: object) -> list[dict]:
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if not isinstance(raw, dict):
        return []
    candidates = [
        raw.get("timetable"),
        raw.get("showtimes"),
        raw.get("items"),
        raw.get("data"),
    ]
    data = raw.get("data")
    if isinstance(data, dict):
        candidates.extend([data.get("timetable"), data.get("showtimes"), data.get("items"), data.get("data")])
    for candidate in candidates:
        if isinstance(candidate, list):
            return [x for x in candidate if isinstance(x, dict)]
    return []


def _raise_for_status(r: httpx.Response) -> None:
    if r.status_code == 429:
        raise RateLimited("feed returned HTTP 429")
    if r.status_code in (401, 403):
        raise Forbidden(f"feed returned HTTP {r.status_code}")
    r.raise_for_status()
