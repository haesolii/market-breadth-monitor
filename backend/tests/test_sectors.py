import datetime as dt

import pandas as pd

from app import sectors, store
from app.universes import KR, US

STEPS = (5, 21, 63, 252)


def _bars(closes: dict[str, list[float]], d0=dt.date(2025, 12, 20)) -> pd.DataFrame:
    return pd.DataFrame([(d0 + dt.timedelta(days=i), t, c, 1000.0) for t, cs in closes.items() for i, c in enumerate(cs)],
                        columns=["date", "ticker", "close", "volume"])


def test_returns_periods_ytd_and_breaks():
    closes = [100.0 + i for i in range(30)]                   # 2025-12-20 .. 2026-01-18
    r, daily = sectors.returns(_bars({"A": closes}), US, STEPS)
    r = r.set_index("ticker").loc["A"]
    assert round(r.r1d, 6) == round((129 / 128 - 1) * 100, 6)
    assert round(r.r1w, 6) == round((129 / 124 - 1) * 100, 6)
    assert pd.isna(r.r3m) and pd.isna(r.r1y)                   # not enough history
    assert round(r.ytd, 6) == round((129 / 111 - 1) * 100, 6)  # vs last close of 2025 (12-31 = 111)
    assert len(daily) == 29 and round(daily["r"].iloc[0], 6) == 0.01
    # Korea: a move beyond the daily limit is an unadjusted corporate action -> only the new series counts
    k, kd = sectors.returns(_bars({"K": [10.0] * 10 + [50.0, 51.0]}), KR, STEPS)
    k = k.set_index("ticker").loc["K"]
    assert round(k.r1d, 6) == 2.0 and pd.isna(k.r1w) and len(kd) == 1


def test_summary_weights_and_nasdaq_filter():
    d = dt.date(2026, 1, 5)
    store.write("sector_map", pd.DataFrame([
        {"market": "yahoo", "ticker": "A", "name": "A", "exchange": "NASDAQ", "sector": "기술", "industry": "", "size": 3.0, "close": 1, "r1d": 10.0, "date": d},
        {"market": "yahoo", "ticker": "B", "name": "B", "exchange": "NYSE", "sector": "기술", "industry": "", "size": 1.0, "close": 1, "r1d": -10.0, "date": d},
    ]).assign(r1w=None, r1m=None, r3m=None, r1y=None, ytd=None))
    s = sectors.summary("yahoo", "r1d")
    assert s["sectors"][0]["ret"] == 5.0 and s["sectors"][0]["up_pct"] == 50.0  # cap-weighted 0.75*10 - 0.25*10
    assert sectors.summary("nasdaq", "r1d")["n"] == 1


def test_sector_index_history_and_beta():
    days = [dt.date(2026, 1, 1) + dt.timedelta(days=i) for i in range(30)]
    daily = pd.DataFrame([(t, d, r) for d, i in zip(days, range(30)) for t, r in (("A", 0.01 * (-1) ** i), ("B", 0.02 * (-1) ** i))],
                         columns=["ticker", "date", "r"])
    stocks = pd.DataFrame({"ticker": ["A", "B"], "sector": ["가", "나"], "size": [1.0, 1.0]})
    sd = sectors.sector_daily(daily, stocks)
    assert round(sd[(sd["sector"] == sectors.ALL)]["ret"].iloc[0], 6) == 0.015   # equal sizes -> average
    store.write("sector_daily", sd.assign(market="kospi"))
    store.write("sector_map", pd.DataFrame({"market": "kospi", "ticker": ["A", "B"], "name": "x", "exchange": "KOSPI",
                                            "sector": ["가", "나"], "industry": "", "size": 1.0, "close": 1.0, "r1d": 1.0,
                                            "r1w": None, "r1m": None, "r3m": None, "r1y": None, "ytd": None, "date": days[-1]}))
    h = sectors.history("kospi", 252, top=5)
    st = {x["sector"]: x for x in h["stats"]}
    assert round(st["나"]["beta"], 6) == round(0.02 / 0.015, 6) and round(st["가"]["corr"], 6) == 1.0
    assert h["series"][sectors.ALL][0] == round((1 + 0.015) * 100, 2) and h["corr"]["matrix"][0][0] == 1.0
