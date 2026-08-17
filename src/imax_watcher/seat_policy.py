from __future__ import annotations
from collections import defaultdict
from .models import Seat, Preferences

# Row/edge ratios are relative to the live seat map so the policy is not tied to hard-coded seat numbers.
_SCOPE_ROW_BANDS = {
    "prime": (0.35, 0.68, 0.28),
    "good": (0.25, 0.82, 0.18),
    "okay": (0.18, 0.95, 0.10),
    "wide": (0.14, 1.00, 0.05),
}

def _row_rank(rows: list[str], row: str) -> float:
    if len(rows) <= 1:
        return 0.5
    return rows.index(row) / (len(rows) - 1)

def seat_allowed(seat: Seat, all_seats: list[Seat], scope: str) -> bool:
    rows = sorted({s.row.upper() for s in all_seats})
    row = seat.row.upper()
    if row not in rows:
        return False
    rmin, rmax, edge_ratio = _SCOPE_ROW_BANDS[scope]
    if not (rmin <= _row_rank(rows, row) <= rmax):
        return False
    nums = sorted(s.number for s in all_seats if s.row.upper() == row)
    if not nums:
        return False
    lo, hi = min(nums), max(nums)
    width = max(1, hi - lo + 1)
    edge = max(1, round(width * edge_ratio))
    return lo + edge <= seat.number <= hi - edge

def acceptable_available_seats(all_seats: list[Seat], prefs: Preferences) -> list[Seat]:
    return [s for s in all_seats if s.available and seat_allowed(s, all_seats, prefs.seat_scope)]

def contiguous_groups(seats: list[Seat]) -> list[list[Seat]]:
    by_row: dict[str, list[Seat]] = defaultdict(list)
    for seat in seats:
        by_row[seat.row.upper()].append(seat)
    groups: list[list[Seat]] = []
    for row_seats in by_row.values():
        ordered = sorted(row_seats, key=lambda s: s.number)
        current: list[Seat] = []
        for seat in ordered:
            if not current or seat.number == current[-1].number + 1:
                current.append(seat)
            else:
                groups.append(current)
                current = [seat]
        if current:
            groups.append(current)
    return groups

def qualifying_sets(all_seats: list[Seat], prefs: Preferences) -> list[list[Seat]]:
    seats = acceptable_available_seats(all_seats, prefs)
    groups = contiguous_groups(seats)
    n = prefs.party_size
    mode = prefs.adjacency_mode
    if n <= 1:
        return [[s] for s in seats]
    if mode == "all_together":
        return [g[i:i+n] for g in groups for i in range(0, max(0, len(g)-n+1))]
    if mode == "min_two":
        need = min(2, n)
        return [g[i:i+need] for g in groups for i in range(0, max(0, len(g)-need+1))]
    if mode == "prefer_together":
        together = [g[i:i+n] for g in groups for i in range(0, max(0, len(g)-n+1))]
        return together or [[s] for s in seats]
    return [[s] for s in seats]

def signature(groups: list[list[Seat]]) -> set[str]:
    return {"-".join(s.name for s in g) for g in groups}
