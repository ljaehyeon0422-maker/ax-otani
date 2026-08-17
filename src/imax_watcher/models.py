from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Literal

SeatScope = Literal["prime", "good", "okay", "wide"]
AdjacencyMode = Literal["all_together", "min_two", "prefer_together", "any"]

@dataclass(slots=True)
class Preferences:
    party_size: int = 2
    adjacency_mode: AdjacencyMode = "prefer_together"
    seat_scope: SeatScope = "okay"

    def merged(self, override: dict | None) -> "Preferences":
        data = asdict(self)
        if override:
            data.update({k: v for k, v in override.items() if v is not None})
        return Preferences(**data)

@dataclass(slots=True, frozen=True)
class Seat:
    row: str
    number: int
    available: bool = True

    @property
    def name(self) -> str:
        return f"{self.row.upper()}{self.number}"

@dataclass(slots=True)
class Showing:
    key: str
    movie_id: str
    movie_name: str
    date: str
    start_time: str
    total_seats: int | None = None
    remaining_seats: int | None = None
    seats: list[Seat] | None = None
