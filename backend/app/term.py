"""Volatility and futures term structure: contango (later > nearer, the calm normal) vs
backwardation (nearer > later, stress or a tight market).

  vol_index      — VIX family by horizon (^VIX9D, ^VIX, ^VIX3M, ^VIX6M, ^VIX1Y) + ^VVIX, ^VXN (Yahoo).
                   VIX / VIX3M > 1 = the volatility curve is inverted (backwardation).
  vix_futures    — CBOE daily settlement of the monthly VX futures (one row per trade date and expiry);
                   back-filled BACKFILL sessions on the first run.
  futures_basis  — front futures vs the cash index per day: ES / S&P 500, NQ / Nasdaq-100,
                   RTY / Russell 2000, YM / Dow (Yahoo continuous front month) and KOSPI 200 futures /
                   KOSPI 200 (Naver). basis % = futures / cash - 1; normally slightly positive (carry),
                   negative = backwardation.
  crude_curve    — WTI crude futures by month (Yahoo CL<month><yy>.NYM), today's snapshot.

ponytail: Yahoo's continuous front month rolls (a jump in the basis on roll days) and futures settle
at a different time than the cash close, so day-to-day basis is approximate; a precise basis needs
synchronous intraday quotes and the dividend-adjusted fair value.
"""
import datetime as dt
import re
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from . import store, world
from .collectors import http_session

VOL = {"^VIX9D": "VIX 9일", "^VIX": "VIX 30일", "^VIX3M": "VIX 3개월", "^VIX6M": "VIX 6개월", "^VIX1Y": "VIX 1년",
       "^VVIX": "VVIX (VIX의 변동성)", "^VXN": "VXN (나스닥 100)"}
CURVE = ["^VIX9D", "^VIX", "^VIX3M", "^VIX6M", "^VIX1Y"]
PAIRS = {"ES": ("ES=F", "^GSPC", "S&P 500"), "NQ": ("NQ=F", "^NDX", "나스닥 100"), "RTY": ("RTY=F", "^RUT", "러셀 2000"),
         "YM": ("YM=F", "^DJI", "다우")}
CBOE = "https://www.cboe.com/us/futures/market_statistics/settlement/csv"
NAVER = "https://m.stock.naver.com/api/index/{code}/price"
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
BACKFILL = 260
SINCE = dt.date.today() - dt.timedelta(days=3 * 365)
MONTH_CODE = "FGHJKMNQUVXZ"


def _closes(symbols: list[str], s) -> pd.DataFrame:
    frames = []
    for sym in symbols:
        df, _ = world.chart(sym, s, live=True)
        frames.append(df[df["date"] >= SINCE][["date", "symbol", "close"]])
    return pd.concat(frames, ignore_index=True)


def parse_cboe(text: str, trade_date: dt.date) -> pd.DataFrame:
    """Monthly VX contracts (symbol VX/X6, not the weeklies VX44/X6) from one settlement CSV."""
    rows = []
    for line in text.splitlines()[1:]:
        p = line.split(",")
        if len(p) >= 4 and p[0] == "VX" and re.fullmatch(r"VX/[A-Z]\d", p[1]):
            rows.append({"date": trade_date, "expiry": dt.date.fromisoformat(p[2]), "price": float(p[3])})
    return pd.DataFrame(rows)


def _vix_futures(s, old: pd.DataFrame) -> pd.DataFrame:
    have = set(pd.to_datetime(old["date"]).dt.date) if len(old) else set()
    today = dt.date.today()
    days = [today - dt.timedelta(days=i) for i in range(0, int(BACKFILL * 1.45) if not have else 8)]
    def one(d):
        r = s.get(CBOE, params={"dt": d.isoformat()}, timeout=30)
        return parse_cboe(r.text, d) if r.ok and r.text.startswith("Product") else None

    with ThreadPoolExecutor(8) as ex:
        frames = [f for f in ex.map(one, [d for d in days if d.weekday() < 5 and d not in have]) if f is not None and len(f)]
    return pd.concat([old, *frames], ignore_index=True).drop_duplicates(["date", "expiry"], keep="last") if frames else old


def _naver(s, code: str, pages: int) -> pd.Series:
    rows = []
    for page in range(1, pages + 1):
        r = s.get(NAVER.format(code=code), params={"pageSize": 60, "page": page}, timeout=20)
        r.raise_for_status()
        items = r.json()
        if not items:
            break
        rows += [(dt.date.fromisoformat(x["localTradedAt"][:10]), float(x["closePrice"].replace(",", ""))) for x in items]
    return pd.Series(dict(rows)).sort_index()


def _crude(s) -> pd.DataFrame:
    today = dt.date.today()
    rows = []
    for i in range(1, 13):
        m = (today.month - 1 + i) % 12
        y = today.year + (today.month - 1 + i) // 12
        sym = f"CL{MONTH_CODE[m]}{y % 100:02d}.NYM"
        try:
            df, _ = world.chart(sym, s, live=True)
        except Exception:  # noqa: BLE001 - far months may not trade yet
            continue
        rows.append({"contract": f"{y}-{m + 1:02d}", "symbol": sym, "price": float(df["close"].iloc[-1]), "date": df["date"].iloc[-1]})
    df = pd.DataFrame(rows)
    return df[df["date"] >= df["date"].max() - dt.timedelta(days=3)] if len(df) else df  # drop the expired front month


def refresh() -> dict:
    s = http_session()
    s.headers["User-Agent"] = BROWSER_UA
    vol = _closes(list(VOL), s)
    store.write("vol_index", vol)
    px = _closes(sorted({x for f, c, _ in PAIRS.values() for x in (f, c)}), s).pivot_table(index="date", columns="symbol", values="close")
    basis = [pd.DataFrame({"date": px.index, "pair": k, "fut": px[f].values, "spot": px[c].values}) for k, (f, c, _) in PAIRS.items()]
    k_pages = 1 if len(store.read("futures_basis")) else 13
    fut, spot = _naver(s, "FUT", k_pages), _naver(s, "KPI200", k_pages)
    both = pd.concat([fut.rename("fut"), spot.rename("spot")], axis=1).dropna()
    basis.append(both.rename_axis("date").reset_index().assign(pair="K200"))
    old_b = store.read("futures_basis")
    b = pd.concat([old_b, *basis], ignore_index=True).dropna(subset=["fut", "spot"]).drop_duplicates(["date", "pair"], keep="last")
    store.write("futures_basis", b.sort_values(["pair", "date"]).reset_index(drop=True))
    vx = _vix_futures(s, store.read("vix_futures"))
    store.write("vix_futures", vx)
    crude = _crude(s)
    if len(crude):
        store.write("crude_curve", crude)
    return {"latest_date": str(max(vol["date"])), "vix_futures_days": int(vx["date"].nunique()) if len(vx) else 0, "crude": len(crude)}


# ---- read side ----------------------------------------------------------------------
def _rows(df: pd.DataFrame) -> list[dict]:
    df = df.copy()
    for c in df.columns:
        if df[c].dtype == object or "date" in c or c == "expiry":
            df[c] = df[c].astype(str)
    return df.astype(object).where(df.notna(), None).to_dict("records")


def view(days: int = 252) -> dict:
    vol, vx, b, crude = store.read("vol_index"), store.read("vix_futures"), store.read("futures_basis"), store.read("crude_curve")
    out = {"labels": VOL, "pairs": {k: v[2] for k, v in PAIRS.items()} | {"K200": "코스피 200"}}
    if len(vol):
        w = vol.pivot_table(index="date", columns="symbol", values="close").sort_index().tail(days)
        out["vol"] = {"dates": [str(d) for d in w.index], "series": {c: [None if pd.isna(v) else round(float(v), 2) for v in w[c]] for c in w}}
        f = w.ffill()  # an index not yet updated today keeps its last close
        snap = lambda i: [None if c not in f or pd.isna(f[c].iloc[i]) else round(float(f[c].iloc[i]), 2) for c in CURVE]  # noqa: E731
        out["vol_curve"] = {"labels": [VOL[c] for c in CURVE], "now": snap(-1), "w1": snap(-6) if len(w) > 6 else None,
                            "m1": snap(-22) if len(w) > 22 else None, "date": str(w.index[-1])}
        if "^VIX" in w and "^VIX3M" in w:
            r = (w["^VIX"] / w["^VIX3M"]).dropna()
            out["vix_ratio"] = {"now": round(float(r.iloc[-1]), 3), "pctile": round(float((r <= r.iloc[-1]).mean() * 100), 1),
                                "days_inverted_1y": int((r.tail(252) > 1).sum())}
    if len(vx):
        vx = vx.copy()
        vx["date"] = pd.to_datetime(vx["date"]).dt.date
        dates = sorted(vx["date"].unique())
        curve = lambda d: vx[(vx["date"] == d)].sort_values("expiry")  # noqa: E731
        out["vix_futures"] = {"date": str(dates[-1]), "curves": {lab: _rows(curve(d)[["expiry", "price"]]) for lab, d in
                                                                  (("now", dates[-1]), ("w1", dates[-6] if len(dates) > 6 else None),
                                                                   ("m1", dates[-22] if len(dates) > 22 else None)) if d}}
        f12 = []
        for d in dates[-days:]:  # front-month vs second-month spread over time (contango > 0)
            c = curve(d)
            if len(c) >= 2:
                f12.append([str(d), round(float(c["price"].iloc[1] / c["price"].iloc[0] - 1) * 100, 2), round(float(c["price"].iloc[0]), 2)])
        out["vix_m1m2"] = f12
    if len(b):
        b = b.copy()
        b["basis"] = (b["fut"] / b["spot"] - 1) * 100
        out["basis"] = {k: [[str(d), round(float(v), 3)] for d, v in zip(g["date"].tail(days), g["basis"].tail(days))] for k, g in b.groupby("pair")}
        last = b.sort_values("date").groupby("pair").tail(1)
        out["basis_now"] = _rows(last[["pair", "date", "fut", "spot", "basis"]])
    if len(crude):
        out["crude"] = _rows(crude)
    return out
