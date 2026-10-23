import datetime as dt

import pandas as pd

from app import etf


def test_changes_between_snapshots():
    d1, d2 = dt.date(2026, 10, 22), dt.date(2026, 10, 23)
    snaps = pd.DataFrame([
        ("F", d1, "A", 100.0, 50.0), ("F", d1, "B", 100.0, 30.0), ("F", d1, "C", 100.0, 20.0),
        ("F", d2, "A", 100.2, 49.0),   # +0.2%: rounding, not a trade
        ("F", d2, "B", 150.0, 40.0),   # bought
        ("F", d2, "D", 10.0, 11.0),    # new; C sold out
    ], columns=["etf", "date", "name", "shares", "weight"]).assign(ticker="")
    ch = etf.changes(snaps).set_index("name")
    assert dict(ch["kind"]) == {"B": "증가", "C": "편출", "D": "편입"}
    assert ch.loc["B", "shares_prev"] == 100 and ch.loc["D", "date"] == d2 and ch.loc["C", "prev_date"] == d1
    assert etf.changes(snaps[snaps["date"] == d1]).empty   # one snapshot: nothing to compare
