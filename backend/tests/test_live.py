import datetime as dt
from zoneinfo import ZoneInfo

import pandas as pd

from app import refresh, remote
from app.market_calendar import live_session

KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")


def test_live_session_window():
    mon = dt.date(2026, 10, 19)
    at = lambda h, m, tz=KST: dt.datetime(2026, 10, 19, h, m, tzinfo=tz)
    assert live_session(at(8, 59), "XKRX") is None  # before the open
    assert live_session(at(9, 0), "XKRX") == mon
    assert live_session(at(17, 59), "XKRX") == mon  # closed but not final yet
    assert live_session(at(18, 0), "XKRX") is None  # final -> regular refresh
    assert live_session(at(9, 29, ET), "NYSE") is None
    assert live_session(at(9, 30, ET), "NYSE") == mon
    assert live_session(dt.datetime(2026, 10, 18, 12, 0, tzinfo=KST), "XKRX") is None  # Sunday


def test_clean_bars_live_keeps_today(monkeypatch):
    today = dt.date(2026, 10, 19)
    monkeypatch.setattr(refresh, "live_session", lambda cal: today)
    monkeypatch.setattr(refresh, "latest_complete_session", lambda cal: dt.date(2026, 10, 16))
    bars = pd.DataFrame({"date": [dt.date(2026, 10, 16), today], "ticker": ["A", "A"], "close": [1.0, 2.0], "volume": [1, 1]})
    assert list(refresh._clean_bars(bars, "XKRX", live=True)["date"]) == [dt.date(2026, 10, 16), today]
    assert list(refresh._clean_bars(bars, "XKRX")["date"]) == [dt.date(2026, 10, 16)]


def test_version_tracks_content():
    a = pd.DataFrame({"date": [dt.date(2026, 10, 19)], "x": [1.0]})
    assert remote.version(a) == remote.version(a.copy())
    assert remote.version(a) != remote.version(a.assign(x=2.0))
    assert remote.version(a)["rows"] == 1


def test_load_splices_recent_rows(monkeypatch):
    """Changed version -> only rows from SPLICE_DAYS before the cached end are re-read."""
    d = [dt.date(2026, 9, 1), dt.date(2026, 10, 16), dt.date(2026, 10, 19)]
    table = pd.DataFrame({"date": d, "x": [1.0, 2.0, 3.5]})  # published: today's row changed
    cached = table.assign(x=[1.0, 2.0, 3.0])
    queries = []

    class Cur:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def execute(self, sql, params=()):
            queries.append(sql)
            if "versions" in sql:
                self.rows, self.description = [({"hash": "new", "rows": 3},)], None
            elif "to_regclass" in sql:
                self.rows = [("t",)]
            else:
                df = table[table["date"] >= params[0]] if params else table
                self.description = [type("D", (), {"name": c}) for c in df.columns]
                self.rows = list(df.itertuples(index=False, name=None))
        def fetchone(self): return self.rows[0]
        def fetchall(self): return self.rows

    class Con(Cur):
        def cursor(self): return Cur()
        def commit(self): pass

    monkeypatch.setattr(remote, "_connect", Con)
    import time
    df = remote._load("t", (0.0, cached, "old", time.time()))
    assert list(df["x"]) == [1.0, 2.0, 3.5]
    assert any("WHERE date >=" in q for q in queries) and not any(q.endswith('"t"') for q in queries)


def test_recent_part_only_when_history_unchanged():
    d = [dt.date(2026, 9, 1), dt.date(2026, 10, 16), dt.date(2026, 10, 19)]
    old = pd.DataFrame({"date": d, "x": [1.0, 2.0, 3.0]})
    v = remote.version(old)
    cut, rows = remote.recent_part(old.assign(x=[1.0, 2.0, 3.5]), v)  # only today changed
    assert str(cut) == v["cut"] and list(rows["x"]) == [2.0, 3.5]
    assert remote.recent_part(old.assign(x=[9.0, 2.0, 3.0]), v) is None  # history revised -> full write


def test_coverage_flags_thin_last_session():
    d0, d1 = dt.date(2026, 10, 16), dt.date(2026, 10, 19)
    bars = pd.DataFrame({"date": [d0] * 100 + [d1] * 97, "ticker": list(range(100)) + list(range(97))})
    assert refresh._coverage(bars) == 0.97 < refresh.MIN_COVERAGE
    assert refresh._coverage(bars[bars["date"] == d0]) == 1.0
