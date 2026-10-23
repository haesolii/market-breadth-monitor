"""US macro dashboard data from FRED (St. Louis Fed), keyless CSV endpoint.

Raw observations are stored as-is (data/macro.parquet: series, date, value);
the display transform (level, year-over-year %, month-over-month change) and
the reference flags are computed on read. Values are FRED's latest vintage
(revisions overwrite earlier prints).
"""
import concurrent.futures as cf
import datetime as dt
import io

import pandas as pd
import requests

from . import store
from .collectors import http_session
from .market_calendar import ET

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"

# id: (name, group, transform, unit, good-direction)
#   transform: level | yoy (% vs 12 months / 52 weeks earlier) | mom (change vs prior obs) | scale:<k>
#   good: up | down | neutral  -> color of changes (e.g. unemployment rising = red)
SERIES = {
    "CPIAUCSL": ("CPI (전년 대비)", "물가", "yoy", "%", "down"),
    "CPILFESL": ("근원 CPI (전년 대비)", "물가", "yoy", "%", "down"),
    "PCEPILFE": ("근원 PCE (전년 대비)", "물가", "yoy", "%", "down"),
    "UNRATE": ("실업률", "고용", "level", "%", "down"),
    "PAYEMS": ("비농업 고용 (전월 대비)", "고용", "mom", "천 명", "up"),
    "ICSA": ("신규 실업수당 청구", "고용", "scale:0.001", "천 건", "down"),
    "SAHMREALTIME": ("삼 법칙 경기침체 지표", "고용", "level", "%p", "down"),
    "FEDFUNDS": ("연방기금금리", "금리·신용", "level", "%", "neutral"),
    "DGS2": ("미국 2년물 국채", "금리·신용", "level", "%", "neutral"),
    "DGS10": ("미국 10년물 국채", "금리·신용", "level", "%", "neutral"),
    "T10Y2Y": ("장단기 금리차 (10년−2년)", "금리·신용", "level", "%p", "up"),
    "T10Y3M": ("장단기 금리차 (10년−3개월)", "금리·신용", "level", "%p", "up"),
    "BAMLH0A0HYM2": ("하이일드 스프레드", "금리·신용", "level", "%p", "down"),
    "INDPRO": ("산업생산 (전년 대비)", "경기", "yoy", "%", "up"),
    "RSAFS": ("소매판매 (전년 대비)", "경기", "yoy", "%", "up"),
    "UMCSENT": ("미시간대 소비자심리", "경기", "level", "", "up"),
    "M2SL": ("M2 통화량 (전년 대비)", "유동성", "yoy", "%", "neutral"),
    "WALCL": ("연준 총자산", "유동성", "scale:0.000001", "조 달러", "neutral"),
    "DTWEXBGS": ("달러 인덱스 (광의)", "유동성", "level", "", "neutral"),
    "NFCI": ("금융여건지수 (시카고 연은)", "유동성", "level", "", "down"),
}
GROUP_ORDER = ["물가", "고용", "금리·신용", "경기", "유동성"]
# Scheduled monthly / weekly releases tracked as events (daily market series are not "releases").
RELEASES = ["CPIAUCSL", "CPILFESL", "PCEPILFE", "UNRATE", "PAYEMS", "ICSA", "SAHMREALTIME", "INDPRO", "RSAFS", "UMCSENT"]


def _session():
    """FRED silently stalls browser-like custom User-Agents coming from datacenter IPs
    (GitHub Actions) but serves the plain requests UA; short timeouts so a stall can
    never hold up the whole refresh."""
    s = http_session(pool=8)
    s.headers["User-Agent"] = requests.utils.default_user_agent()
    s.mount("https://", requests.adapters.HTTPAdapter(max_retries=1, pool_maxsize=8))
    return s


def _fetch_one(s, sid: str) -> pd.DataFrame:
    r = s.get(FRED_CSV, params={"id": sid}, timeout=20)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    if df.shape[1] < 2 or len(df) < 10:
        raise ValueError(f"{sid}: unexpected CSV")
    df.columns = ["date", "value"]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")  # FRED uses "." for missing
    df = df.dropna()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df.assign(series=sid)


def refresh() -> dict:
    s = _session()
    old = store.read("macro")
    frames, failed = [], []
    with cf.ThreadPoolExecutor(8) as ex:
        futs = {ex.submit(_fetch_one, s, sid): sid for sid in SERIES}
        for f in cf.as_completed(futs):
            sid = futs[f]
            try:
                df = f.result()
            except Exception as e:  # noqa: BLE001
                failed.append(f"{sid}: {e}")
                continue
            n_old = int((old["series"] == sid).sum()) if len(old) else 0
            if n_old and len(df) < 0.9 * n_old:
                failed.append(f"{sid}: download shrank ({len(df)} < {n_old})")
                continue
            frames.append(df)
    if not frames:
        raise RuntimeError("all FRED downloads failed: " + "; ".join(failed[:5]))
    new = pd.concat(frames, ignore_index=True)
    keep = old[old["series"].isin(SERIES) & ~old["series"].isin(new["series"])] if len(old) else old
    if len(old):
        record_releases(old, new)
    store.write("macro", pd.concat([keep, new], ignore_index=True).sort_values(["series", "date"]))
    if failed:
        store.log("warn", "macro", "; ".join(failed))
    return {"latest_date": str(new["date"].max()), "series": len(frames), "failed": len(failed)}


def record_releases(old: pd.DataFrame, new: pd.DataFrame, now: dt.datetime | None = None) -> pd.DataFrame:
    """A tracked series whose latest observation moved forward was just released: store
    (series, observation, value, previous value, detection time). FRED keeps no release
    timestamps in its keyless CSV, so the release is dated by when this refresh first saw it."""
    now = now or dt.datetime.now(dt.timezone.utc)
    rows = []
    for sid in RELEASES:
        o, n = old[old["series"] == sid], new[new["series"] == sid]
        if o.empty or n.empty or max(n["date"]) <= max(o["date"]):
            continue
        s = display_series(n, sid)
        if len(s) < 2:
            continue
        rows.append({"series": sid, "obs_date": s.index[-1], "value": float(s.iloc[-1]), "prev": float(s.iloc[-2]),
                     "detected_at": now.isoformat(timespec="minutes"), "date": now.astimezone(ET).date()})
    df = pd.DataFrame(rows)
    if len(df):
        store.upsert("macro_releases", df, ["series", "obs_date"])
    return df


def releases(days: int = 45) -> list[dict]:
    """Recent releases with the market's move on the release day: S&P 500 % and US 10-year yield
    in bp, close of the first session on/after the release vs the session before."""
    rel = store.read("macro_releases")
    if rel.empty:
        return []
    rel = rel[pd.to_datetime(rel["date"]).dt.date >= dt.date.today() - dt.timedelta(days=days)]
    idx = store.read("indices")
    out = []
    for r in rel.sort_values("detected_at", ascending=False).itertuples():
        name, group, _t, unit, good = SERIES[r.series]
        row = {"series": r.series, "name": name, "group": group, "unit": unit, "good": good, "obs_date": str(r.obs_date),
               "value": r.value, "prev": r.prev, "chg": r.value - r.prev, "date": str(r.date), "detected_at": r.detected_at}
        for sym, key, bp in (("^GSPC", "spx", False), ("^TNX", "us10y", True)):
            s = idx[idx["symbol"] == sym].sort_values("date") if len(idx) else idx
            d = pd.to_datetime(s["date"]).dt.date.to_numpy() if len(s) else []
            i = int(pd.Index(d).searchsorted(pd.Timestamp(r.date).date())) if len(d) else 0
            if 0 < i < len(d):
                a, b = float(s["close"].iloc[i - 1]), float(s["close"].iloc[i])
                row[key] = (b - a) * 100 if bp else (b / a - 1) * 100
                row["react_date"] = str(d[i])
        out.append(row)
    return out


def display_series(raw: pd.DataFrame, sid: str) -> pd.Series:
    """Raw observations -> the series shown on screen (date-indexed)."""
    s = raw.set_index("date")["value"].sort_index()
    t = SERIES[sid][2]
    if t == "yoy":
        # 12 observations back for monthly data, 52 for weekly
        lag = 52 if len(s) > 3 and (s.index[-1] - s.index[-2]).days <= 8 else 12
        s = (s / s.shift(lag) - 1) * 100
    elif t == "mom":
        s = s.diff()
    elif t.startswith("scale:"):
        s = s * float(t.split(":")[1])
    return s.dropna()


def _flag(code, label, level, strong=False):
    return {"code": code, "label": label, "level": level, "strong": strong}


def _flags(sid: str, s: pd.Series) -> list[dict]:
    """Reference highlights (not trading signals)."""
    v = float(s.iloc[-1])
    f = []
    if sid == "SAHMREALTIME":
        if v >= 0.5:
            f.append(_flag("sahm", "경기침체 신호 구간", "down", True))
        elif v >= 0.3:
            f.append(_flag("sahm_watch", "경기침체 주의", "warn"))
    elif sid in ("T10Y2Y", "T10Y3M") and v < 0:
        f.append(_flag("inverted", "장단기 금리 역전", "down", True))
    elif sid == "BAMLH0A0HYM2":
        month_ago = s[s.index <= s.index[-1] - dt.timedelta(days=30)]
        if len(month_ago) and v - float(month_ago.iloc[-1]) >= 1.0:
            f.append(_flag("hy_spike", "신용 스프레드 급등 (1개월)", "down", True))
        elif v >= 5:
            f.append(_flag("hy_high", "신용 스프레드 높음", "warn"))
    elif sid == "ICSA":
        year_ago = s[s.index <= s.index[-1] - dt.timedelta(days=364)]
        if len(year_ago) and v >= 1.2 * float(year_ago.iloc[-1]):
            f.append(_flag("claims_up", "청구 건수 급증 (전년 대비 +20% 이상)", "down"))
    elif sid in ("CPIAUCSL", "CPILFESL", "PCEPILFE") and v >= 4:
        f.append(_flag("hot_inflation", "고물가 (4% 이상)", "warn"))
    elif sid == "NFCI" and v > 0:
        f.append(_flag("tight", "금융여건 긴축 (평균보다 타이트)", "warn"))
    elif sid == "PAYEMS" and v < 0:
        f.append(_flag("jobs_down", "고용 감소", "down", True))
    return f


def summary() -> dict:
    raw = store.read("macro")
    today = dt.date.today()
    cards = []
    for sid, (name, group, _t, unit, good) in SERIES.items():
        card = {"id": sid, "name": name, "group": group, "unit": unit, "good": good}
        r = raw[raw["series"] == sid] if len(raw) else raw
        s = display_series(r, sid) if len(r) else pd.Series(dtype=float)
        if len(s) >= 2:
            last_d = s.index[-1]
            year_ago = s[s.index <= last_d - dt.timedelta(days=364)]
            monthly = len(s) > 2 and (s.index[-1] - s.index[-2]).days >= 28
            card.update({
                "date": str(last_d), "monthly": monthly, "value": float(s.iloc[-1]), "prev": float(s.iloc[-2]),
                "chg": float(s.iloc[-1] - s.iloc[-2]),
                "chg_1y": float(s.iloc[-1] - year_ago.iloc[-1]) if len(year_ago) else None,
                "age_days": (today - last_d).days, "flags": _flags(sid, s),
            })
        else:
            card["flags"] = [_flag("nodata", "데이터 없음", "stale")]
        cards.append(card)
    return {"cards": cards, "groups": GROUP_ORDER}


def history(ids: list[str], since: dt.date | None = None) -> dict:
    raw = store.read("macro")
    out = {}
    for sid in ids:
        if sid in SERIES and len(raw):
            s = display_series(raw[raw["series"] == sid], sid)
            if since:
                s = s[s.index >= since]
            out[sid] = [[str(d), round(float(v), 4)] for d, v in s.items()]
    return out
