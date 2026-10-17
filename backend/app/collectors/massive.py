"""Source "massive": Massive.com (formerly Polygon.io) full-market daily bars.

- Bars: GET /v2/aggs/grouped/locale/us/market/stocks/{date}?adjusted=false
  (one call per session, cached forever under data/massive/). We fetch RAW bars
  and apply splits ourselves (GET /stocks/v1/splits) at compute time, so cached
  days never mix "adjusted as of different fetch dates".
- Universe: GET /v3/reference/tickers type=CS, active=true AND active=false
  (delisted included -> survivorship-free), primary exchange NYSE/NASDAQ/AMEX/Arca/BATS.
Requires MASSIVE_API_KEY. Free plan: 5 req/min, ~2 years of history.
"""
import datetime as dt
import threading
import time

import numpy as np
import pandas as pd

from .. import store
from ..config import DATA, MASSIVE_API_KEY, MASSIVE_RATE_PER_MIN
from . import http_session

API = "https://api.massive.com"
MIC_LABEL = {"XNYS": "NYSE", "XNAS": "NASDAQ", "XNGS": "NASDAQ", "XNMS": "NASDAQ", "XNCM": "NASDAQ",
             "XASE": "NYSE American", "ARCX": "NYSE Arca", "BATS": "Cboe BZX"}
CACHE = DATA / "massive"


class BeforeCoverage(Exception):
    pass


class Client:
    def __init__(self, key: str = MASSIVE_API_KEY, rate_per_min: float = MASSIVE_RATE_PER_MIN):
        if not key:
            raise RuntimeError("MASSIVE_API_KEY is not set")
        self.key, self.gap, self.s = key, 60.0 / rate_per_min, http_session()
        self._last, self._lock = 0.0, threading.Lock()

    def get(self, url: str, params: dict | None = None) -> dict:
        with self._lock:  # client-side rate limit
            wait = self._last + self.gap - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
        url = url if url.startswith("http") else API + url
        r = self.s.get(url, params={**(params or {}), "apiKey": self.key}, timeout=60)
        if r.status_code == 403:
            raise BeforeCoverage(r.text[:200])
        r.raise_for_status()
        return r.json()

    def paginate(self, path: str, params: dict) -> list[dict]:
        out, page = [], self.get(path, params)
        while True:
            out += page.get("results") or []
            nxt = page.get("next_url")
            if not nxt:
                return out
            page = self.get(nxt)


def universe(c: Client) -> pd.DataFrame:
    rows = []
    for active in ("true", "false"):
        rows += c.paginate("/v3/reference/tickers",
                           {"market": "stocks", "type": "CS", "active": active, "limit": 1000})
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["ticker", "name", "exchange", "active"])
    df = df[df["primary_exchange"].isin(MIC_LABEL)]
    df = df.assign(exchange=df["primary_exchange"].map(MIC_LABEL))
    # A reused ticker can appear active + inactive; prefer the active record.
    df = df.sort_values("active", ascending=False).drop_duplicates("ticker")
    return df[["ticker", "name", "exchange", "active"]].reset_index(drop=True)


def splits(c: Client, since: str) -> pd.DataFrame:
    rows = c.paginate("/stocks/v1/splits", {"execution_date.gte": since, "limit": 5000})
    df = pd.DataFrame(rows, columns=["ticker", "execution_date", "split_from", "split_to"])
    df["execution_date"] = pd.to_datetime(df["execution_date"]).dt.date
    return df.dropna()


def grouped(c: Client, date: dt.date) -> pd.DataFrame | None:
    """Raw bars for one session, from cache or API. None = no data (holiday)."""
    p = CACHE / f"{date}.parquet"
    if p.exists():
        return pd.read_parquet(p)
    js = c.get(f"/v2/aggs/grouped/locale/us/market/stocks/{date}", {"adjusted": "false"})
    res = js.get("results") or []
    if not res:
        return None
    df = pd.DataFrame(res).rename(columns={"T": "ticker", "c": "close", "v": "volume"})[["ticker", "close", "volume"]]
    df.insert(0, "date", date)
    CACHE.mkdir(exist_ok=True)
    df.to_parquet(p, index=False)
    return df


def adjust_for_splits(bars: pd.DataFrame, sp: pd.DataFrame) -> pd.DataFrame:
    """Back-adjust: for each split executed on E, bars dated < E get
    close * from/to and volume * to/from (TC2000-style split adjustment)."""
    if sp.empty:
        return bars
    sp = sp.assign(lr=np.log(sp["split_from"] / sp["split_to"]))
    f = store.sql("""
        SELECT b.ticker, b.date, exp(coalesce(sum(s.lr), 0)) AS f
        FROM (SELECT DISTINCT ticker, date FROM bars) b
        LEFT JOIN sp s ON s.ticker = b.ticker AND s.execution_date > b.date
        GROUP BY 1, 2""", bars=bars, sp=sp)
    f["date"] = pd.to_datetime(f["date"]).dt.date
    out = bars.merge(f, on=["ticker", "date"], how="left")
    out["close"] = out["close"] * out["f"]
    out["volume"] = out["volume"] / out["f"]
    return out.drop(columns="f")


def cached_bars() -> pd.DataFrame:
    files = sorted(CACHE.glob("*.parquet")) if CACHE.exists() else []
    if not files:
        return pd.DataFrame(columns=["date", "ticker", "close", "volume"])
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df
