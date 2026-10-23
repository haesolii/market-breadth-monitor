import datetime as dt

import pandas as pd

from app import leaders, store, watch


def _frame(n=300):
    days = [dt.date(2025, 1, 1) + dt.timedelta(days=i) for i in range(n)]
    rows = []
    for t, slope in (("UP", 1.0), ("DN", -0.1), ("FLAT", 0.0)):
        for i, d in enumerate(days):
            c = 100 + slope * i
            rows.append({"date": d, "ticker": t, "close": c})
    df = pd.DataFrame(rows)
    g = df.groupby("ticker")["close"]
    for n_ in (10, 20, 50):
        df[f"ma{n_}"] = g.transform(lambda s, k=n_: s.rolling(k, min_periods=1).mean())
    df["n10"], df["n50"] = 10, 50
    df["n252"] = g.cumcount() + 1
    df["hi252"] = g.transform(lambda s: s.rolling(252, min_periods=1).max())
    df["lo252"] = g.transform(lambda s: s.rolling(252, min_periods=1).min())
    for col, k in (("r21", 21), ("r63", 63), ("r126", 126)):
        df[col] = g.transform(lambda s, k=k: (s / s.shift(k) - 1) * 100)
    df["adr"], df["dvol"], df["ok"], df["liquid"] = 1.0, 1e9, True, True
    df["r1"], df["gap"], df["vratio"], df["breakout"], df["adr_true"] = 0.0, float("nan"), 1.0, False, True
    return df


def test_breadth_counts_and_leader_health():
    b = leaders.breadth(_frame()).set_index("date").iloc[-1]
    assert round(b.above10, 4) == round(100 / 3, 4)            # only UP is above its rising average
    assert b.new_high == 1 and b.new_low == 1                  # UP at a 252-day high, DN at a low
    assert b.leaders == 1 and b.leaders_above20 == 100.0       # top 2% of 3 stocks = the best one (UP)


def test_leader_list_and_trend():
    f = _frame()
    last = f["date"] == f["date"].max()
    f.loc[last & (f["ticker"] == "FLAT"), ["r1", "vratio"]] = [10.0, 3.0]   # closed +10% on 3x volume, open unknown
    lst = leaders.leaders(f)
    assert lst.loc[lst["kind"] == "leader", "ticker"].tolist() == ["UP"] and bool(lst["above50"].iloc[0])
    assert lst.loc[lst["kind"] == "ep", "ticker"].tolist() == ["FLAT"]
    up = pd.Series([100 + i for i in range(40)], dtype=float)
    assert leaders.trend(up)["state"] == "강세" and leaders.trend(-up + 300)["state"] == "약세"
    assert leaders.trend(up.head(10)) is None


def test_big_flows_relative_to_own_history():
    days = [dt.date(2026, 7, 1) + dt.timedelta(days=i) for i in range(80)]
    f = pd.DataFrame({"date": days, "foreign": [1e9] * 79 + [5e9], "inst": [1e9] * 79 + [-2e9]})
    hits = watch.big_flows(f, size=1e13, since=days[-5])
    assert [(w, x) for _, w, _, x in hits] == [("foreign", 5.0)]   # inst: only 2x its normal
    assert watch.big_flows(f, size=1e15, since=days[-5]) == []      # 5e9 is < 0.01% of a huge cap


def test_watch_alerts_sent_once():
    today = dt.date.today()
    store.write("sector_map", pd.DataFrame({"market": "kospi", "ticker": ["005930"], "name": ["삼성전자"], "exchange": "KOSPI",
                                            "sector": "반도체", "industry": "", "size": [1e15], "close": 1.0, "r1d": [-6.0],
                                            "r1w": None, "r1m": None, "r3m": None, "r1y": None, "ytd": None, "date": today}))
    watch.save([{"ticker": "005930", "market": "kospi", "name": "삼성전자"}])
    first = watch.alerts()
    assert len(first) == 1 and "급등락" in first[0] and "-6.0%" in first[0]
    assert watch.alerts() == []                                     # already sent
    watch.save([])


def test_monitor_reports_start_and_recovery(monkeypatch):
    from app import monitor, refresh
    monkeypatch.setattr(refresh, "enabled_sources", lambda: ["macro"])
    store.set_source("macro", last_success="2026-10-23T00:00:00+00:00", last_error="HTTP 500", last_error_at="2026-10-23T01:00:00+00:00")
    assert monitor.changes() == ["• ⚠️ <b>macro</b>: 갱신 실패: HTTP 500"]
    assert monitor.changes() == []                                   # still broken: no repeat
    store.set_source("macro", last_success=store.now_utc(), last_error=None)
    assert monitor.changes() == ["• ✅ <b>macro</b>: 정상으로 돌아옴"]
