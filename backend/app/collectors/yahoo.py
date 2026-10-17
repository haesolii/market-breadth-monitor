"""Source "yahoo": free, keyless per-ticker daily bars.

Universe = NASDAQ Trader symbol directory (all NASDAQ / NYSE / NYSE American /
NYSE Arca / Cboe BZX / IEX listings), minus ETFs, test issues and names that
look like non-common securities. Yahoo `close` is split-adjusted (NOT dividend
adjusted, like TC2000 price charts); volume is split-adjusted by Yahoo.

Known limitation: the directory lists only CURRENTLY listed symbols, so history
is survivorship-biased (delisted names are missing unless we stored them while
they were still listed). This is surfaced in the UI and docs.
"""
import concurrent.futures as cf
import datetime as dt
import io
import re

import pandas as pd

from . import http_session

DIR = "https://www.nasdaqtrader.com/dynamic/symdir/"
OTHER_EXCH = {"N": "NYSE", "A": "NYSE American", "P": "NYSE Arca", "Z": "Cboe BZX", "V": "IEX"}
EXCLUDE_NAME = re.compile(
    r"warrant|\bright|\bunits?\b|preferred|depositary|\bADSs?\b|\bADR|\bnotes?\b|debenture|"
    r"\betf\b|\betn\b|\bfund\b|%|subordinated|\bbond|trust preferred|beneficial interest|"
    r"\bperpetual|\bseries [a-z]\b.*(?:pfd|cum)", re.I)
EXCLUDE_SYMBOL = re.compile(r"[\$\^~]|\.(?:W|WS|U|R|RT|WI)$|\.P")


def _read(s, name: str) -> pd.DataFrame:
    r = s.get(DIR + name, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text), sep="|", dtype=str, keep_default_na=False)
    return df[~df.iloc[:, 0].str.startswith("File Creation")]


def universe() -> pd.DataFrame:
    """Return (ticker, name, exchange, yahoo, excluded_reason) for every listed symbol."""
    s = http_session()
    nq = _read(s, "nasdaqlisted.txt")
    ot = _read(s, "otherlisted.txt")
    a = pd.DataFrame({"ticker": nq["Symbol"], "name": nq["Security Name"], "exchange": "NASDAQ",
                      "etf": nq["ETF"], "test": nq["Test Issue"]})
    b = pd.DataFrame({"ticker": ot["ACT Symbol"], "name": ot["Security Name"],
                      "exchange": ot["Exchange"].map(OTHER_EXCH).fillna(ot["Exchange"]),
                      "etf": ot["ETF"], "test": ot["Test Issue"]})
    u = pd.concat([a, b], ignore_index=True)
    reason = pd.Series("", index=u.index)
    reason[u["etf"] == "Y"] = "ETF"
    reason[(reason == "") & (u["test"] == "Y")] = "test issue"
    reason[(reason == "") & u["ticker"].str.contains(EXCLUDE_SYMBOL)] = "symbol suffix (pref/warrant/unit/right)"
    reason[(reason == "") & u["name"].str.contains(EXCLUDE_NAME)] = "name pattern (non-common)"
    reason[(reason == "") & ~u["exchange"].isin(list(OTHER_EXCH.values()) + ["NASDAQ"])] = "exchange"
    u["excluded_reason"] = reason
    u["name"] = u["name"].str.replace(r"\s*-?\s*(Class [A-C] )?(Common Stock|Ordinary Shares?)\s*$", r" \1",
                                      regex=True, flags=re.I).str.strip()
    u["yahoo"] = u["ticker"].str.replace(".", "-", regex=False)
    return u.drop(columns=["etf", "test"]).drop_duplicates("ticker").reset_index(drop=True)


def _chart(s, symbol: str, range_: str):
    r = s.get(f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}",
              params={**({"period1": 946684800, "period2": int(dt.datetime.now().timestamp())} if range_ == "max" else {"range": range_}),
                      "interval": "1d", "events": "split"}, timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    res = (r.json().get("chart") or {}).get("result")
    if not res or not res[0].get("timestamp"):
        return None
    res = res[0]
    off = res["meta"].get("gmtoffset", -18000)
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame({
        "date": [dt.datetime.fromtimestamp(t + off, dt.timezone.utc).date() for t in res["timestamp"]],
        "close": q.get("close"), "volume": q.get("volume")})
    df = df.dropna(subset=["close"])
    df["volume"] = df["volume"].fillna(0)
    splits = list((res.get("events") or {}).get("splits", {}).values())
    return df.drop_duplicates("date", keep="last"), bool(splits)


def fetch(symbols: dict[str, str], range_: str, workers: int = 12):
    """symbols: ticker -> yahoo symbol. Returns (bars, tickers_with_splits, failed)."""
    s = http_session(pool=workers)
    frames, split_tickers, failed = [], [], []

    def one(item):
        t, y = item
        try:
            return t, _chart(s, y, range_), None
        except Exception as e:  # noqa: BLE001 - record and continue
            return t, None, str(e)

    with cf.ThreadPoolExecutor(workers) as ex:
        for t, res, err in ex.map(one, symbols.items()):
            if err:
                failed.append((t, err))
            elif res is not None:
                df, has_split = res
                df.insert(1, "ticker", t)
                frames.append(df)
                if has_split:
                    split_tickers.append(t)
    bars = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["date", "ticker", "close", "volume"])
    return bars, split_tickers, failed

