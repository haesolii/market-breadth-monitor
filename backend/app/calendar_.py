"""Event calendar: what is scheduled next.

  econ_calendar — US macro release dates: BEA schedule (GDP, PCE / personal income, trade ...) and
                  FOMC decisions (federalreserve.gov), both keyless; CPI / jobs / PPI / retail sales /
                  JOLTS from FRED's release calendar when FRED_API_KEY is set (BLS blocks scripts).
  kr_ir         — Korean IR meetings announced on DART (기업설명회(IR)개최): date / time and the
                  stated topic, read from each filing's document; most large caps hold one on the
                  day they report quarterly results (earnings = topic mentions 실적).
US earnings dates come from the earnings table (app.earnings).
"""
import datetime as dt
import html as htmllib
import io
import re
import zipfile

import pandas as pd

from . import store, watch
from .collectors import http_session
from .config import DART_API_KEY, FRED_API_KEY

BEA = "https://www.bea.gov/news/schedule"
FOMC = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
FRED = "https://api.stlouisfed.org/fred/release/dates"
DART_LIST = "https://opendart.fss.or.kr/api/list.json"
DART_DOC = "https://opendart.fss.or.kr/api/document.xml"
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
FRED_RELEASES = {10: "CPI (소비자물가)", 50: "고용보고서 (비농업 고용)", 46: "PPI (생산자물가)", 9: "소매판매", 192: "JOLTS (구인)"}
BEA_KO = [("GDP (", "GDP"), ("Personal Income and Outlays", "개인소득·소비 (PCE 물가)"), ("U.S. International Trade in Goods and Services", "무역수지")]
IR_DAYS = 45
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september",
                                       "october", "november", "december"], 1)}


def _text(h: str) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", h))).strip()


def parse_bea(page: str) -> list[dict]:
    out = []
    for table in re.findall(r"<table.*?</table>", page, flags=re.S):
        year = re.search(r"Year (\d{4})", table)
        if not year:
            continue
        for row in re.findall(r"<tr class=\"scheduled-releases-type.*?</tr>", table, flags=re.S):
            date = re.search(r'release-date">([A-Za-z]+) (\d+)<', row)
            if not date or date.group(1).lower() not in MONTHS:
                continue
            tm = re.search(r"<small[^>]*>([^<]+)</small>", row)
            title = _text(re.search(r'release-title[^>]*>(.*?)</td>', row, flags=re.S).group(1))
            ko = next((k for e, k in BEA_KO if title.startswith(e)), None)
            if ko:
                out.append({"date": dt.date(int(year.group(1)), MONTHS[date.group(1).lower()], int(date.group(2))),
                            "time": (tm.group(1).strip() + " ET") if tm else "", "kind": "매크로", "title": ko, "detail": title})
    return out


def parse_fomc(page: str) -> list[dict]:
    out = []
    for year, body in re.findall(r"(\d{4}) FOMC Meetings</a></h4>(.*?)(?=\d{4} FOMC Meetings</a></h4>|$)", page, flags=re.S):
        for month, days in re.findall(r'fomc-meeting__month[^>]*><strong>([^<]+)</strong>.*?fomc-meeting__date[^>]*>([^<]+)<', body, flags=re.S):
            last_month = month.split("/")[-1].strip().lower()
            day = re.findall(r"\d+", days)
            mo = next((v for k, v in MONTHS.items() if k.startswith(last_month[:3])), None)
            if not day or not mo:
                continue
            sep = "*" in days
            out.append({"date": dt.date(int(year), mo, int(day[-1])), "time": "2:00 PM ET", "kind": "FOMC",
                        "title": "FOMC 금리 결정" + (" (경제전망 발표)" if sep else ""), "detail": f"{month} {days.strip()}"})
    return out


def fred_dates(s, today: dt.date) -> list[dict]:
    out = []
    for rid, name in FRED_RELEASES.items():
        r = s.get(FRED, params={"release_id": rid, "api_key": FRED_API_KEY, "file_type": "json", "realtime_start": str(today - dt.timedelta(days=7)),
                                "include_release_dates_with_no_data": "true", "sort_order": "asc", "limit": 20}, timeout=30)
        r.raise_for_status()
        out += [{"date": dt.date.fromisoformat(x["date"]), "time": "8:30 AM ET" if rid != 192 else "10:00 AM ET", "kind": "매크로",
                 "title": name, "detail": "FRED release calendar"} for x in r.json().get("release_dates", [])]
    return out


def parse_ir(doc: str) -> dict:
    """Two DART forms: "1. 일시 및 장소 일시 2026-10-30 15:30 ..." (KOSPI) and "1. 일시 행사일 ... 시작일 종료일 시작시간
    종료시간 2026-10-20 2026-10-20 14:00 15:00 ..." (KOSDAQ). Never the later "IR 자료 게재일시"."""
    t = _text(doc)
    m = (re.search(r"1\.\s*일시\s*행사일.*?종료시간\s*(\d{4})-(\d{1,2})-(\d{1,2})\s*\d{4}-\d{1,2}-\d{1,2}\s*(\d{1,2}:\d{2})?", t)
         or re.search(r"1\.\s*일시\s*(?:및\s*장소\s*)?(?:일시\s*)?(\d{4})[-.](\d{1,2})[-.](\d{1,2})\s*(\d{1,2}:\d{2})?", t))
    topic = re.search(r"주요\s*(?:설명회\s*)?내용\s*(?:\(요약\))?\s*(.*?)\s*\d+\.\s*(?:결정일자|후원기관|개최확정일)", t)
    purpose = re.search(r"(?:개최|실시)\s*목적\s*(.*?)\s*\d+\.\s*(?:개최|실시)\s*방법", t)
    texts = [g.group(1).strip() for g in (topic, purpose) if g and g.group(1).strip() not in ("", "-")]
    return {"ir_date": dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None,
            "ir_time": (m.group(4) or "") if m else "", "summary": (texts[0] if texts else "")[:120], "earnings": "실적" in " ".join(texts)}


def fetch_ir(s, known: set[str], today: dt.date) -> pd.DataFrame:
    rows = []
    for page in range(1, 60):
        r = s.get(DART_LIST, params={"crtfc_key": DART_API_KEY, "bgn_de": (today - dt.timedelta(days=IR_DAYS)).strftime("%Y%m%d"),
                                     "end_de": today.strftime("%Y%m%d"), "pblntf_ty": "I", "page_no": page, "page_count": 100}, timeout=30)
        r.raise_for_status()
        j = r.json()
        if j.get("status") == "013":
            break
        if j.get("status") != "000":
            raise RuntimeError(f"DART {j.get('status')}: {j.get('message')}")
        for x in j["list"]:
            if "기업설명회" not in x["report_nm"] or x.get("corp_cls") not in ("Y", "K") or x["rcept_no"] in known:  # KOSPI / KOSDAQ only
                continue
            d = s.get(DART_DOC, params={"crtfc_key": DART_API_KEY, "rcept_no": x["rcept_no"]}, timeout=30)
            try:
                z = zipfile.ZipFile(io.BytesIO(d.content))
                info = parse_ir(z.read(z.namelist()[0]).decode("utf-8", "ignore"))
            except (zipfile.BadZipFile, IndexError):
                continue
            if info["ir_date"]:
                rows.append({"rcept_no": x["rcept_no"], "filed": dt.datetime.strptime(x["rcept_dt"], "%Y%m%d").date(), "code": x["stock_code"],
                             "name": x["corp_name"], "market": {"Y": "kospi", "K": "kosdaq"}.get(x.get("corp_cls"), ""), **info})
        if page >= int(j.get("total_page") or 1):
            break
    return pd.DataFrame(rows)


def refresh() -> dict:
    s = http_session()
    s.headers["User-Agent"] = BROWSER_UA
    today = dt.date.today()
    ev, errors = [], []
    for name, fn in (("BEA", lambda: parse_bea(s.get(BEA, timeout=30).text)), ("FOMC", lambda: parse_fomc(s.get(FOMC, timeout=30).text)),
                     *((("FRED", lambda: fred_dates(s, today)),) if FRED_API_KEY else ())):
        try:
            got = fn()
            if not got:
                raise RuntimeError("no dates parsed")
            ev += got
        except Exception as e:  # noqa: BLE001 - one source failing keeps the others
            errors.append(f"{name}: {e}")
    old = store.read("econ_calendar")
    if ev:
        new = pd.DataFrame(ev)
        keep = old[~old["title"].isin(set(new["title"]))] if len(old) else old  # a failed source keeps its old rows
        store.write("econ_calendar", pd.concat([keep, new], ignore_index=True).drop_duplicates(["date", "title"]).sort_values("date"))
    ir = store.read("kr_ir")
    if DART_API_KEY:
        try:
            new_ir = fetch_ir(s, set(ir["rcept_no"]) if len(ir) else set(), today)
            ir = pd.concat([ir, new_ir], ignore_index=True).drop_duplicates("rcept_no", keep="last") if len(new_ir) else ir
            if len(ir):
                ir = ir[pd.to_datetime(ir["ir_date"]).dt.date >= today - dt.timedelta(days=120)]
                store.write("kr_ir", ir.sort_values("ir_date").reset_index(drop=True))
        except Exception as e:  # noqa: BLE001
            errors.append(f"DART IR: {e}")
    if not ev and not len(ir):
        raise RuntimeError("; ".join(errors) or "no calendar data")
    if errors:
        store.log("warn", "calendar", "; ".join(errors))
    return {"latest_date": str(today), "macro": len(ev), "kr_ir": len(ir), "errors": errors}


def view(back: int = 3, ahead: int = 30, min_cap: float = 5e10) -> dict:
    today = dt.date.today()
    lo, hi = today - dt.timedelta(days=back), today + dt.timedelta(days=ahead)
    mine = {(w["ticker"]) for w in watch.load()}
    rows = []
    ec = store.read("econ_calendar")
    for r in ec.to_dict("records") if len(ec) else []:
        if lo <= pd.to_datetime(r["date"]).date() <= hi:
            rows.append({**r, "date": str(pd.to_datetime(r["date"]).date()), "ticker": None, "market": "us"})
    e = store.read("earnings")
    if len(e):
        e = e[(pd.to_datetime(e["date"]).dt.date >= lo) & (pd.to_datetime(e["date"]).dt.date <= hi)]
        e = e[(e["mcap"] >= min_cap) | e["symbol"].isin(mine)]
        for r in e.itertuples():
            done = pd.notna(r.eps)
            detail = (f"EPS {r.eps:.2f} vs 예상 {r.eps_forecast:.2f}" + ("" if pd.isna(r.react) else f" · 반응 {r.react:+.1f}%")) if done and pd.notna(r.eps_forecast) \
                else ("" if pd.isna(r.eps_forecast) else f"예상 EPS {r.eps_forecast:.2f}")
            rows.append({"date": str(pd.to_datetime(r.date).date()), "time": {"pre": "장전", "after": "장후"}.get(r.time, ""), "kind": "미국 실적",
                         "title": f"{r.name} ({r.symbol})", "detail": detail, "ticker": r.symbol, "market": "yahoo", "mcap": float(r.mcap) if pd.notna(r.mcap) else None})
    ir = store.read("kr_ir")
    if len(ir):
        ir = ir[(pd.to_datetime(ir["ir_date"]).dt.date >= lo) & (pd.to_datetime(ir["ir_date"]).dt.date <= hi)]
        ir = ir.sort_values("rcept_no").drop_duplicates(["code", "ir_date"], keep="last")  # corrections re-announce the same meeting
        for r in ir.itertuples():
            rows.append({"date": str(pd.to_datetime(r.ir_date).date()), "time": r.ir_time, "kind": "한국 실적 IR" if r.earnings else "한국 IR",
                         "title": f"{r.name} ({r.code})", "detail": r.summary, "ticker": r.code, "market": r.market})
    for r in rows:
        r["watch"] = r.get("ticker") in mine
    return {"today": str(today), "fred": bool(FRED_API_KEY or (len(ec) and ec["detail"].eq("FRED release calendar").any())),
            "rows": sorted(rows, key=lambda r: (r["date"], r["kind"] != "FOMC", r["kind"] != "매크로", -(r.get("mcap") or 0)))}
