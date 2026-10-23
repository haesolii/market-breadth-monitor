"""Headlines (personal dashboard only): fetched on request and kept CACHE_S seconds in memory.

  Korea  — Naver stock news (per stock) and Naver finance main news (market), unofficial endpoints
  US     — Google News RSS search ("<ticker> stock", "stock market")
Each item: time (KST), source, title, summary, url. Titles and links only point to the publisher;
the articles themselves are not stored. Not for a public / ad-supported page (publisher terms).
"""
import datetime as dt
import email.utils
import html
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

from .collectors import http_session

NAVER_STOCK = "https://m.stock.naver.com/api/news/stock/{code}"
NAVER_MAIN = "https://m.stock.naver.com/api/news/list"
GOOGLE = "https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={gl}:{lang}"
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
KST = dt.timezone(dt.timedelta(hours=9))
CACHE_S = 300
KR = ("kospi", "kosdaq")
_cache: dict[str, tuple[float, list[dict]]] = {}
_lock = threading.Lock()


def _cached(key: str, fn) -> list[dict]:
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_S:
        return hit[1]
    try:
        val = fn()
    except Exception:  # noqa: BLE001 - a news source being down must not break the page
        return hit[1] if hit else []
    with _lock:
        _cache[key] = (time.time(), val)
    return val


def _s():
    s = http_session()
    s.headers["User-Agent"] = BROWSER_UA
    return s


def _kst(stamp: str) -> str:
    """'YYYYMMDDHHMM[SS]' (KST) -> 'YYYY-MM-DD HH:MM'."""
    return f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]} {stamp[8:10]}:{stamp[10:12]}"


def _clean(t: str | None, n: int = 160) -> str:
    t = html.unescape(re.sub(r"<[^>]+>", "", t or "")).strip()
    return t[:n] + ("…" if len(t) > n else "")


def _thumb(u: str | None) -> str:
    """Naver image URL resized to a small thumbnail (the original can be megabytes)."""
    return f"{u.split('?')[0]}?type=nf220_150" if u and u.startswith("https://imgnews.pstatic.net/") else ""


def parse_naver_stock(groups: list[dict]) -> list[dict]:
    out = []
    for g in groups:
        for x in g.get("items") or []:
            out.append({"time": _kst(x["datetime"]), "source": x.get("officeName", ""), "title": _clean(x.get("titleFull") or x.get("title"), 200),
                        "summary": _clean(x.get("body")), "url": x.get("mobileNewsUrl") or f"https://n.news.naver.com/mnews/article/{x['officeId']}/{x['articleId']}",
                        "thumb": _thumb(x.get("imageOriginLink"))})
    return out


def parse_naver_main(items: list[dict]) -> list[dict]:
    return [{"time": _kst(x["dt"]), "source": x.get("ohnm", ""), "title": _clean(x.get("tit"), 200), "summary": _clean(x.get("subcontent")),
             "url": f"https://n.news.naver.com/mnews/article/{x['oid']}/{x['aid']}", "thumb": _thumb(x.get("thumbUrl"))} for x in items]


def parse_google(xml: str) -> list[dict]:
    out = []
    for it in re.findall(r"<item>(.*?)</item>", xml, flags=re.S):
        get = lambda tag: (re.search(f"<{tag}[^>]*>(.*?)</{tag}>", it, flags=re.S) or [None, ""])[1]  # noqa: E731
        title, source = html.unescape(get("title")), html.unescape(get("source"))
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3]
        when = email.utils.parsedate_to_datetime(get("pubDate")).astimezone(KST).strftime("%Y-%m-%d %H:%M") if get("pubDate") else ""
        out.append({"time": when, "source": source, "title": title, "summary": "", "url": html.unescape(get("link")), "thumb": ""})
    return out


def _google(q: str, lang: str = "en") -> list[dict]:
    hl, gl = ("ko", "KR") if lang == "ko" else ("en-US", "US")
    r = _s().get(GOOGLE.format(q=quote(q), hl=hl, gl=gl, lang=lang), timeout=15)
    r.raise_for_status()
    return parse_google(r.text)


def stock(ticker: str, market: str, name: str = "", n: int = 30) -> list[dict]:
    if market in KR:
        def fn():
            r = _s().get(NAVER_STOCK.format(code=ticker), params={"pageSize": n}, timeout=15)
            r.raise_for_status()
            return parse_naver_stock(r.json())
        return _cached(f"kr:{ticker}", fn)[:n]
    q = f"{ticker}-USD crypto when:7d" if market == "crypto" else f"{ticker} stock when:7d"
    return sorted(_cached(f"us:{q}", lambda: _google(q)), key=lambda x: x["time"], reverse=True)[:n]


def market(n: int = 40) -> dict:
    def kr():
        r = _s().get(NAVER_MAIN, params={"category": "mainnews", "pageSize": n, "page": 1}, timeout=15)
        r.raise_for_status()
        return parse_naver_main(r.json())
    us = lambda: sorted(_google("stock market when:1d"), key=lambda x: x["time"], reverse=True)  # noqa: E731
    return {"kr": _cached("kr:main", kr)[:n], "us": _cached("us:main", us)[:n]}


def watch(items: list[dict], per: int = 5) -> list[dict]:
    """The latest `per` headlines of every watchlist stock, newest first."""
    def one(it):
        return [{**x, "ticker": it["ticker"], "market": it.get("market"), "name": it.get("name") or it["ticker"]}
                for x in stock(it["ticker"], it.get("market", ""), it.get("name", ""), per)]
    with ThreadPoolExecutor(8) as ex:
        rows = [x for part in ex.map(one, items) for x in part]
    return sorted(rows, key=lambda x: x["time"], reverse=True)
