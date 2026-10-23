import datetime as dt

import pandas as pd

from app import macro


def raw(values, start=dt.date(2020, 1, 1), months=True):
    dates = [(pd.Timestamp(start) + (pd.DateOffset(months=i) if months else pd.Timedelta(weeks=i))).date() for i in range(len(values))]
    return pd.DataFrame({"date": dates, "value": values})


def test_transforms():
    cpi = macro.display_series(raw([100 + i for i in range(24)]), "CPIAUCSL")      # yoy on monthly = 12 obs lag
    assert round(cpi.iloc[-1], 4) == round((123 / 111 - 1) * 100, 4)
    jobs = macro.display_series(raw([1000, 1010, 1005]), "PAYEMS")                  # mom change
    assert jobs.tolist() == [10, -5]
    claims = macro.display_series(raw([200000, 210000], months=False), "ICSA")      # scaled to thousands
    assert claims.tolist() == [200.0, 210.0]


def test_flags():
    s = pd.Series([0.1, 0.6], index=[dt.date(2026, 8, 1), dt.date(2026, 9, 1)])
    assert macro._flags("SAHMREALTIME", s)[0]["code"] == "sahm"
    assert macro._flags("T10Y2Y", pd.Series([-0.1], index=[dt.date(2026, 9, 1)]))[0]["code"] == "inverted"
    hy = pd.Series([3.0, 4.2], index=[dt.date(2026, 8, 1), dt.date(2026, 9, 5)])
    assert macro._flags("BAMLH0A0HYM2", hy)[0]["code"] == "hy_spike"
    assert macro._flags("UNRATE", pd.Series([4.0], index=[dt.date(2026, 9, 1)])) == []


def test_release_detection_dates_new_observations():
    import datetime as dt
    import pandas as pd
    from app import macro, store
    d = [dt.date(2025, m, 1) for m in range(1, 13)] + [dt.date(2026, m, 1) for m in range(1, 10)]
    old = pd.DataFrame({"series": "UNRATE", "date": d[:-1], "value": 4.0})
    new = pd.DataFrame({"series": "UNRATE", "date": d, "value": [4.0] * 20 + [4.3]})
    daily = pd.DataFrame({"series": "DGS10", "date": d, "value": 4.0})
    now = dt.datetime(2026, 10, 2, 13, 0, tzinfo=dt.timezone.utc)   # 09:00 ET
    rel = macro.record_releases(pd.concat([old, daily[:-1]]), pd.concat([new, daily]), now)
    assert rel["series"].tolist() == ["UNRATE"]                      # daily market series are not releases
    assert rel.loc[0, "date"] == dt.date(2026, 10, 2) and round(rel.loc[0, "value"] - rel.loc[0, "prev"], 6) == 0.3
    assert macro.record_releases(pd.concat([new]), pd.concat([new]), now).empty   # nothing new
    store.write("indices", pd.DataFrame({"symbol": "^GSPC", "date": [dt.date(2026, 10, 1), dt.date(2026, 10, 2)], "close": [100.0, 98.0]}))
    r = macro.releases(days=3650)[0]
    assert r["series"] == "UNRATE" and round(r["spx"], 6) == -2 and "us10y" not in r
