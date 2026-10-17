"""KOSPI / KOSDAQ universe from KRX KIND "상장법인목록" (listed companies; one row
per company = its common share, so preferred shares, ETFs/ETNs and REIT funds
not registered as companies are absent). Prices come from Yahoo (.KS / .KQ).
Like the US Yahoo source, this is the CURRENT listing -> survivorship-biased history."""
import html
import re

import pandas as pd

from . import http_session

KIND = "https://kind.krx.co.kr/corpgeneral/corpList.do"
MARKET = {"kospi": ("stockMkt", "KOSPI", ".KS"), "kosdaq": ("kosdaqMkt", "KOSDAQ", ".KQ")}
_ROW = re.compile(r"<tr>(.*?)</tr>", re.S)
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S)


def parse(text: str) -> pd.DataFrame:
    rows = []
    for tr in _ROW.findall(text):
        tds = [html.unescape(re.sub(r"<[^>]+>|\s+", " ", td)).strip() for td in _TD.findall(tr)]
        if len(tds) >= 4:
            rows.append({"name": tds[0], "market": tds[1], "ticker": tds[2], "industry": tds[3]})
    return pd.DataFrame(rows, columns=["name", "market", "ticker", "industry"])


def universe(market: str) -> pd.DataFrame:
    mt, label, suffix = MARKET[market]
    r = http_session().get(KIND, params={"method": "download", "marketType": mt}, timeout=60)
    r.raise_for_status()
    df = parse(r.content.decode("euc-kr", errors="replace"))
    if len(df) < 100:
        raise RuntimeError(f"KIND {market}: only {len(df)} rows parsed")
    df = df[df["ticker"].str.fullmatch(r"[0-9A-Z]{6}")].drop_duplicates("ticker")
    return pd.DataFrame({"ticker": df["ticker"], "name": df["name"], "exchange": label,
                         "yahoo": df["ticker"] + suffix, "excluded_reason": "",
                         "industry": df["industry"]}).reset_index(drop=True)
