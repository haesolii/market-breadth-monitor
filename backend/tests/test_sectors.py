import datetime as dt

import pandas as pd

from app import sectors, store
from app.universes import KR, US


def _bars(closes: dict[str, list[float]], d0=dt.date(2025, 12, 20)) -> pd.DataFrame:
    return pd.DataFrame([(d0 + dt.timedelta(days=i), t, c, 1000.0) for t, cs in closes.items() for i, c in enumerate(cs)],
                        columns=["date", "ticker", "close", "volume"])


def test_returns_periods_ytd_and_breaks():
    closes = [100.0 + i for i in range(30)]                   # 2025-12-20 .. 2026-01-18
    r = sectors.returns(_bars({"A": closes}), US, (5, 21, 63)).set_index("ticker").loc["A"]
    assert round(r.r1d, 6) == round((129 / 128 - 1) * 100, 6)
    assert round(r.r1w, 6) == round((129 / 124 - 1) * 100, 6)
    assert pd.isna(r.r3m)                                      # not enough history
    assert round(r.ytd, 6) == round((129 / 111 - 1) * 100, 6)  # vs last close of 2025 (12-31 = 111)
    # Korea: a move beyond the daily limit is an unadjusted corporate action -> only the new series counts
    k = sectors.returns(_bars({"K": [10.0] * 10 + [50.0, 51.0]}), KR, (5, 21, 63)).set_index("ticker").loc["K"]
    assert round(k.r1d, 6) == 2.0 and pd.isna(k.r1w)


def test_summary_weights_and_nasdaq_filter():
    d = dt.date(2026, 1, 5)
    store.write("sector_map", pd.DataFrame([
        {"market": "yahoo", "ticker": "A", "name": "A", "exchange": "NASDAQ", "sector": "기술", "industry": "", "size": 3.0, "close": 1, "r1d": 10.0, "date": d},
        {"market": "yahoo", "ticker": "B", "name": "B", "exchange": "NYSE", "sector": "기술", "industry": "", "size": 1.0, "close": 1, "r1d": -10.0, "date": d},
    ]).assign(r1w=None, r1m=None, r3m=None, ytd=None))
    s = sectors.summary("yahoo", "r1d")
    assert s["sectors"][0]["ret"] == 5.0 and s["sectors"][0]["up_pct"] == 50.0  # cap-weighted 0.75*10 - 0.25*10
    assert sectors.summary("nasdaq", "r1d")["n"] == 1
