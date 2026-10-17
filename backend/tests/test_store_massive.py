import datetime as dt

import pandas as pd

from app import store
from app.collectors import massive


def test_upsert_keeps_old_rows_and_dedups():
    store.upsert("t", pd.DataFrame({"date": [1, 2], "source": "a", "v": [1, 2]}), ["source", "date"])
    out = store.upsert("t", pd.DataFrame({"date": [2, 3], "source": "a", "v": [20, 3]}), ["source", "date"])
    assert out["v"].tolist() == [1, 20, 3]


def test_split_adjustment():
    d = [dt.date(2024, 1, i) for i in (2, 3, 4)]
    bars = pd.DataFrame({"date": d, "ticker": "X", "close": [100.0, 100.0, 50.0], "volume": [1000.0, 1000.0, 2000.0]})
    sp = pd.DataFrame({"ticker": ["X"], "execution_date": [dt.date(2024, 1, 4)], "split_from": [1], "split_to": [2]})
    out = massive.adjust_for_splits(bars, sp).sort_values("date")
    assert out["close"].round(6).tolist() == [50.0, 50.0, 50.0]
    assert out["volume"].round(6).tolist() == [2000.0, 2000.0, 2000.0]


def test_massive_grouped_cache(monkeypatch):
    class Fake(massive.Client):
        def __init__(self):
            self.calls = 0

        def get(self, url, params=None):
            self.calls += 1
            return {"results": [{"T": "AAA", "c": 10.0, "v": 5e5, "o": 9}]}

    c = Fake()
    d = dt.date(2024, 1, 2)
    a = massive.grouped(c, d)
    b = massive.grouped(c, d)       # second call served from cache
    assert c.calls == 1 and a.equals(b) and a.columns.tolist() == ["date", "ticker", "close", "volume"]
