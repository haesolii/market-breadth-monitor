"""Crypto universe: every Binance spot USDT pair, including delisted ("BREAK") pairs,
whose daily klines stay downloadable -> far less survivorship bias than a current
top-N list. Excluded: stablecoins / fiat, tokenized stocks (bStocks) and gold
(tCommodities) by Binance's own tags, wrapped / staked copies by name, and for
delisted pairs (no names or tags) leveraged tokens and old stablecoins by symbol.
Bars: daily UTC klines (00:00-24:00) from the public market-data mirror, which
(unlike api.binance.com) also answers from US servers such as GitHub Actions.
Volume = base-asset units, so AVGC20 * AVGV20 is the USDT turnover."""
import concurrent.futures as cf
import datetime as dt
import re

import pandas as pd

from . import http_session

API = "https://data-api.binance.vision/api/v3/"
PRODUCTS = "https://www.binance.com/bapi/asset/v2/public/asset-service/product/get-products"
EXCLUDE_TAGS = {"stablecoin": "stablecoin", "bStocks": "tokenized stock", "tCommodities": "tokenized commodity"}
EXCLUDE_NAME = re.compile(r"wrapped|staked|^euro$", re.I)
EXCLUDE_DELISTED = re.compile(r"(?:UP|DOWN|BULL|BEAR)$|USD|EUR|KRW|^(?:GBP|AUD|BRL|TRY|DAI|PAX|UST|BETH)$")


def universe() -> pd.DataFrame:
    s = http_session()
    r = s.get(API + "exchangeInfo", params={"permissions": "SPOT"}, timeout=60)
    r.raise_for_status()
    pairs = [x for x in r.json()["symbols"] if x["quoteAsset"] == "USDT" and x["status"] in ("TRADING", "BREAK")]
    r = s.get(PRODUCTS, params={"includeEtf": "true"}, timeout=60)
    r.raise_for_status()
    prod = {x["s"]: x for x in r.json()["data"]}
    rows = []
    for x in pairs:
        p = prod.get(x["symbol"]) or {}
        tags = p.get("tags") or []
        name = p.get("an") or x["baseAsset"]
        listed = x["status"] == "TRADING"
        reason = next((v for k, v in EXCLUDE_TAGS.items() if k in tags), "")
        if not reason and EXCLUDE_NAME.search(name):
            reason = "wrapped / staked / fiat"
        if not reason and not listed and EXCLUDE_DELISTED.search(x["baseAsset"]):
            reason = "delisted leveraged token / stablecoin"
        rows.append({"ticker": x["baseAsset"], "name": name, "exchange": "BINANCE", "yahoo": x["symbol"],
                     "excluded_reason": reason, "listed": listed})
    u = pd.DataFrame(rows)
    if u["listed"].sum() < 100:
        raise RuntimeError(f"Binance: only {u['listed'].sum()} USDT pairs trading")
    return u.drop_duplicates("ticker").reset_index(drop=True)


def _klines(s, symbol: str, start_ms: int) -> pd.DataFrame:
    rows = []
    while True:
        r = s.get(API + "klines", params={"symbol": symbol, "interval": "1d", "startTime": start_ms, "limit": 1000}, timeout=30)
        r.raise_for_status()
        page = r.json()
        rows += page
        if len(page) < 1000:
            break
        start_ms = page[-1][0] + 1
    return pd.DataFrame({"date": [dt.datetime.fromtimestamp(k[0] / 1000, dt.timezone.utc).date() for k in rows],
                         "close": [float(k[4]) for k in rows], "volume": [float(k[5]) for k in rows]})


def fetch(symbols: dict[str, str], range_: str, workers: int = 8):
    """Same contract as yahoo.fetch: ticker -> pair; range_ '1mo' or 'Ny'. No splits on crypto."""
    days = 31 if range_ == "1mo" else int(range_.rstrip("y")) * 366
    start_ms = int((dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).timestamp() * 1000)
    s = http_session(pool=workers)
    frames, failed = [], []

    def one(item):
        t, sym = item
        try:
            return t, _klines(s, sym, start_ms), None
        except Exception as e:  # noqa: BLE001 - record and continue
            return t, None, str(e)

    with cf.ThreadPoolExecutor(workers) as ex:
        for t, df, err in ex.map(one, symbols.items()):
            if err:
                failed.append((t, err))
            elif len(df):
                df.insert(1, "ticker", t)
                frames.append(df)
    bars = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["date", "ticker", "close", "volume"])
    return bars, [], failed
