"""Source "public_repo": published 20% bull/bear series from
github.com/georggatchev87/market-breadth (computed from Massive grouped-daily
bars, CS on NYSE/NASDAQ/AMEX/Arca/BATS incl. delisted). Counts only, no tickers.
The repo has no LICENSE file: we only download its published JSON for personal
use and do not redistribute its code."""
import pandas as pd

from . import http_session

BASE = "https://raw.githubusercontent.com/georggatchev87/market-breadth/main/"


def _series(s, name: str, col: str) -> pd.DataFrame:
    r = s.get(BASE + name, timeout=30)
    r.raise_for_status()
    rows = r.json()
    if not isinstance(rows, list) or not rows or not {"date", "value"} <= set(rows[0]):
        raise ValueError(f"{name}: unexpected schema")
    df = pd.DataFrame(rows)[["date", "value"]].rename(columns={"value": col})
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d").dt.date
    if (df[col] < 0).any() or df["date"].duplicated().any():
        raise ValueError(f"{name}: negative values or duplicate dates")
    return df


def fetch() -> tuple[pd.DataFrame, dict]:
    s = http_session()
    up = _series(s, "breadth_5d_up20.json", "bull")
    down = _series(s, "breadth_5d_down20.json", "bear")
    status = s.get(BASE + "status.json", timeout=30).json()
    df = up.merge(down, on="date", how="inner")
    # Upstream writes a provisional intraday row; keep only finalized sessions.
    if status.get("state") != "final" and status.get("date"):
        df = df[df["date"].astype(str) != status["date"]]
    return df.sort_values("date").reset_index(drop=True), status
