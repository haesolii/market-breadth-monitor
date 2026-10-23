"use client";
import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import type { ECharts } from "echarts";
import { Err, Panel, RangePicker, useSource } from "@/components/bits";
import { CorrHeatmap } from "@/components/CorrHeatmap";
import { useApi, useBench, type Series } from "@/lib/api";
import { READ, defOf, defaultLevels, fmt } from "@/lib/defs";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

type Stat = { key: string; last: number; first: number; min: number; max: number; mean: number; pctile: number };
type Flow = { source: string; benchmark: string; range: string[]; n: number; stats: Stat[];
  vs_returns: { rows: string[]; cols: string[]; matrix: (number | null)[][] }; between: { rows: string[]; matrix: (number | null)[][] } };
type Vals = Record<string, number | null>;

const KEYS = ["bull", "bear", "up4", "down4", "ratio5", "ratio10", "quarter_up25", "quarter_down25", "month_up25", "month_down25",
  "month_up50", "month_down50", "day34_up13", "day34_down13", "day34_diff", "t2108"];
const GROUP = "indicator-flow";
const connect = (c: ECharts) => { c.group = GROUP; import("echarts").then((e) => e.connect(GROUP)); };

/** One indicator over time with its highlight levels (dashed); hovering moves every chart's crosshair. */
function Mini({ dates, data, color, levels, digits }: { dates: string[]; data: (number | null)[]; color: string; levels: (number | null)[]; digits: number }) {
  const option = useMemo(() => ({
    backgroundColor: "transparent", animation: false,
    grid: { left: 44, right: 8, top: 8, bottom: 20 },
    tooltip: { trigger: "axis", backgroundColor: "#18181b", borderColor: "#3f3f46", textStyle: { color: "#e4e4e7", fontSize: 11 },
      valueFormatter: (v: number) => (v === null || v === undefined ? "—" : Number(v).toLocaleString("en-US", { maximumFractionDigits: digits })) },
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    xAxis: { type: "category", data: dates, axisLabel: { color: "#71717a", fontSize: 9, hideOverlap: true }, axisLine: { lineStyle: { color: "#3f3f46" } } },
    yAxis: { type: "value", scale: true, splitNumber: 3, axisLabel: { color: "#71717a", fontSize: 9 }, splitLine: { lineStyle: { color: "#27272a" } } },
    series: [{ type: "line", data, showSymbol: false, connectNulls: true, lineStyle: { color, width: 1.5 }, itemStyle: { color },
      markLine: { symbol: "none", silent: true, label: { show: false },
        data: levels.filter((v): v is number => v !== null).map((y) => ({ yAxis: y, lineStyle: { color: "#a1a1aa", type: "dashed" as const, width: 1 } })) } }],
  }), [dates, data, color, levels, digits]);
  return <ReactECharts option={option} notMerge style={{ height: 130 }} theme="dark" onChartReady={connect} />;
}

const pctileTone = (p: number) => (p >= 90 ? "bg-emerald-700 text-white" : p >= 75 ? "bg-emerald-950 text-emerald-300" : p <= 10 ? "bg-red-700 text-white" : p <= 25 ? "bg-red-950 text-red-300" : "bg-zinc-800 text-zinc-300");

/** Market Monitor + 20% indicators as small multiples on one date axis, with where today sits in the
 * window (percentile) and rank correlations with the benchmark's returns and with each other. */
export function IndicatorFlow() {
  const [src, srcSel, st] = useSource("monitor", true);
  const [range, setRange] = useState(252);
  const mm = useApi<Series>(src ? `/api/monitor?source=${src}` : null);
  const flow = useApi<Flow>(src ? `/api/research/flow?source=${src}&days=${range}` : null);
  const bench = useBench(st?.source_info[src]?.benchmark ?? "^GSPC");
  const rows = useMemo(() => { const r = mm.data?.rows ?? []; return range ? r.slice(-range) : r; }, [mm.data, range]);
  const dates = useMemo(() => rows.map((r) => String(r.date)), [rows]);
  const last = rows.at(-1) as Vals | undefined, prev5 = rows.at(-6) as Vals | undefined;
  const levels = useMemo(() => defaultLevels(last?.eligible_universe_count, src), [last, src]);
  const stats = new Map((flow.data?.stats ?? []).map((s) => [s.key, s]));
  const name = (k: string) => defOf(k)?.ko ?? k;
  const benchData = useMemo(() => (bench.map ? dates.map((d) => bench.map!.get(d) ?? null) : []), [bench.map, dates]);

  return (
    <div className="space-y-3">
      <Panel title="지표 흐름 (Indicator flow)" right={<>{srcSel}<RangePicker value={range} onChange={setRange} /></>}>
        <div className="text-[11px] text-zinc-500">
          모든 차트가 같은 날짜 축을 공유합니다 (한 차트에 마우스를 올리면 전부 같은 날짜를 가리킴). 점선 = 기본 강조 기준. 백분위 = 현재 값이 선택 기간 안에서 몇 % 위치인지 (90 이상 / 10 이하는 기간 내 극단).
        </div>
        <Err error={mm.error ?? flow.error} />
        <div className="mt-2">
          <div className="text-xs text-zinc-300">{bench.name} <span className="text-zinc-500">(벤치마크 종가)</span></div>
          <Mini dates={dates} data={benchData} color="#e4e4e7" levels={[]} digits={2} />
        </div>
        <div className="mt-2 grid gap-x-4 gap-y-2 md:grid-cols-2 xl:grid-cols-4">
          {KEYS.filter((k) => rows.some((r) => typeof r[k] === "number")).map((k) => {
            const d = defOf(k)!, s = stats.get(k), v = last?.[k], p5 = prev5?.[k];
            const digits = d.kind === "ratio" ? 2 : d.kind === "pct" ? 1 : 0;
            const color = d.kind === "up" ? "#10b981" : d.kind === "down" ? "#ef4444" : "#38bdf8";
            const read = typeof v === "number" && last ? READ[k]?.read(v, last) : undefined;
            return (
              <div key={k} className="rounded border border-zinc-800 p-2">
                <div className="flex items-baseline gap-2 text-xs">
                  <span className="truncate text-zinc-300" title={d.formula}>{d.ko}</span>
                  <span className="ml-auto font-mono text-sm text-zinc-100">{fmt(v, digits)}</span>
                  <span className="font-mono text-[11px] text-zinc-500" title="5거래일 전 대비">{typeof v === "number" && typeof p5 === "number" ? `${v - p5 >= 0 ? "+" : ""}${fmt(v - p5, digits)}` : ""}</span>
                  {s && <span className={`rounded px-1 font-mono text-[10px] ${pctileTone(s.pctile)}`} title={`기간 최소 ${fmt(s.min, digits)} · 평균 ${fmt(s.mean, digits)} · 최대 ${fmt(s.max, digits)}`}>{s.pctile.toFixed(0)}%ile</span>}
                </div>
                {read && <div className="truncate text-[11px] text-zinc-400" title={READ[k].rule(last!)}>{read}</div>}
                <Mini dates={dates} data={rows.map((r) => (typeof r[k] === "number" ? (r[k] as number) : null))} color={color} levels={levels[k] ?? []} digits={digits} />
              </div>
            );
          })}
        </div>
      </Panel>

      {flow.data && flow.data.n > 0 && (
        <div className="grid gap-3 xl:grid-cols-2">
          <Panel title={`지표 × ${bench.name} 수익률 순위상관 (${flow.data.range[0]} ~ ${flow.data.range[1]})`}>
            <CorrHeatmap rows={flow.data.vs_returns.rows.map(name)} cols={flow.data.vs_returns.cols} matrix={flow.data.vs_returns.matrix} height={520} left={130} />
            <div className="text-[11px] text-zinc-500">
              스피어만 순위상관 (지표 값이 클수록 수익률도 큰지). 과거 20일·당일은 지표가 시장을 얼마나 따라가는지, 이후 5일·20일은 그날 값이 이후 수익률과 어떤 관계였는지를 봅니다.
              이후 구간은 서로 겹쳐 표본이 독립이 아니므로 참고용이며, 매매 신호가 아닙니다.
            </div>
          </Panel>
          <Panel title="지표 간 순위상관">
            <CorrHeatmap rows={flow.data.between.rows.map(name)} matrix={flow.data.between.matrix} height={520} left={130} />
            <div className="text-[11px] text-zinc-500">서로 상관이 1에 가까운 지표는 같은 정보를 담고 있습니다 (하나만 봐도 됨). 상관이 낮은 지표 조합이 서로 다른 시장 상태를 보여줍니다.</div>
          </Panel>
        </div>
      )}
    </div>
  );
}
