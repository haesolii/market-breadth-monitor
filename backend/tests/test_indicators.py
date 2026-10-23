import datetime as dt

import pandas as pd

from app import indicators


def bars(series: dict[str, list[tuple[float, float]]]) -> pd.DataFrame:
    """series: ticker -> [(close, volume), ...] on consecutive dates."""
    d0 = dt.date(2024, 1, 1)
    rows = [(d0 + dt.timedelta(days=i), t, c, v)
            for t, vals in series.items() for i, (c, v) in enumerate(vals)]
    return pd.DataFrame(rows, columns=["date", "ticker", "close", "volume"])


def test_bull_bear_20pct():
    n = 70
    flat = [(10.0, 200_000)] * n
    up = [(10.0, 200_000)] * (n - 1) + [(12.0, 200_000)]          # exactly +20% -> bull
    dn = [(10.0, 200_000)] * (n - 1) + [(7.99, 200_000)]          # < 0.8x -> bear
    dn_edge = [(10.0, 200_000)] * (n - 1) + [(8.0, 200_000)]      # exactly 0.8x -> not bear
    lowvol = [(10.0, 200_000)] * (n - 3) + [(10.0, 100_000)] * 2 + [(12.0, 200_000)]  # minv3 = 100k, not >
    cheap = [(4.0, 200_000)] * (n - 1) + [(4.9, 200_000)]         # < $5
    b20, mm = indicators.compute(bars({"F": flat, "U": up, "D": dn, "E": dn_edge, "L": lowvol, "C": cheap}))
    last = b20.iloc[-1]
    assert (last.bull, last.bear) == (1, 1)
    assert b20.iloc[0:5].empty or b20.date.min() > dt.date(2024, 1, 5)  # warm-up rows dropped


def test_market_monitor():
    n = 70
    base = [(10.0, 200_000)] * (n - 1)
    s = {
        "UP4": base + [(10.4, 200_001)],       # +4%, vol >= 100k and > prior -> up4
        "UP4NV": base + [(10.4, 200_000)],     # vol not > prior -> no
        "DN4": base + [(9.6, 300_000)],        # -4% -> down4
        "M50": base + [(15.0, 300_000)],       # +50% vs C20 -> month up25 & up50, quarter up25, 34d up13
        "T": [(10.0 + i * 0.01, 200_000) for i in range(n)],  # rising -> above SMA40
    }
    _, mm = indicators.compute(bars(s))
    last = mm.iloc[-1]
    assert last.up4 == 2 and last.down4 == 1          # UP4 + M50 up (M50 vol 300k > 200k)
    assert last.month_up50 == 1 and last.month_up25 == 1
    assert last.quarter_up25 == 1 and last.day34_up13 == 1 and last.day34_diff == 1
    assert last.t2108 == 80.0                           # UP4, UP4NV, M50, T above SMA40; DN4 below
    assert last.eligible_universe_count == 5
    # warm-up: quarter NULL before 65 sessions
    assert pd.isna(mm.iloc[10].quarter_up25) and not pd.isna(mm.iloc[-1].quarter_up25)


def test_ratio_div_zero():
    n = 30
    s = {"A": [(10.0 * (1.05 ** (i % 2)), 100_000 + i * 1000) for i in range(n)]}  # alternating +5% / -4.76%
    _, mm = indicators.compute(bars(s))
    assert mm.ratio5.notna().any()
    s2 = {"A": [(10.0 * 1.05 ** i, 100_000 + i * 1000) for i in range(n)]}  # only ups -> ratio NULL
    _, mm2 = indicators.compute(bars(s2))
    assert mm2.ratio5.isna().all()


def test_kr_params_and_breaks():
    from app.universes import KR
    n = 70
    # 5 -> 6 (+20%), 200k shares: passes the US $5 floor, fails the KR ₩1,000 floor
    s = {"A": [(5.0, 200_000)] * (n - 1) + [(6.0, 200_000)]}
    b20_kr, _ = indicators.compute(bars(s), KR)
    b20_us, _ = indicators.compute(bars(s))
    assert b20_us.iloc[-1].bull == 1 and b20_kr.iloc[-1].bull == 0
    # unadjusted 10:1 reverse split 5 bars ago (+900%): KR cuts history at the break -> no fake bull
    s = {"B": [(224.0, 200_000)] * (n - 5) + [(2240.0, 200_000)] * 5, "C": [(2000.0, 200_000)] * n}
    cut = indicators.cut_breaks(bars(s), KR.daily_limit)
    assert set(cut[cut.ticker == "B"].close) == {224.0} and set(cut[cut.ticker == "B#1"].close) == {2240.0}
    assert len(cut[cut.ticker == "C"]) == n
    b20, _ = indicators.compute(bars(s), KR)
    assert b20.bull.fillna(0).max() == 0


def test_crypto_halt_splits_series():
    from app.universes import CRYPTO
    d0 = dt.date(2024, 1, 1)
    # 1000:1 redenomination after a 10-day halt: two series, no fake +99,900% move
    b = pd.DataFrame({"date": [d0 + dt.timedelta(days=i) for i in [*range(30), *range(40, 70)]], "ticker": "X",
                      "close": [1.0] * 30 + [1000.0] * 30, "volume": 1e6})
    cut = indicators.cut_breaks(b, CRYPTO.daily_limit, CRYPTO.max_gap_days)
    assert set(cut[cut.ticker == "X"].close) == {1.0} and set(cut[cut.ticker == "X#1"].close) == {1000.0}


def test_live_volume_is_paced_to_a_full_day():
    import datetime as dt
    from app import market_calendar as mc
    # 2026-10-21 is a full NYSE session (09:30-16:00 ET = 13:30-20:00 UTC); at 16:45 UTC half has elapsed.
    assert abs(mc.session_elapsed(dt.datetime(2026, 10, 21, 16, 45, tzinfo=dt.timezone.utc)) - 0.5) < 1e-9
    assert mc.session_elapsed(dt.datetime(2026, 10, 21, 21, 0, tzinfo=dt.timezone.utc)) == 1.0
    assert mc.session_elapsed(dt.datetime(2026, 10, 24, 15, 0, tzinfo=dt.timezone.utc)) == 1.0  # Saturday


def test_crypto_uses_turnover_not_unit_count():
    import pandas as pd
    from app import indicators, store
    from app.universes import CRYPTO
    # +5% day on 1M units: at 0.10 USDT (100k turnover) it is too thin, at 1.0 (1M) it counts.
    def up4(px):
        b = pd.DataFrame({"date": pd.to_datetime(["2026-01-01", "2026-01-02"]).date, "ticker": "X",
                          "close": [px, px * 1.05], "volume": [5e5, 1e6]})
        return bool(store.sql(f"SELECT up4 FROM ({indicators.flags_sql(CRYPTO)}) ORDER BY date", bars=b)["up4"].iloc[-1])
    assert not up4(0.10) and up4(1.0)


def test_volume_share_curve():
    from app.market_calendar import volume_share
    assert volume_share(0) == 0 and abs(volume_share(1) - 1) < 1e-12
    assert volume_share(1 / 13) > 1 / 13          # heavy open: more than a linear share after 30 min
    assert volume_share(12 / 13) < 12 / 13        # closing auction still to come
    xs = [volume_share(i / 100) for i in range(101)]
    assert xs == sorted(xs)
