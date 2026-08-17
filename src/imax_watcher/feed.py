from __future__ import annotations
import httpx
from .models import Showing, Seat

class FeedError(RuntimeError): pass
class RateLimited(FeedError): pass
class Forbidden(FeedError): pass

class JsonFeed:
    """Consumes a permitted JSON seat feed; never bypasses CGV access controls."""
    def __init__(self, url: str | None, timeout: float = 10):
        self.url=url; self.timeout=timeout

    async def fetch(self) -> list[Showing]:
        if not self.url:
            return []
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            r=await client.get(self.url, headers={"Accept":"application/json"})
        if r.status_code == 429: raise RateLimited("feed returned HTTP 429")
        if r.status_code in (401,403): raise Forbidden(f"feed returned HTTP {r.status_code}")
        r.raise_for_status()
        raw=r.json()
        items=raw.get("showings", raw if isinstance(raw,list) else [])
        out=[]
        for x in items:
            seats=[Seat(str(s["row"]).upper(), int(s["number"]), bool(s.get("available",True))) for s in x.get("seats",[])]
            out.append(Showing(key=str(x["key"]),movie_id=str(x["movie_id"]),movie_name=x["movie_name"],date=str(x["date"]),start_time=str(x["start_time"]),total_seats=x.get("total_seats"),remaining_seats=x.get("remaining_seats"),seats=seats or None))
        return out
