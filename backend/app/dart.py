"""Korean preliminary earnings (영업(잠정)실적 공정공시) from DART, with the stock's reaction.

DART's list API gives the filing (company, title, date, receipt no.) but not the figures — the
numbers live in the filing document, linked from each row. Needs DART_API_KEY (free).
Reaction: the filing time is not in the list, so the move is measured over two sessions — close of
the first session after the filing date vs the close before it — like an unknown-time US report.
"""
import datetime as dt

import pandas as pd

from . import store
from .analyst import _kr_bars, _rows
from .collectors import http_session
from .config import DART_API_KEY

API = "https://opendart.fss.or.kr/api/list.json"
VIEW = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="
BACKFILL_DAYS = 120
REFETCH_DAYS = 3
MARKET = {"Y": "kospi", "K": "kosdaq"}


def is_prelim(title: str) -> bool:
    return "잠정" in title and "실적" in title


# Major disclosures worth a line in the feed: (category, words in the title); first match wins.
EVENTS = [("유상증자", ("유상증자",)), ("무상증자", ("무상증자",)), ("자사주 소각", ("주식소각",)),
          ("자사주 매입", ("자기주식취득", "자기주식 취득")), ("자사주 처분", ("자기주식처분", "자기주식 처분")),
          ("최대주주 변경", ("최대주주변경", "최대주주 변경")), ("공급계약·수주", ("단일판매", "공급계약")),
          ("CB·BW 발행", ("전환사채권발행", "신주인수권부사채권발행", "교환사채권발행")), ("합병·분할", ("합병", "분할")),
          ("감자", ("감자",)), ("공개매수", ("공개매수",)), ("소송", ("소송",)), ("거래정지·위험", ("거래정지", "횡령", "배임", "관리종목", "상장폐지"))]
EVENT_DAYS = 30
COLS = ["rcept_no", "date", "code", "name", "market", "title"]


def category(title: str) -> str | None:
    t = title.replace(" ", "")
    return next((c for c, words in EVENTS if any(w.replace(" ", "") in t for w in words)), None)


def fetch(since: dt.date, until: dt.date) -> pd.DataFrame:
    """KOSPI / KOSDAQ filings that are preliminary results or a major EVENTS category, from the exchange
    (I) and major-matter (B) disclosure lists."""
    s = http_session()
    rows = []
    for kind in ("I", "B"):
        for page in range(1, 300):
            r = s.get(API, params={"crtfc_key": DART_API_KEY, "bgn_de": since.strftime("%Y%m%d"), "end_de": until.strftime("%Y%m%d"),
                                   "pblntf_ty": kind, "page_no": page, "page_count": 100}, timeout=30)
            r.raise_for_status()
            j = r.json()
            if j.get("status") == "013":  # no filings in the range
                break
            if j.get("status") != "000":
                raise RuntimeError(f"DART {j.get('status')}: {j.get('message')}")
            rows += [{"rcept_no": x["rcept_no"], "date": dt.datetime.strptime(x["rcept_dt"], "%Y%m%d").date(), "code": x.get("stock_code") or "",
                      "name": x["corp_name"], "market": MARKET.get(x.get("corp_cls"), ""), "title": " ".join(x["report_nm"].split())}
                     for x in j["list"] if x.get("stock_code") and x.get("corp_cls") in MARKET
                     and (is_prelim(x["report_nm"]) or category(x["report_nm"]))]
            if page >= int(j.get("total_page") or 1):
                break
    return pd.DataFrame(rows, columns=COLS).drop_duplicates("rcept_no")


def react(df: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in ("react", "ret_since"):
        df[c] = float("nan")
    b = bars.sort_values(["ticker", "date"])
    for code, g in df.groupby("code"):
        px = b[b["ticker"] == code]
        if px.empty:
            continue
        d, c = px["date"].to_numpy(), px["close"].to_numpy()
        dates = g["date"].to_numpy()
        i_pre = d.searchsorted(dates, side="left") - 1     # last session before the filing date
        i_post = d.searchsorted(dates, side="right")       # first session after it
        pre = pd.Series(c[i_pre.clip(0)], index=g.index).where(i_pre >= 0)
        post = pd.Series(c[i_post.clip(max=len(c) - 1)], index=g.index).where(i_post < len(c))
        df.loc[g.index, "react"] = (post / pre - 1) * 100
        df.loc[g.index, "ret_since"] = (c[-1] / pre - 1) * 100
    return df


def refresh() -> dict:
    if not DART_API_KEY:
        raise RuntimeError("DART_API_KEY is not set")
    old, old_ev = store.read("dart_prelim"), store.read("dart_events")
    today = dt.date.today()
    since_p = today - dt.timedelta(days=REFETCH_DAYS if len(old) else BACKFILL_DAYS)
    since_e = today - dt.timedelta(days=REFETCH_DAYS if len(old_ev) else EVENT_DAYS)
    since = min(since_p, since_e)
    frames = []
    while since <= today:  # the API serves at most 3 months per request
        until = min(today, since + dt.timedelta(days=85))
        frames.append(fetch(since, until))
        since = until + dt.timedelta(days=1)
    new = pd.concat(frames, ignore_index=True)
    prelim = new[new["title"].map(is_prelim) & (new["date"] >= since_p)]
    events = new[~new["title"].map(is_prelim) & (new["date"] >= since_e)].assign(category=lambda d: d["title"].map(category))
    out = _merge("dart_prelim", old, prelim, COLS)
    ev = _merge("dart_events", old_ev, events, [*COLS, "category"], keep_days=180)
    return {"latest_date": str(out["date"].max()) if len(out) else None, "filings": len(out), "events": len(ev)}


def _merge(table: str, old: pd.DataFrame, new: pd.DataFrame, cols: list[str], keep_days: int | None = None) -> pd.DataFrame:
    raw = pd.concat([old[cols] if len(old) else None, new[cols]], ignore_index=True).drop_duplicates("rcept_no", keep="last")
    if raw.empty:
        return raw
    raw["date"] = pd.to_datetime(raw["date"]).dt.date
    if keep_days:
        raw = raw[raw["date"] >= dt.date.today() - dt.timedelta(days=keep_days)]
    out = react(raw, _kr_bars(set(raw["code"]), min(raw["date"]) - dt.timedelta(days=10)))
    store.write(table, out.sort_values(["date", "rcept_no"], ascending=False).reset_index(drop=True))
    return out


def collapse(df: pd.DataFrame) -> pd.DataFrame:
    """One row per company per day: a company often files the consolidated and separate results, a
    subsidiary's results and corrections ([기재정정] / [첨부추가]) together. Main row = the company's own
    consolidated original; the rest are counted (extra) and flagged (correction / subsidiary)."""
    if df.empty:
        return df.assign(extra=0, correction=False, subsidiary=False)
    df = df.assign(correction=df["title"].str.startswith("["), subsidiary=df["title"].str.contains("자회사", regex=False))
    df["_rank"] = df["correction"] * 4 + df["subsidiary"] * 2 + ~df["title"].str.startswith("연결")
    g = df.sort_values("_rank").groupby(["code", "date"], sort=False)
    out = g.head(1).set_index(["code", "date"])
    out["extra"] = g.size() - 1
    out["correction"], out["subsidiary"] = g["correction"].any(), g["subsidiary"].any()
    return out.reset_index().drop(columns="_rank").sort_values(["date", "rcept_no"], ascending=False)


def events(days: int = 14, category_: str = "") -> list[dict]:
    df = store.read("dart_events")
    if df.empty:
        return []
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df[df["date"] >= dt.date.today() - dt.timedelta(days=days)]
    if category_:
        df = df[df["category"] == category_]
    return [{**r, "url": VIEW + r["rcept_no"]} for r in _rows(df.sort_values(["date", "rcept_no"], ascending=False))]


def view(days: int = 30, code: str = "") -> list[dict]:
    df = store.read("dart_prelim")
    if df.empty:
        return []
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df[df["code"] == code] if code else df[df["date"] >= dt.date.today() - dt.timedelta(days=days)]
    return [{**r, "url": VIEW + r["rcept_no"]} for r in _rows(collapse(df))]
