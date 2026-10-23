import datetime as dt

import pandas as pd

from app import earnings


def test_parse_and_reaction_by_report_time():
    ev = earnings.parse(dt.date(2026, 10, 6), [
        {"symbol": "A", "name": "a", "time": "time-pre-market", "eps": "$1.10", "epsForecast": "$1.00", "noOfEsts": "5", "marketCap": "$3,000,000,000"},
        {"symbol": "B", "name": "b", "time": "time-after-hours", "eps": "($0.20)", "epsForecast": "($0.10)", "noOfEsts": "2", "marketCap": "N/A"},
        {"symbol": "C", "name": "c", "time": "time-not-supplied", "eps": "N/A", "epsForecast": "$2.00", "noOfEsts": "1", "marketCap": "$1"}])
    assert round(ev.loc[0, "surprise"], 6) == 10 and ev.loc[1, "eps"] == -0.2 and round(ev.loc[1, "surprise"], 6) == -100
    assert pd.isna(ev.loc[2, "eps"]) and ev.loc[2, "time"] == ""
    d = [dt.date(2026, 10, x) for x in (5, 6, 7, 8)]
    bars = pd.concat([pd.DataFrame({"date": d, "ticker": t, "close": [100.0, 110, 121, 121]}) for t in "ABC"])
    r = earnings.react(ev, bars).set_index("symbol")
    assert round(r.loc["A", "react"], 6) == 10 and r.loc["A", "react_days"] == 1        # pre-market: D vs D-1
    assert round(r.loc["B", "react"], 6) == 10 and r.loc["B", "react_days"] == 1        # after hours: D+1 vs D
    assert round(r.loc["C", "react"], 6) == 21 and r.loc["C", "react_days"] == 2        # unknown time: D+1 vs D-1
