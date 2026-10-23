import datetime as dt

import pandas as pd

from app import report


def test_signal_levels_and_edge_trigger():
    assert report.cnt(100, "bear", "kospi", 900) == 14          # calibrated market line
    assert report.cnt(1000, "down4", "yahoo", 2500) == 500       # US universes scale by size
    assert report.cnt(1000, "down4", "public_repo", None) == 1000
    d = [dt.date(2026, 10, i) for i in (1, 2, 3)]
    rows = pd.DataFrame({"date": d, "bear": [120, 130, 40], "t2108": [25, 18, 15]})
    assert report.new_signals(rows.iloc[:1], "yahoo") is None    # needs a previous session
    assert report.new_signals(rows.iloc[:2], "yahoo") == ("2026-10-02", ["40일선 위 종목 18.0% — 극단적 과매도 (< 20%)"])
    assert report.new_signals(rows, "yahoo") == ("2026-10-03", [])  # still oversold: not new
