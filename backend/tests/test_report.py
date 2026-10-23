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


def test_score_signal_only_on_crossing():
    assert "약세" in report.score_signal({"score": 28.0, "prev": 33.0})
    assert "강세" in report.score_signal({"score": 71.0, "prev": 69.0})
    assert report.score_signal({"score": 25.0, "prev": 28.0}) is None and report.score_signal({"score": 50.0, "prev": None}) is None
