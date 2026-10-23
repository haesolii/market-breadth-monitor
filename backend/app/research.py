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
