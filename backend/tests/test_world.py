import datetime as dt

import numpy as np
import pandas as pd

from app import world


def series(values):
    d0 = dt.date(2025, 1, 1)
    return pd.Series(values, index=[d0 + dt.timedelta(days=i) for i in range(len(values))], dtype=float)


def codes(m):
    return {f["code"] for f in m["flags"]}


def test_flags():
    rng = np.random.default_rng(0)
    base = 100 * np.cumprod(1 + rng.normal(0, 0.01, 300))
    today = dt.date(2025, 1, 1) + dt.timedelta(days=299)
    crash = series(list(base[:-1]) + [base[-2] * 0.9])                # -10% day on 1% vol -> big move down
    m = world.analyze(crash, "X", 2.0, 10.0, today)
    assert "big_move" in codes(m) and m["flags"][0]["level"] == "down" and m["z1d"] < -5
    high = series(list(np.linspace(100, 200, 300)))                    # steady rise -> 52w high, no drawdown
    m = world.analyze(high, "X", 2.0, 10.0, today)
    assert "high52" in codes(m) and "correction" not in codes(m) and round(m["chg1d"], 4) > 0
    dd = series(list(np.linspace(100, 200, 280)) + [170] * 20)         # -15% from high -> correction
    assert "correction" in codes(world.analyze(dd, "X", 2.0, 10.0, today))
    assert "bear" in codes(world.analyze(dd, "X", 2.0, 5.0, today))     # -15% <= -2*5%
    vix = series([15.0] * 299 + [32.0])                                  # VIX: fear + spike, colors inverted
    m = world.analyze(vix, "^VIX", 2.0, 10.0, today)
    assert {"vix_fear", "vix_spike"} <= codes(m) and all(f["level"] == "down" for f in m["flags"])
    assert "stale" in codes(world.analyze(high, "X", 2.0, 10.0, today + dt.timedelta(days=10)))


def test_yields_bp_and_inversion():
    today = dt.date(2025, 1, 1) + dt.timedelta(days=299)
    y = series([4.0] * 299 + [4.2])                       # +20bp day on a flat series
    m = world.analyze(y, "^TNX", 2.0, 10.0, today)
    assert m["unit"] == "bp" and round(m["chg1d"], 6) == 20.0 and m["dd52"] is None
    assert {"big_move", "high52"} <= codes(m) and all(f["level"] == "down" for f in m["flags"])
    rows = [{"symbol": "^TNX", "close": 4.0, "flags": []}, {"symbol": "^IRX", "close": 4.5, "flags": []}]
    world._curve_flag(rows)
    assert rows[0]["spread_10y3m"] == -50.0 and rows[0]["flags"][0]["code"] == "inverted"


def test_missing(monkeypatch):
    listed = ["^GSPC", *world.ETF_BENCH]
    monkeypatch.setattr(world, "config", lambda: [{"symbol": "^GSPC"}])
    monkeypatch.setattr(world.store, "read", lambda _: pd.DataFrame({"symbol": listed}))
    assert not world.missing()
    monkeypatch.setattr(world.store, "read", lambda _: pd.DataFrame({"symbol": listed[:-1]}))  # new ETF -> refresh
    assert world.missing()
