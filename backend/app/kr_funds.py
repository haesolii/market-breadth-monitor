"""Korean market funds (KOFIA FreeSIS, keyless): investor deposits, credit (margin) loans by market,
unsettled trades and forced liquidations — how much leverage and dry powder retail holds.

  kr_funds — per day (억원): deposit (투자자예탁금), deriv_deposit (장내파생상품 거래예수금), rp (대고객 RP 매도잔고),
             unsettled (위탁매매 미수금), forced (미수금 대비 실제 반대매매금액), forced_pct (미수금 대비 반대매매 비중 %),
             margin / margin_kospi / margin_kosdaq (신용거래융자), stock_loan (신용거래대주), pledge_loan (예탁증권담보융자)
Short-selling statistics are not here: KRX's data portal now requires a login.
"""
import datetime as dt

import pandas as pd

from . import store
from .collectors import http_session

API = "https://freesis.kofia.or.kr/meta/getMetaDataList.do"
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
BACKFILL_DAYS = 3 * 365
# FreeSIS object -> column per TMPVn (values in 백만원, except the % column)
SERIES = {"STATSCU0100000060BO": {"TMPV2": "deposit", "TMPV3": "deriv_deposit", "TMPV4": "rp", "TMPV5": "unsettled",
                                  "TMPV6": "forced", "TMPV7": "forced_pct"},
          "STATSCU0100000070BO": {"TMPV2": "margin", "TMPV3": "margin_kospi", "TMPV4": "margin_kosdaq", "TMPV5": "stock_loan",
                                  "TMPV9": "pledge_loan"}}


def parse(rows: list[dict], cols: dict[str, str]) -> pd.DataFrame:
    out = pd.DataFrame([{"date": dt.datetime.strptime(r["TMPV1"], "%Y%m%d").date(),
                         **{c: (float(r[k]) if r.get(k) is not None else None) for k, c in cols.items()}} for r in rows])
    for c in cols.values():
        if c != "forced_pct" and c in out:
            out[c] = out[c] / 100  # 백만원 -> 억원
    return out


def refresh() -> dict:
    s = http_session()
    s.headers.update({"User-Agent": BROWSER_UA, "Content-Type": "application/json"})
    old = store.read("kr_funds")
    today = dt.date.today()
    start = today - dt.timedelta(days=10 if len(old) else BACKFILL_DAYS)
    frames = []
    for obj, cols in SERIES.items():
        r = s.post(API, json={"dmSearch": {"tmpV40": "1000000", "tmpV41": "1", "tmpV1": "D", "tmpV45": start.strftime("%Y%m%d"),
                                           "tmpV46": today.strftime("%Y%m%d"), "OBJ_NM": obj}}, timeout=30)
        r.raise_for_status()
        rows = r.json().get("ds1") or []
        if not rows:
            raise RuntimeError(f"KOFIA {obj}: no rows")
        frames.append(parse(rows, cols).set_index("date"))
    new = pd.concat(frames, axis=1).reset_index()
    out = pd.concat([old, new], ignore_index=True).drop_duplicates("date", keep="last").sort_values("date") if len(old) else new.sort_values("date")
    store.write("kr_funds", out.reset_index(drop=True))
    return {"latest_date": str(out["date"].max()), "rows": len(out)}


def view(days: int = 756) -> dict:
    df = store.read("kr_funds")
    if df.empty:
        return {"rows": []}
    df = df.sort_values("date").tail(days)
    sm = store.read("sector_map")
    cap = {m: float(sm.loc[sm["market"] == m, "size"].sum()) / 1e8 for m in ("kospi", "kosdaq")} if len(sm) else {}
    last = df.iloc[-1]
    ago = lambda n: df.iloc[-1 - n] if len(df) > n else None  # noqa: E731
    chg = {k: {n: (None if ago(n) is None or pd.isna(ago(n)[k]) else float(last[k] - ago(n)[k])) for n in (5, 20)}
           for k in ("deposit", "margin", "margin_kospi", "margin_kosdaq")}
    ratio = {m: (float(last[f"margin_{m}"]) / cap[m] * 100 if cap.get(m) else None) for m in ("kospi", "kosdaq")}
    return {"rows": df.assign(date=df["date"].astype(str)).astype(object).where(df.notna(), None).to_dict("records"),
            "change": chg, "margin_to_cap": ratio}
