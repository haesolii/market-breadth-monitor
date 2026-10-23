"""AI market brief: Claude reads the dashboard's own numbers (breadth, macro releases and how
markets reacted, sectors, broker reports, earnings, active-ETF moves) and writes a short Korean
summary. Descriptive only — the prompt forbids recommendations.

    python -m app.brief            # write today's brief (needs ANTHROPIC_API_KEY), print it
    python -m app.brief --dry-run  # print the context that would be sent

Stored in table ai_brief (one row per KST date and slot: "us" after the US close, "kr" after Korea's).
"""
import argparse
import datetime as dt
import json
import os

import pandas as pd

from . import analyst, dart, earnings, etf, flows, kr_funds, macro, research, sectors, store, world

MODEL = "claude-opus-5-5"
KST = dt.timezone(dt.timedelta(hours=9))
MARKETS = {"public_repo": "미국 (상장폐지 포함, 20%)", "yahoo": "미국", "kospi": "코스피", "kosdaq": "코스닥", "crypto": "크립토"}
SYSTEM = """당신은 개인 투자 연구용 대시보드의 시장 요약을 쓰는 애널리스트입니다.
주어진 JSON 수치만 근거로 한국어 시장 브리핑을 씁니다. 규칙:
- 숫자는 JSON에 있는 값만 인용하고, 없는 사실(뉴스, 원인, 전망치)을 지어내지 않습니다.
- 매수·매도 권유, 목표가 제시, 투자 판단 표현을 쓰지 않습니다. 관찰과 해석만 씁니다.
- 매크로 발표는 "발표값(직전 대비) → 발표일 S&P 500·10년물 반응"을 함께 적어, 시장이 어떻게 받아들였는지 설명합니다.
- 시장 폭(breadth) 지표의 극단값(Bear 급증, 10일 비율 0.5 이하/2 이상, T2108 20 미만/80 초과)은 반드시 언급합니다.
- health_score는 시장 폭 지표 6개 묶음의 1년 백분위 평균(0~100, 50 = 보통, 70↑ 폭넓은 강세, 30↓ 폭넓은 약세)이며 시장과 함께 움직이는 동행 지표입니다. 예측처럼 쓰지 않습니다.
- 섹터 rotation의 quadrant는 시장 대비 상대강도(주도·약화·부진·개선)이고, above40_pct는 섹터 안 40일선 위 종목 비율입니다.
- 한국 수급(kr_flows)은 억원 단위 순매수입니다. market_today는 시장 전체, 나머지는 코스피·코스닥 전 종목 합계입니다. kr_market_funds는 투자자예탁금·신용융자 잔고(억원)와 반대매매 비중, kr_major_disclosures는 유상증자·자사주·수주 같은 주요 공시와 2거래일 주가 반응입니다.
- 형식: 마크다운. "## 한눈에" (3줄 이내) 다음 "## 시장 폭", "## 매크로 발표와 시장 반응", "## 섹터", "## 한국 수급", "## 리포트·실적·ETF", "## 체크포인트" 순서.
  해당 데이터가 비어 있는 절은 생략합니다. 전체 600단어 이내, 각 절은 짧은 글머리표."""


def _recs(df: pd.DataFrame, cols: list[str], n: int) -> list[dict]:
    if df is None or df.empty:
        return []
    d = df[[c for c in cols if c in df]].head(n).copy()
    for c in d.columns:
        if d[c].dtype.kind == "f":
            d[c] = d[c].round(2)
    return json.loads(d.to_json(orient="records", date_format="iso", force_ascii=False))


def context() -> dict:
    mm, b20 = store.read("market_monitor_daily"), store.read("breadth20")
    breadth = {}
    for src, label in MARKETS.items():
        row = {}
        b = b20[b20["source"] == src].sort_values("date").tail(2) if len(b20) else b20
        m = mm[mm["source"] == src].sort_values("date").tail(2) if len(mm) else mm
        if len(b):
            row.update(date=str(b["date"].iloc[-1]), bull=_f(b["bull"].iloc[-1]), bear=_f(b["bear"].iloc[-1]),
                       bear_prev=_f(b["bear"].iloc[0]) if len(b) > 1 else None)
        if len(m):
            r = m.iloc[-1]
            row.update(mm_date=str(r["date"]), up4=_f(r["up4"]), down4=_f(r["down4"]), ratio10=_f(r["ratio10"]),
                       t2108=_f(r["t2108"]), quarter_up25=_f(r["quarter_up25"]), quarter_down25=_f(r["quarter_down25"]),
                       eligible=_f(r["eligible_universe_count"]))
        sc = research.score_now(src) if src != "public_repo" else None
        if sc:
            row.update(health_score=sc["score"], health_score_5d_ago=sc["score_5d_ago"], health_score_20d_ago=sc["score_20d_ago"])
        if row:
            breadth[label] = row
    w = world.summary()
    idx = [{"name": r["name"], "chg1d": _r(r.get("chg1d")), "chg1m": _r(r.get("chg1m")), "unit": r.get("unit"),
            "flags": [f["label"] for f in r.get("flags", []) if f["level"] != "stale"]} for r in w["rows"] if r.get("close") is not None]
    sec = {}
    for m in ("yahoo", "kospi", "kosdaq"):
        for per in ("r1d", "r1w"):
            s = sectors.summary(m, per, leaves=0)["sectors"]
            big = sorted([x for x in s if x["n"] >= 5], key=lambda x: x["ret"])
            if big:
                sec.setdefault(MARKETS[m], {})[per] = {"top": [(x["sector"], round(x["ret"], 2)) for x in big[-3:][::-1]],
                                                       "bottom": [(x["sector"], round(x["ret"], 2)) for x in big[:3]]}
    a = analyst.feed(3)
    e = earnings.view(back=3, ahead=5, min_cap=1e10)
    rep = pd.DataFrame(e["reported"])
    if len(rep):
        rep = rep.reindex(rep["react"].abs().sort_values(ascending=False).index)
    ef = etf.overview(days=3)
    return {
        "as_of_kst": dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "breadth": breadth,
        "macro_releases_7d": [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items() if k not in ("group", "good", "detected_at")}
                              for r in macro.releases(days=7)],
        "macro_flags": [{"name": c["name"], "value": _r(c.get("value")), "flags": [f["label"] for f in c["flags"]]}
                        for c in macro.summary()["cards"] if any(f["level"] != "stale" for f in c.get("flags", []))],
        "world_indices": idx,
        "sectors": sec,
        "kr_broker_reports_3d": {"target_up": _recs(pd.DataFrame(a["up"]), ["name", "broker", "goal_chg", "react1d"], 6),
                                 "target_down": _recs(pd.DataFrame(a["down"]), ["name", "broker", "goal_chg", "react1d"], 6),
                                 "most_covered": _recs(pd.DataFrame(a["top_covered"]), ["name", "n", "react", "upside"], 6)},
        "us_earnings_3d": _recs(rep, ["date", "symbol", "name", "surprise", "react", "react_days"], 10),
        "us_earnings_next_5d": _recs(pd.DataFrame(e["upcoming"]), ["date", "symbol", "name", "time"], 15),
        "sector_rotation": {MARKETS[m]: sectors.rotation(m) for m in ("yahoo", "kospi", "kosdaq")},
        "kr_flows": _flows(),
        "kr_market_funds_억원": _funds(),
        "kr_major_disclosures_3d": [{k: r.get(k) for k in ("date", "name", "category", "title", "react")}
                                    for r in sorted(dart.events(3), key=lambda r: -abs(r.get("react") or 0))[:12]],
        "kr_prelim_earnings_3d": [{k: r.get(k) for k in ("date", "name", "title", "react", "correction")}
                                  for r in sorted(dart.view(3), key=lambda r: -abs(r.get("react") or 0))[:10]],
        "active_etf_consensus_3d": [{"name": c["name"], "buy_funds": len(c["buy"]), "sell_funds": len(c["sell"])} for c in ef["consensus"][:10]],
    }


def _funds() -> dict:
    v = kr_funds.view(30)
    if not v["rows"]:
        return {}
    last = v["rows"][-1]
    return {"date": last["date"], "investor_deposit": last["deposit"], "margin_loans": last["margin"], "margin_kospi": last["margin_kospi"],
            "margin_kosdaq": last["margin_kosdaq"], "forced_liquidation_pct": last["forced_pct"], "change_5d_20d": v["change"],
            "margin_to_market_cap_pct": v["margin_to_cap"]}


def _flows() -> dict:
    f = flows.overview(days=5)
    if not f["dates"]:
        return {}
    last = f["market"][-2:] if f["market"] else []
    sec = sorted(f["sectors"], key=lambda r: r["foreign5"])
    pick = lambda rows, who: [{"name": r["name"], who + "_5d": r[who], "foreign_hold_chg_20d": r["hold_chg20"]} for r in rows[:5]]  # noqa: E731
    return {"market_today": [{k: r[k] for k in ("date", "market", "foreign", "inst", "indiv")} for r in last],
            "all_stocks_5d_total": {k: round(sum(v), 1) for k, v in f["daily"].items()},
            "sectors_foreign_buy_5d": [(r["sector"], r["foreign5"], r["inst5"]) for r in sec[-4:][::-1]],
            "sectors_foreign_sell_5d": [(r["sector"], r["foreign5"], r["inst5"]) for r in sec[:4]],
            "foreign_buy": pick(f["stocks"]["foreign_nlargest"], "foreign"), "foreign_sell": pick(f["stocks"]["foreign_nsmallest"], "foreign"),
            "inst_buy": pick(f["stocks"]["inst_nlargest"], "inst"), "inst_sell": pick(f["stocks"]["inst_nsmallest"], "inst")}


def write(ctx: dict, slot: str) -> str:
    import anthropic  # only the brief job needs the SDK

    client = anthropic.Anthropic()
    resp = client.beta.messages.create(
        model=MODEL, max_tokens=16000, system=SYSTEM,
        output_config={"effort": "medium"},
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",  # a declined request reruns on the recommended model
        messages=[{"role": "user", "content": "오늘의 대시보드 수치 (JSON):\n" + json.dumps(ctx, ensure_ascii=False, default=str)}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"brief declined: {getattr(resp.stop_details, 'category', None)}")
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    if not text:
        raise RuntimeError(f"empty brief (stop_reason={resp.stop_reason})")
    row = pd.DataFrame([{"date": dt.datetime.now(KST).date(), "slot": slot, "created_at": store.now_utc(), "model": resp.model, "text": text}])
    store.upsert("ai_brief", row, ["date", "slot"])
    return text


def latest(n: int = 7) -> list[dict]:
    df = store.read("ai_brief")
    if df.empty:
        return []
    df = df.sort_values("created_at", ascending=False).head(n).assign(date=lambda d: d["date"].astype(str))
    return df.to_dict("records")


def _f(v) -> float | None:
    return None if v is None or pd.isna(v) else float(v)


def _r(v) -> float | None:
    return None if v is None or pd.isna(v) else round(float(v), 2)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", choices=["us", "kr"], default="us")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    ctx = context()
    if a.dry_run or not os.getenv("ANTHROPIC_API_KEY"):
        print(json.dumps(ctx, ensure_ascii=False, indent=1, default=str))
        if not a.dry_run:
            print("ANTHROPIC_API_KEY is not set: brief not written")
    else:
        print(write(ctx, a.slot))
