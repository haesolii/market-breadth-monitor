"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Err, Kpi, Panel } from "@/components/bits";
import { TimeChart } from "@/components/TimeChart";
import { useApi } from "@/lib/api";
import { useSetting } from "@/lib/settings";
import { stockHref } from "@/lib/stock";

type B = { date: string; n: number; above10: number; above20: number; above50: number | null; new_high: number; new_low: number;
  leaders: number | null; leaders_above10: number | null; leaders_above20: number | null; leaders_r21: number | null };
type L = { ticker: string; name: string | null; sector: string | null; close: number; r21: number | null; r63: number | null; r126: number | null;
  adr: number; dvol: number; off_high: number; above10: boolean; above20: boolean; above50: boolean };
type T = { close: number; ma10: number; ma20: number; ma10_rising: boolean; state: string; dist10: number; dist20: number };
type Res = { market: string; index: string; trend: T | null; index_closes: [string, number][]; breadth: B[]; leaders: L[]; leader_pct: number };

const MARKETS: [string, string][] = [["nasdaq", "나스닥"], ["yahoo", "미국 전체"], ["kospi", "코스피"], ["kosdaq", "코스닥"], ["crypto", "크립토"]];
const INDEX_NAME: Record<string, string> = { "^IXIC": "나스닥 종합", "^GSPC": "S&P 500", "^KS11": "코스피", "^KQ11": "코스닥", "BTC-USD": "비트코인" };
const pct = (v: number | null | undefined, d = 1) => (v === null || v === undefined ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(d)}%`);
const tone = (v: number | null | undefined) => (!v ? "text-zinc-400" : v > 0 ? "text-emerald-400" : "text-red-400");
const STATE: Record<string, [string, "up" | "down" | "flat", string]> = {
  강세: ["강세 (공격 가능)", "up", "지수가 10일선 위, 10일선이 20일선 위에서 오르는 중"],
  중립: ["중립 (선별)", "flat", "추세가 엇갈림: 지수와 10·20일선 위치가 정렬되지 않음"],
  약세: ["약세 (현금·관망)", "down", "지수가 20일선 아래, 10일선도 20일선 아래"],
};
const SORTS: [keyof L, string][] = [["r21", "1개월"], ["r63", "3개월"], ["r126", "6개월"], ["adr", "변동폭"], ["off_high", "고점 대비"]];
const Dot = ({ on }: { on: boolean }) => <span className={on ? "text-emerald-400" : "text-zinc-600"}>{on ? "●" : "○"}</span>;

export default function Leaders() {
  const [market, setMarket] = useSetting("leaders.market", "nasdaq");
  const [sort, setSort] = useState<keyof L>("r63");
  const [minAdr, setMinAdr] = useState(0);
  const { data, error } = useApi<Res>(`/api/leaders?market=${market}`);
  const dates = useMemo(() => data?.breadth.map((b) => b.date) ?? [], [data]);
  const idx = useMemo(() => new Map(data?.index_closes ?? []), [data]);
  const ma = useMemo(() => (k: "above10" | "above20" | "above50", name: string, color: string) => ({ name, color, type: "line" as const, data: data?.breadth.map((b) => b[k]) ?? [] }), [data]);
  const last = data?.breadth.at(-1), prev5 = data?.breadth.at(-6);
  const rows = useMemo(() => [...(data?.leaders ?? [])].filter((l) => l.adr >= minAdr).sort((a, b) => ((b[sort] as number) ?? -1e9) - ((a[sort] as number) ?? -1e9)), [data, sort, minAdr]);
  const st = data?.trend ? STATE[data.trend.state] : null;
  const kr = market === "kospi" || market === "kosdaq";

  return (
    <div className="space-y-3">
      <Panel title="주도주·추세 (Qullamaggie 방식)" right={
        <div className="flex overflow-hidden rounded border border-zinc-700 text-xs">
          {MARKETS.map(([k, l]) => <button key={k} onClick={() => setMarket(k)} className={`px-3 py-1 ${market === k ? "bg-sky-700 text-white" : "text-zinc-300 hover:bg-zinc-800"}`}>{l}</button>)}
        </div>}>
        <Err error={error} />
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-6">
          {data?.trend && st && <Kpi label={`${INDEX_NAME[data.index] ?? data.index} 추세`} value={<span className="text-lg">{st[0]}</span>} tone={st[1]}
            sub={`${st[2]} · 10일선 대비 ${pct(data.trend.dist10)} · 20일선 대비 ${pct(data.trend.dist20)}`} />}
          {last && <>
            <Kpi label="10일선 위 종목" value={`${last.above10.toFixed(0)}%`} sub={prev5 ? `5일 전 ${prev5.above10.toFixed(0)}%` : undefined} />
            <Kpi label="20일선 위 종목" value={`${last.above20.toFixed(0)}%`} sub={prev5 ? `5일 전 ${prev5.above20.toFixed(0)}%` : undefined} />
            <Kpi label="50일선 위 종목" value={last.above50 === null ? "—" : `${last.above50.toFixed(0)}%`} sub={prev5?.above50 != null ? `5일 전 ${prev5.above50.toFixed(0)}%` : undefined} />
            <Kpi label="52주 신고가 / 신저가" value={<span className="text-lg"><span className="text-emerald-400">{last.new_high}</span> / <span className="text-red-400">{last.new_low}</span></span>}
              sub={`대상 ${last.n.toLocaleString()}종목`} />
            <Kpi label={`주도주 20일선 위 (${last.leaders ?? 0}종목)`} value={last.leaders_above20 === null ? "—" : `${last.leaders_above20.toFixed(0)}%`}
              tone={(last.leaders_above20 ?? 0) >= 70 ? "up" : (last.leaders_above20 ?? 100) < 40 ? "down" : "flat"}
              sub={`주도주 1개월 중앙 수익률 ${pct(last.leaders_r21)}`} />
          </>}
        </div>
        <div className="mt-2 text-[11px] text-zinc-500">
          Qullamaggie는 &ldquo;지수가 10·20일선 위에서 오르고, 주도주들이 계속 오를 때만&rdquo; 공격적으로 매수합니다. 주도주 = 그날 거래대금이 충분한 종목 중 3개월 수익률 상위 {data?.leader_pct ?? 2}%.
          주도주의 20일선 위 비율이 무너지면 시장보다 먼저 위험 신호가 나오는 경우가 많습니다. 매매 신호 아님.
        </div>
      </Panel>

      {dates.length > 0 && (
        <div className="grid gap-3 xl:grid-cols-2">
          <Panel title="이동평균 위 종목 비율 (10·20·50일)">
            <TimeChart dates={dates} series={[ma("above10", "10일선 위", "#38bdf8"), ma("above20", "20일선 위", "#f59e0b"), ma("above50", "50일선 위", "#a78bfa")]}
              spy={dates.map((d) => idx.get(d) ?? null)} lowerName={INDEX_NAME[data!.index] ?? data!.index} height={420} yName="%" />
          </Panel>
          <Panel title="주도주 상태와 신고가·신저가">
            <TimeChart dates={dates} series={[
              { name: "주도주 10일선 위 %", color: "#10b981", type: "line", data: data!.breadth.map((b) => b.leaders_above10) },
              { name: "주도주 20일선 위 %", color: "#f59e0b", type: "line", data: data!.breadth.map((b) => b.leaders_above20) },
            ]} spy={data!.breadth.map((b) => b.new_high - b.new_low)} lowerName="신고가 − 신저가 (종목 수)" lowerBar height={420} yName="%" />
          </Panel>
        </div>
      )}

      {data && (
        <Panel title={`오늘의 주도주 ${rows.length}종목 (1·3·6개월 수익률 상위 ${data.leader_pct}%)`} right={<>
          <span className="text-xs text-zinc-400">정렬</span>
          <div className="flex overflow-hidden rounded border border-zinc-700 text-xs">
            {SORTS.map(([k, l]) => <button key={k} onClick={() => setSort(k)} className={`px-2 py-1 ${sort === k ? "bg-zinc-700 text-white" : "text-zinc-400 hover:bg-zinc-800"}`}>{l}</button>)}
          </div>
          <select value={minAdr} onChange={(e) => setMinAdr(Number(e.target.value))} className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200">
            {[0, 2, 3, 4, 5].map((v) => <option key={v} value={v}>{v ? `변동폭 ${v}% 이상` : "변동폭 전체"}</option>)}
          </select>
        </>}>
          <div className="max-h-[560px] overflow-auto">
            <table className="w-full font-mono text-xs">
              <thead className="sticky top-0 bg-zinc-900 text-zinc-400"><tr>
                <th className="text-left">종목</th><th className="text-left">섹터</th><th>1개월</th><th>3개월</th><th>6개월</th>
                <th title="최근 20일 평균 일간 변동폭 (종가 기준 근사: 고가·저가 기준 ADR의 약 0.6~0.7배)">변동폭*</th><th>52주 고점 대비</th><th>10·20·50일선</th><th>거래대금(20일)</th>
              </tr></thead>
              <tbody>
                {rows.map((l) => (
                  <tr key={l.ticker} className="border-t border-zinc-900 text-center hover:bg-zinc-900">
                    <td className="max-w-48 truncate text-left font-sans"><Link className="text-sky-300 hover:underline" href={stockHref(l.ticker, market === "nasdaq" ? "yahoo" : market)}>{kr || market === "crypto" ? l.name ?? l.ticker : l.ticker}</Link> <span className="text-[10px] text-zinc-500">{kr ? l.ticker : l.name}</span></td>
                    <td className="max-w-32 truncate text-left font-sans text-zinc-400">{l.sector ?? ""}</td>
                    <td className={tone(l.r21)}>{pct(l.r21, 0)}</td><td className={tone(l.r63)}>{pct(l.r63, 0)}</td><td className={tone(l.r126)}>{pct(l.r126, 0)}</td>
                    <td>{l.adr.toFixed(1)}%</td><td className={l.off_high > -10 ? "text-emerald-400" : "text-zinc-400"}>{pct(l.off_high)}</td>
                    <td><Dot on={l.above10} /> <Dot on={l.above20} /> <Dot on={l.above50} /></td>
                    <td className="text-zinc-400">{kr ? `${(l.dvol / 1e8).toFixed(0)}억` : `$${(l.dvol / 1e6).toFixed(0)}M`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-1 text-[11px] text-zinc-500">* 데이터가 종가만 있어 변동폭은 종가 대비 등락폭 평균으로 근사했습니다 (Qullamaggie 기준 ADR 5%는 여기서 약 3~3.5%). 고점 근처(−10% 이내)에서 10·20일선 위에 있는 종목이 그의 셋업 후보입니다.</div>
        </Panel>
      )}
    </div>
  );
}
