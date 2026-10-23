"use client";
import Link from "next/link";
import { Panel } from "@/components/bits";
import { useApi } from "@/lib/api";

type M = { key: string; label: string; score: { score: number; score_5d_ago: number | null } | null; trend: { state: string; dist20: number } | null;
  new_high: number | null; new_low: number | null; above20: number | null; leaders_above20: number | null };
type Ev = { date: string; time: string; kind: string; title: string; ticker: string | null; market: string };
type S = { markets: M[]; vix: { ratio: number | null; vix: number | null }; kr_flow: { market: string; foreign: number; inst: number; indiv: number; date: string }[]; events: Ev[] };

const tone = (score: number) => (score >= 70 ? "text-emerald-400" : score < 30 ? "text-red-400" : "text-zinc-100");
const word = (score: number) => (score >= 70 ? "폭넓은 강세" : score >= 50 ? "보통 이상" : score >= 30 ? "보통 이하" : "폭넓은 약세");
const trendTone: Record<string, string> = { 강세: "text-emerald-400", 약세: "text-red-400", 중립: "text-zinc-300" };
const eok = (v: number) => `${v > 0 ? "+" : ""}${Math.round(v).toLocaleString("ko-KR")}억`;

/** Home headline: one card per market (health score, index trend, highs / lows), volatility, Korean flows, next events. */
export function TodaySummary() {
  const { data } = useApi<S>("/api/summary");
  if (!data) return <Panel title="오늘의 시장 요약"><div className="h-24 animate-pulse rounded bg-zinc-900" /></Panel>;
  const inverted = (data.vix.ratio ?? 0) > 1;
  return (
    <Panel title="오늘의 시장 요약" right={<span className="text-[11px] text-zinc-500">종합 점수 = 시장 폭 지표들의 1년 백분위 (50 = 보통) · 매매 신호 아님</span>}>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {data.markets.map((m) => (
          <Link key={m.key} href="/research" className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3 hover:border-zinc-600">
            <div className="flex items-baseline justify-between">
              <span className="text-sm font-semibold text-zinc-200">{m.label}</span>
              {m.trend && <span className={`text-xs ${trendTone[m.trend.state] ?? ""}`}>지수 {m.trend.state}</span>}
            </div>
            {m.score ? (
              <div className="flex items-baseline gap-2 pt-1">
                <span className={`font-mono text-3xl font-semibold ${tone(m.score.score)}`}>{m.score.score.toFixed(0)}</span>
                <span className="text-xs text-zinc-400">{word(m.score.score)}</span>
                {m.score.score_5d_ago !== null && <span className="ml-auto text-[11px] text-zinc-500">5일 전 {m.score.score_5d_ago.toFixed(0)}</span>}
              </div>
            ) : <div className="pt-1 text-xs text-zinc-500">점수 없음</div>}
            <div className="mt-2 h-1.5 rounded bg-zinc-800"><div className="h-1.5 rounded bg-sky-500" style={{ width: `${Math.max(2, m.score?.score ?? 0)}%` }} /></div>
            <div className="flex flex-wrap gap-x-3 pt-2 text-[11px] text-zinc-400">
              {m.new_high !== null && <span>신고가 <b className="text-emerald-400">{m.new_high}</b> / 신저가 <b className="text-red-400">{m.new_low}</b></span>}
              {m.above20 !== null && <span>20일선 위 {m.above20.toFixed(0)}%</span>}
              {m.leaders_above20 !== null && <span>주도주 {m.leaders_above20.toFixed(0)}%</span>}
            </div>
          </Link>
        ))}
      </div>
      <div className="mt-3 grid gap-2 lg:grid-cols-3">
        <Link href="/term" className="rounded border border-zinc-800 p-2 text-xs hover:border-zinc-600">
          <div className="text-zinc-500">변동성</div>
          <div className="pt-0.5 text-zinc-200">VIX <b>{data.vix.vix?.toFixed(1) ?? "—"}</b> · 단기÷3개월 <b className={inverted ? "text-red-400" : "text-emerald-400"}>{data.vix.ratio?.toFixed(2) ?? "—"}</b>
            <span className="text-zinc-500"> ({inverted ? "역전: 단기 공포" : "정상"})</span></div>
        </Link>
        <Link href="/flows" className="rounded border border-zinc-800 p-2 text-xs hover:border-zinc-600">
          <div className="text-zinc-500">한국 수급 {data.kr_flow[0]?.date ?? ""}</div>
          {data.kr_flow.map((f) => (
            <div key={f.market} className="pt-0.5 text-zinc-300">{f.market === "kospi" ? "코스피" : "코스닥"} 외국인 <b className={f.foreign >= 0 ? "text-emerald-400" : "text-red-400"}>{eok(f.foreign)}</b> · 기관 <b className={f.inst >= 0 ? "text-emerald-400" : "text-red-400"}>{eok(f.inst)}</b></div>
          ))}
        </Link>
        <Link href="/calendar" className="rounded border border-zinc-800 p-2 text-xs hover:border-zinc-600">
          <div className="text-zinc-500">이번 주 일정</div>
          {data.events.slice(0, 5).map((e, i) => <div key={i} className="truncate pt-0.5 text-zinc-300"><span className="font-mono text-zinc-500">{e.date.slice(5)}</span> {e.title}</div>)}
          {!data.events.length && <div className="pt-0.5 text-zinc-500">예정된 주요 일정 없음</div>}
        </Link>
      </div>
    </Panel>
  );
}
