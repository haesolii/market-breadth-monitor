"""Event study: what did the benchmark index do after a breadth reading crossed a threshold?

No look-ahead: an event on day D uses only the breadth value known at D's close;
forward return h = index close(D+h sessions) / close(D) - 1. Events whose D+h is
not yet in the data are excluded for that horizon (so n can differ by horizon).
Entry at D's close is slightly optimistic (breadth is known only after the close);
the study reports it as such. Excursions: the worst (MAE) and best (MFE) close within
the next EXC sessions, relative to D's close.
"""
import math

import numpy as np
import pandas as pd

HORIZONS = (1, 3, 5, 10, 20)
EXC = 20


def forward_returns(spy: pd.DataFrame) -> pd.DataFrame:
    s = spy.sort_values("date").reset_index(drop=True)
    for h in HORIZONS:
        s[f"r{h}"] = (s["close"].shift(-h) / s["close"] - 1) * 100
    nxt = s["close"].shift(-1).rolling(pd.api.indexers.FixedForwardWindowIndexer(window_size=EXC), min_periods=EXC)
    s[f"mae{EXC}"] = (nxt.min() / s["close"] - 1) * 100
    s[f"mfe{EXC}"] = (nxt.max() / s["close"] - 1) * 100
    return s


def _cmp(v: pd.Series, op: str, threshold: float) -> pd.Series:
    return v >= threshold if op == ">=" else v <= threshold


def _welch_p(a: np.ndarray, b: np.ndarray) -> float | None:
    """Two-sided Welch t-test p-value (normal approximation; fine for n >= 30,
    indicative only for small samples)."""
    if len(a) < 2 or len(b) < 2:
        return None
    se = math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    if se == 0:
        return None
    t = (a.mean() - b.mean()) / se
    return math.erfc(abs(t) / math.sqrt(2))


def _stats(x: np.ndarray) -> dict:
    if len(x) == 0:
        return {"n": 0}
    return {"n": int(len(x)), "mean": float(x.mean()), "median": float(np.median(x)),
            "win_rate": float((x > 0).mean() * 100), "max": float(x.max()), "min": float(x.min()),
            "std": float(x.std(ddof=1)) if len(x) > 1 else None}


def study(series: pd.DataFrame, spy: pd.DataFrame, threshold: float, op: str = ">=",
          mode: str = "independent", gap: int = 5, op2: str = ">=", threshold2: float | None = None) -> dict:
    """series: (date, value[, value2]). An event needs value op threshold AND, when series has
    value2, value2 op2 threshold2. mode: 'independent' = every qualifying day is an event;
    'cluster' = consecutive qualifying days within `gap` sessions collapse into the first."""
    fr = forward_returns(spy)
    both = "value2" in series and threshold2 is not None
    df = series.dropna(subset=["value", "value2"] if both else ["value"]).merge(fr, on="date", how="inner").reset_index(drop=True)
    if df.empty:
        return {"events": [], "stats": {}, "baseline": {}, "note": "no overlapping index / breadth data"}
    hit = _cmp(df["value"], op, threshold)
    if both:
        hit &= _cmp(df["value2"], op2, threshold2)
    idx = np.flatnonzero(hit.to_numpy())
    if mode == "cluster" and len(idx):
        keep = [idx[0]]
        for prev, cur in zip(idx[:-1], idx[1:]):
            if cur - prev > gap:
                keep.append(cur)
        idx = np.array(keep)
    ev = df.iloc[idx]
    stats, baseline = {}, {}
    for h in HORIZONS:
        col = f"r{h}"
        x = ev[col].dropna().to_numpy()
        allx = df[col].dropna().to_numpy()
        st = _stats(x)
        st["p_vs_baseline"] = _welch_p(x, allx)
        if len(x):
            counts, edges = np.histogram(x, bins=min(20, max(5, len(x) // 3)))
            st["hist"] = {"counts": counts.tolist(), "edges": [round(e, 3) for e in edges.tolist()]}
        stats[h] = st
        baseline[h] = _stats(allx)
    exc = {k: _stats(ev[f"{k}{EXC}"].dropna().to_numpy()) for k in ("mae", "mfe")}
    events = ev[["date", "value", *(["value2"] if both else []), "close", *[f"r{h}" for h in HORIZONS],
                 f"mae{EXC}", f"mfe{EXC}"]].copy()
    events["date"] = events["date"].astype(str)
    return {
        "range": [str(df["date"].min()), str(df["date"].max())],
        "n_days": int(len(df)), "n_events": int(len(ev)),
        "events": events.replace({np.nan: None}).to_dict("records"),
        "stats": stats, "baseline": baseline, "excursion": {"sessions": EXC, **exc},
    }


RET_COLS = {"p20": "과거 20일", "r0": "당일", "r5": "이후 5일", "r20": "이후 20일"}


def indicator_study(ind: pd.DataFrame, prices: pd.DataFrame, cols: list[str], days: int | None = None) -> dict:
    """Indicator levels vs the benchmark: per indicator the latest value, its change over the window
    and its percentile within the window; Spearman rank correlations of each indicator with the
    benchmark's trailing 20-day, same-day and forward 5 / 20-day returns, and between indicators.
    Rank correlation: counts are skewed (quiet days near 0, panics in the hundreds)."""
    fr = forward_returns(prices)
    fr["r0"] = (fr["close"] / fr["close"].shift(1) - 1) * 100
    fr["p20"] = (fr["close"] / fr["close"].shift(20) - 1) * 100
    df = ind.merge(fr[["date", *RET_COLS]], on="date", how="left").sort_values("date")
    sc = health_score(ind, cols)
    df["score"] = df["date"].map(sc)
    if days:
        df = df.tail(days)
    score = [[str(d), round(float(v), 1)] for d, v in zip(df["date"], df["score"]) if not pd.isna(v)]
    cols = [c for c in ["score", *cols] if c in df and df[c].notna().sum() >= 10]
    stats = []
    for c in cols:
        s = df[c].dropna()
        last = float(s.iloc[-1])
        stats.append({"key": c, "last": last, "first": float(s.iloc[0]), "min": float(s.min()), "max": float(s.max()),
                      "mean": float(s.mean()), "pctile": float((s <= last).mean() * 100)})
    m = df[cols + list(RET_COLS)].astype(float)
    vs = m.corr(method="spearman", min_periods=20).loc[cols, list(RET_COLS)]
    cc = m[cols].corr(method="spearman", min_periods=20)
    mat = lambda x: [[None if pd.isna(v) else round(float(v), 2) for v in row] for row in x.to_numpy()]  # noqa: E731
    return {"range": [str(df["date"].iloc[0]), str(df["date"].iloc[-1])] if len(df) else [], "n": len(df), "stats": stats, "score": score,
            "vs_returns": {"rows": cols, "cols": list(RET_COLS.values()), "matrix": mat(vs)},
            "between": {"rows": cols, "matrix": mat(cc)}}


# Indicators whose higher value means a weaker market (inverted in the health score).
WEAK = {"bear", "down4", "quarter_down25", "month_down25", "month_down50", "day34_down13"}
SCORE_WIN = 252


def health_score(ind: pd.DataFrame, cols: list[str], win: int = SCORE_WIN) -> pd.Series:
    """0-100 market health per date: the mean over indicators of each one's percentile within its own
    trailing `win` sessions (weak-side indicators inverted). 50 = an ordinary day for this market.
    Trailing only, so a past score used only data known on that date."""
    df = ind.sort_values("date").set_index("date")
    pct = []
    for c in cols:
        if c not in df or df[c].notna().sum() < 60:
            continue
        p = df[c].rolling(win, min_periods=60).rank(pct=True) * 100
        pct.append(100 - p if c in WEAK else p)
    return pd.concat(pct, axis=1).mean(axis=1).rename("score") if pct else pd.Series(dtype=float, name="score")


LAGS = range(-20, 21)
ROLL = 60


def lead_lag(ind: pd.DataFrame, prices: pd.DataFrame, col: str, days: int | None = None) -> dict:
    """Spearman correlation of the indicator on day t with the benchmark's 5-session return ending at
    t+k, for k = -20..20 (k <= 0: the move that already happened, k >= 5: entirely after t), and the
    trailing ROLL-session (Pearson) correlation with the same-day and next-20-day return over time."""
    fr = forward_returns(prices).set_index("date")
    r5 = (fr["close"] / fr["close"].shift(5) - 1) * 100
    df = ind.set_index("date")[[col]].join(fr[["close", "r20"]], how="inner").sort_index()
    df["r0"] = (df["close"] / df["close"].shift(1) - 1) * 100
    df = df.join(r5.rename("r5b"))
    if days:
        df = df.tail(days)
    x = df[col]
    lag = []
    for k in LAGS:
        y = df["r5b"].shift(-k)
        both = pd.concat([x, y], axis=1).dropna()
        lag.append(None if len(both) < 30 else round(float(both.iloc[:, 0].rank().corr(both.iloc[:, 1].rank())), 3))
    roll = {c: x.rolling(ROLL, min_periods=ROLL).corr(df[c]) for c in ("r0", "r20")}
    best = max((i for i, v in enumerate(lag) if v is not None), key=lambda i: abs(lag[i]), default=None)
    return {"metric": col, "n": int(x.notna().sum()), "lags": list(LAGS), "corr": lag,
            "peak": None if best is None else {"lag": LAGS[best], "corr": lag[best]},
            "dates": [str(d) for d in df.index], "roll": {c: [None if pd.isna(v) else round(float(v), 3) for v in s] for c, s in roll.items()},
            "window": ROLL}
