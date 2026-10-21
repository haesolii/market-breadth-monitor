"""Breadth indicators from daily bars, in one DuckDB window pass.

Input bars: columns (date, ticker, close, volume), split-adjusted, one row per
ticker per session, already restricted to the common-stock universe.
Windows are per-ticker BAR windows (TC2000 semantics: C1, C5, C20, MINC65 ...
refer to the ticker's own previous bars). Every window must be full, otherwise
the stock is not eligible for that indicator on that day.

Formulas: see docs/indicator-definitions.md (TC2000 v12.4 thresholds).
"""
import pandas as pd

from . import store
from .universes import US, Params


def _w(n_prec: int, n_end: str = "CURRENT ROW") -> str:
    return f"OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN {n_prec} PRECEDING AND {n_end})"


FEATURES = f"""
SELECT ticker, date, close, volume,
  LAG(close, 1)  OVER (PARTITION BY ticker ORDER BY date) AS c1,
  LAG(volume, 1) OVER (PARTITION BY ticker ORDER BY date) AS v1,
  LAG(close, 5)  OVER (PARTITION BY ticker ORDER BY date) AS c5,
  LAG(close, 20) OVER (PARTITION BY ticker ORDER BY date) AS c20,
  MIN(volume)   {_w(3, '1 PRECEDING')} AS minv3,
  COUNT(volume) {_w(3, '1 PRECEDING')} AS nv3,
  AVG(close) {_w(19)} * AVG(volume) {_w(19)} AS dv20,
  COUNT(close) {_w(19)} AS n20,
  MIN(close) {_w(33)} AS minc34, MAX(close) {_w(33)} AS maxc34, COUNT(close) {_w(33)} AS n34,
  AVG(close) {_w(39)} AS sma40, COUNT(close) {_w(39)} AS n40,
  MIN(close) {_w(64)} AS minc65, MAX(close) {_w(64)} AS maxc65, COUNT(close) {_w(64)} AS n65
FROM bars
"""

# Per-stock boolean flags. Expressions follow the published TC2000 scans literally.
FLAGS = """
SELECT *,
  (n20 = 20 AND dv20 >= {dv}) AS liq,
  (c1 > 0 AND v1 IS NOT NULL) AS el_daily,
  (c1 > 0 AND 100 * (close - c1) / c1 >= 4    AND volume >= {vol} AND volume > v1) AS up4,
  (c1 > 0 AND 100 * (close - c1) / c1 <= (-4) AND volume >= {vol} AND volume > v1) AS down4,
  (c5 > 0 AND nv3 = 3) AS el_20,
  (c5 > 0 AND close >= c5 * 1.2 AND nv3 = 3 AND minv3 > {vol} AND close >= {px}) AS bull20,
  (c5 > 0 AND close <  c5 * 0.8 AND nv3 = 3 AND minv3 > {vol} AND close >= {px}) AS bear20,
  (n65 = 65 AND n20 = 20 AND dv20 >= {dv}) AS el_q,
  (n65 = 65 AND n20 = 20 AND dv20 >= {dv} AND 100 * ((close + .01) - (minc65 + .01)) / (minc65 + .01) >= 25)   AS q_up25,
  (n65 = 65 AND n20 = 20 AND dv20 >= {dv} AND 100 * ((close + .01) - (maxc65 + .01)) / (maxc65 + .01) <= (-25)) AS q_down25,
  (c20 >= {px} AND n20 = 20 AND dv20 >= {dv}) AS el_m,
  (c20 >= {px} AND n20 = 20 AND dv20 >= {dv} AND 100 * (close - c20) / c20 >= 25)    AS m_up25,
  (c20 >= {px} AND n20 = 20 AND dv20 >= {dv} AND 100 * (close - c20) / c20 <= (-25)) AS m_down25,
  (c20 >= {px} AND n20 = 20 AND dv20 >= {dv} AND 100 * (close - c20) / c20 >= 50)    AS m_up50,
  (c20 >= {px} AND n20 = 20 AND dv20 >= {dv} AND 100 * (close - c20) / c20 <= (-50)) AS m_down50,
  (n34 = 34 AND n20 = 20 AND dv20 >= {dv}) AS el_34,
  (n34 = 34 AND n20 = 20 AND dv20 >= {dv} AND 100 * ((close + .01) - (minc34 + .01)) / (minc34 + .01) >= 13)   AS d34_up13,
  (n34 = 34 AND n20 = 20 AND dv20 >= {dv} AND 100 * ((close + .01) - (maxc34 + .01)) / (maxc34 + .01) <= (-13)) AS d34_down13,
  (n40 = 40) AS el_t2108,
  (n40 = 40 AND close > sma40) AS above40
FROM ({FEATURES}) f
"""

def flags_sql(p: Params = US) -> str:
    """Per-stock flags with the universe's thresholds substituted."""
    return FLAGS.format(FEATURES=FEATURES, px=p.price_floor, vol=p.min_volume, dv=p.min_dollar_vol)


# Minimum dataset sessions before an indicator is meaningful (warm-up). Days
# before that are emitted as NULL, never as a misleading 0.
WARMUP = {"up4": 1, "bull20": 5, "month": 20, "d34": 33, "t2108": 39, "quarter": 64}

MM_COLS = ["up4", "down4", "ratio5", "ratio10", "quarter_up25", "quarter_down25",
           "month_up25", "month_down25", "month_up50", "month_down50",
           "day34_up13", "day34_down13", "day34_diff", "t2108"]


def cut_breaks(bars: pd.DataFrame, limit: float | None, max_gap: int | None = None) -> pd.DataFrame:
    """Split each ticker's history at moves beyond the daily price limit (+1pt
    tolerance) or, on 24/7 markets, at trading halts longer than max_gap days
    (redenominations / relistings under the same symbol): the parts become separate
    series (ticker#1, ticker#2, ...) so no window spans the break, while earlier
    history still counts on its own dates. No-op when the market has neither."""
    if not (limit or max_gap) or bars.empty:
        return bars
    b = bars.sort_values(["ticker", "date"])
    g = b.groupby("ticker")
    brk = (g["close"].pct_change().abs() > limit + 0.01) if limit else pd.Series(False, index=b.index)
    if max_gap:
        brk |= pd.to_datetime(b["date"]).groupby(b["ticker"]).diff().dt.days > max_gap
    seg = brk.groupby(b["ticker"]).cumsum()
    return b.assign(ticker=b["ticker"].where(seg == 0, b["ticker"] + "#" + seg.astype(str)))


def compute(bars: pd.DataFrame, p: Params = US) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (breadth20, market_monitor_daily) frames, one row per session."""
    bars = cut_breaks(bars, p.daily_limit, p.max_gap_days)
    daily = store.sql(f"""
        SELECT date,
          count(*) AS eligible_universe_count,
          sum(el_daily::INT) AS elig_daily, sum(up4::INT) AS up4, sum(down4::INT) AS down4,
          sum(el_20::INT) AS elig_20, sum(bull20::INT) AS bull, sum(bear20::INT) AS bear,
          sum(el_q::INT) AS elig_quarter, sum(q_up25::INT) AS quarter_up25, sum(q_down25::INT) AS quarter_down25,
          sum(el_m::INT) AS elig_month, sum(m_up25::INT) AS month_up25, sum(m_down25::INT) AS month_down25,
          sum(m_up50::INT) AS month_up50, sum(m_down50::INT) AS month_down50,
          sum(el_34::INT) AS elig_34, sum(d34_up13::INT) AS day34_up13, sum(d34_down13::INT) AS day34_down13,
          sum(el_t2108::INT) AS elig_t2108, sum(above40::INT) AS above40
        FROM ({flags_sql(p)}) GROUP BY date ORDER BY date""", bars=bars)
    daily["date"] = pd.to_datetime(daily["date"]).dt.date
    # Provider outage days (e.g. a session where only a handful of tickers have bars)
    # would give wrong breadth: emit nothing for them instead of a misleading count.
    n = daily["eligible_universe_count"]
    daily = daily[~(n < 0.5 * n.rolling(20, min_periods=5).median())].reset_index(drop=True)
    i = daily.index  # dataset session ordinal
    for cols, key in ((["up4", "down4", "elig_daily"], "up4"),
                      (["bull", "bear", "elig_20"], "bull20"),
                      (["month_up25", "month_down25", "month_up50", "month_down50", "elig_month"], "month"),
                      (["day34_up13", "day34_down13", "elig_34"], "d34"),
                      (["above40", "elig_t2108"], "t2108"),
                      (["quarter_up25", "quarter_down25", "elig_quarter"], "quarter")):
        daily[cols] = daily[cols].astype("Float64")
        daily.loc[i < WARMUP[key], cols] = pd.NA

    up, dn = daily["up4"], daily["down4"]
    for n in (5, 10):
        s_up = up.rolling(n, min_periods=n).sum()
        s_dn = dn.rolling(n, min_periods=n).sum()
        # Division by zero (no 4% decliners in the window) -> NULL, not infinity.
        daily[f"ratio{n}"] = (s_up / s_dn.where(s_dn > 0)).round(2)
    daily["day34_diff"] = daily["day34_up13"] - daily["day34_down13"]
    daily["t2108"] = (100 * daily["above40"] / daily["elig_t2108"].where(daily["elig_t2108"] > 0)).round(2)

    b20 = daily[["date", "bull", "bear", "elig_20", "eligible_universe_count"]].dropna(subset=["bull"])
    mm = daily[["date", *MM_COLS, "eligible_universe_count", "elig_daily", "elig_month",
                "elig_quarter", "elig_34", "elig_t2108"]].dropna(subset=["up4"])
    return b20.reset_index(drop=True), mm.reset_index(drop=True)


SCAN_SIGNALS = ["bull20", "bear20", "up4", "down4", "q_up25", "q_down25", "m_up25",
                "m_down25", "m_up50", "m_down50", "d34_up13", "d34_down13"]


def scan(bars: pd.DataFrame, date, p: Params = US) -> pd.DataFrame:
    """All stocks meeting any scan condition on `date` (bars must include >=65
    sessions of history before it)."""
    bars = cut_breaks(bars, p.daily_limit, p.max_gap_days)
    any_sig = " OR ".join(SCAN_SIGNALS)
    out = store.sql(f"""
        SELECT ticker, date, close, volume, c1, c5, c20, minv3, dv20,
          100 * (close / c1 - 1) AS ret1, 100 * (close / c5 - 1) AS ret5,
          100 * (close / c20 - 1) AS ret20, {", ".join(SCAN_SIGNALS)}
        FROM ({flags_sql(p)}) WHERE date = DATE '{date}' AND ({any_sig})""", bars=bars)
    out["ticker"] = out["ticker"].str.split("#").str[0]
    return out
