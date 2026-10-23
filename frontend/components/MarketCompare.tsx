"use client";
import { useMemo, useState } from "react";
import { Err, Panel, RangePicker, Select } from "@/components/bits";
import { TimeChart } from "@/components/TimeChart";
import { LIVE_MS, useApi } from "@/lib/api";

type Res = { metric: string; series: Record<string, [string, number][]>; labels: Record<string, string> };

const METRICS: [string, string][] = [
  ["t2108", "40일선 위 종목 비율 (T2108, %)"], ["ratio10", "10일 매수·매도 강도 비율"],
  ["bear_pct", "20% 급락 종목 비중 (Bear ÷ 대상 종목, %)"], ["net4_pct", "4% 순상승 비중 ((상승−하락) ÷ 대상 종목, %)"],
];
const COLORS: Record<string, string> = { yahoo: "#e4e4e7", nasdaq: "#38bdf8", kospi: "#f59e0b", kosdaq: "#a78bfa", crypto: "#10b981" };
const LINES: Record<string, { y: number; label: string; color: string }[]> = {
  t2108: [{ y: 20, label: "20 과매도", color: "#f87171" }, { y: 80, label: "80 과매수", color: "#34d399" }],
  ratio10: [{ y: 0.5, label: "0.5 약세", color: "#f87171" }, { y: 2, label: "2 강세", color: "#34d399" }],
};

/** Size-free breadth readings of every market on one date axis (crypto trades on weekends too). */
export function MarketCompare() {
  const [metric, setMetric] = useState("t2108");
  const [range, setRange] = useState(126);
  const { data, error } = useApi<Res>(`/api/compare?metric=${metric}`, LIVE_MS);
  const { dates, series } = useMemo(() => {
    if (!data) return { dates: [], series: [] };
    const all = [...new Set(Object.values(data.series).flatMap((s) => s.map(([d]) => d)))].sort();
    const dates = range ? all.filter((d) => d >= all[Math.max(0, all.length - Math.round(range * 1.45))]) : all;  // calendar days incl. weekends
    const series = Object.entries(data.series).map(([k, s]) => {
      const m = new Map(s);
      return { name: data.labels[k] ?? k, data: dates.map((d) => m.get(d) ?? null), color: COLORS[k] ?? "#a1a1aa", type: "line" as const };
    });
    return { dates, series };
  }, [data, range]);
  return (
    <Panel title="시장 간 비교 (Cross-market)" right={<><Select value={metric} onChange={setMetric} options={METRICS} /><RangePicker value={range} onChange={setRange} /></>}>
      <Err error={error} />
      <TimeChart dates={dates} series={series} lines={LINES[metric] ?? []} height={340} />
      <div className="mt-1 text-[11px] text-zinc-500">종목 수가 아니라 비율이라 시장 규모와 무관하게 비교할 수 있음. 미국은 현재 상장 종목 기준. 크립토는 주말 포함.</div>
    </Panel>
  );
}
