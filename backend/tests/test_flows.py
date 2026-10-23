import datetime as dt

import pandas as pd

from app import dart, flows


def test_flow_parse_values_in_won():
    df = flows.parse("005930", [{"bizdate": "20261022", "foreignerPureBuyQuant": "-1,000", "organPureBuyQuant": "+200",
                                 "individualPureBuyQuant": "+800", "foreignerHoldRatio": "46.13%", "closePrice": "214,500"}])
    r = df.iloc[0]
    assert r.date == dt.date(2026, 10, 22) and r.foreign == -214_500_000 and r.inst == 42_900_000 and r.hold_ratio == 46.13


def test_dart_filter_and_two_day_reaction():
    assert dart.is_prelim("연결재무제표기준영업(잠정)실적(공정공시)") and not dart.is_prelim("주요사항보고서")
    d = [dt.date(2026, 10, i) for i in (20, 21, 23)]  # 22nd: no session
    bars = pd.DataFrame({"date": d, "ticker": "A", "close": [100.0, 110.0, 121.0]})
    out = dart.react(pd.DataFrame({"code": ["A"], "date": [dt.date(2026, 10, 21)]}), bars)
    assert round(out["react"].iloc[0], 6) == 21.0 and round(out["ret_since"].iloc[0], 6) == 21.0  # 20th close -> 23rd close
