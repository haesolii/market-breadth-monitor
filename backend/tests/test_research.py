import datetime as dt

import pandas as pd

from app import research


def spy(n=40):
    d0 = dt.date(2024, 1, 1)
    return pd.DataFrame({"date": [d0 + dt.timedelta(days=i) for i in range(n)], "close": [100.0 + i for i in range(n)]})


def test_forward_returns_no_lookahead():
    fr = research.forward_returns(spy(10))
    assert round(fr.loc[0, "r1"], 6) == 1.0          # 101/100 - 1
    assert fr["r20"].isna().all()                     # not enough future -> NaN, never filled
    assert fr.loc[9, "r1"] != fr.loc[9, "r1"]         # last day has no forward data


def test_cluster_vs_independent():
    s = spy()
    series = pd.DataFrame({"date": s["date"], "value": [0] * 40})
    series.loc[[5, 6, 7, 20], "value"] = 200
    ind = research.study(series, s, 100, ">=", "independent")
    clu = research.study(series, s, 100, ">=", "cluster", gap=5)
    assert ind["n_events"] == 4 and clu["n_events"] == 2
    assert ind["stats"][20]["n"] == 3                 # day 20 has no +20 session data -> excluded


def test_calendar_thread_safe():
    import concurrent.futures as cf
    import datetime as dt
    from app import market_calendar as mc
    mc._cal.cache_clear()  # cold calendars, many concurrent first uses
    with cf.ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda c: mc.latest_complete_session(cal=c), ["XKRX", "NYSE"] * 8))
    assert all(isinstance(r, dt.date) for r in res)
