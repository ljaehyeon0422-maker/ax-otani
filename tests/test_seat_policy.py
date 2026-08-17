import sys
sys.path.insert(0,"src")
from imax_watcher.models import Seat, Preferences
from imax_watcher.seat_policy import qualifying_sets, signature

def hall(rows="ABCDEFGHIJKLMN", n=30):
    return [Seat(r,i,False) for r in rows for i in range(1,n+1)]

def available(base,*names):
    wanted=set(names)
    return [Seat(s.row,s.number,s.name in wanted) for s in base]

def test_two_contiguous_okay():
    seats=available(hall(),"H15","H16","H20")
    p=Preferences(2,"all_together","okay")
    assert "H15-H16" in signature(qualifying_sets(seats,p))

def test_front_excluded_in_okay():
    seats=available(hall(),"A15","B15","H15")
    p=Preferences(1,"any","okay")
    sig=signature(qualifying_sets(seats,p))
    assert "H15" in sig and "A15" not in sig

def test_override_priority():
    p=Preferences().merged({"party_size":1}).merged({"seat_scope":"good"})
    assert p.party_size==1 and p.seat_scope=="good"
