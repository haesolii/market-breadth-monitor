"use client";
import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import type { ECharts } from "echarts";
import { Err, Panel, RangePicker, Select, useSource } from "@/components/bits";
import { CorrHeatmap } from "@/components/CorrHeatmap";
import { useApi, useBench, type Series } from "@/lib/api";
import { READ, defOf, defaultLevels, fmt } from "@/lib/defs";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

type Stat = { key: string; last: number; first: number; min: number; max: number; mean: number; pctile: number };
type Flow = { source: string; benchmark: string; range: string[]; n: number; stats: Stat[]; score: [string, number][];
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

type Lag = { metric: string; n: number; lags: number[]; corr: (number | null)[]; peak: { lag: number; corr: number } | null;
  dates: string[]; roll: { r0: (number | null)[]; r20: (number | null)[] }; window: number };
const SCORE = "종합 점수";
const label = (k: string) => (k === "score" ? SCORE : defOf(k)?.ko ?? k);
const TIP = { backgroundColor: "#18181b", borderColor: "#3f3f46", textStyle: { color: "#e4e4e7", fontSize: 11 } };
const AX = { axisLabel: { color: "#71717a", fontSize: 10 }, axisLine: { lineStyle: { color: "#3f3f46" } }, splitLine: { lineStyle: { color: "#27272a" } } };

/** Market health 0-100 over time: 50 = an ordinary day for this market (trailing 1-year percentiles). */
function ScoreChart({ dates, score }: { dates: string[]; score: Map<string, number> }) {
  const option = useMemo(() => ({
    backgroundColor: "transparent", animation: false, grid: { left: 44, right: 8, top: 10, bottom: 22 },
    tooltip: { trigger: "axis", ...TIP, valueFormatter: (v: number) => (v == null ? "—" : Number(v).toFixed(0)) },
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    xAxis: { type: "category", data: dates, ...AX, axisLabel: { ...AX.axisLabel, hideOverlap: true }, splitLine: { show: false } },
    yAxis: { type: "value", min: 0, max: 100, interval: 25, ...AX },
    visualMap: { show: false, pieces: [{ lt: 30, color: "#ef4444" }, { gte: 30, lt: 70, color: "#a1a1aa" }, { gte: 70, color: "#10b981" }] },
    series: [{ name: SCORE, type: "line", data: dates.map((d) => score.get(d) ?? null), showSymbol: false, connectNulls: true, lineStyle: { width: 2 },
      markLine: { symbol: "none", silent: true, label: { show: false }, data: [30, 50, 70].map((y) => ({ yAxis: y, lineStyle: { color: "#52525b", type: "dashed" as const, width: 1 } })) } }],
  }), [dates, score]);
  return <ReactECharts option={option} notMerge style={{ height: 170 }} theme="dark" onChartReady={connect} />;
}

/** Which day's benchmark move the indicator lines up with (lag), and whether that relation is stable (rolling). */
function LeadLag({ src, keys, benchName }: { src: string; keys: string[]; benchName: string }) {
  const [metric, setMetric] = useState("score");
  const [days, setDays] = useState(756);
  const { data, error } = useApi<Lag & { benchmark: string }>(`/api/research/leadlag?source=${src}&metric=${metric}&days=${days}`);
  const bar = useMemo(() => data && ({
    backgroundColor: "transparent", animation: false, grid: { left: 44, right: 10, top: 16, bottom: 36 },
    tooltip: { trigger: "axis", ...TIP, formatter: (p: { name: string; value: number }[]) => {
      const k = Number(p[0].name);
      return `시차 ${k > 0 ? "+" : ""}${k}: t${k - 5 >= 0 ? "+" : ""}${k - 5} ~ t${k >= 0 ? "+" : ""}${k} 5거래일 수익률<br/><b>상관 ${p[0].value ?? "—"}</b>`;
    } },
    xAxis: { type: "category", data: data.lags.map(String), name: "시차 (거래일, + = 지표 이후)", nameLocation: "middle", nameGap: 24, nameTextStyle: { color: "#71717a", fontSize: 10 }, ...AX, splitLine: { show: false } },
    yAxis: { type: "value", min: -1, max: 1, ...AX },
    series: [{ type: "bar", barCategoryGap: "20%", data: data.corr.map((v, i) => ({ value: v, itemStyle: { color: v == null ? "#3f3f46" : v >= 0 ? "#10b981" : "#ef4444", borderRadius: 2, opacity: data.lags[i] >= 5 ? 1 : 0.5 } })) }],
  }), [data]);
  const roll = useMemo(() => data && ({
    backgroundColor: "transparent", animation: false, grid: { left: 44, right: 10, top: 28, bottom: 22 },
    legend: { top: 0, textStyle: { color: "#a1a1aa", fontSize: 11 } },
    tooltip: { trigger: "axis", ...TIP, valueFormatter: (v: number) => (v == null ? "—" : Number(v).toFixed(2)) },
    xAxis: { type: "category", data: data.dates, ...AX, axisLabel: { ...AX.axisLabel, hideOverlap: true }, splitLine: { show: false } },
    yAxis: { type: "value", min: -1, max: 1, ...AX },
    series: [["r0", "당일 수익률", "#38bdf8"], ["r20", "이후 20일 수익률", "#f59e0b"]].map(([k, n, c]) => ({
      name: n, type: "line", data: data.roll[k as "r0" | "r20"], showSymbol: false, lineStyle: { color: c, width: 2 }, itemStyle: { color: c },
      markLine: { symbol: "none", silent: true, label: { show: false }, data: [{ yAxis: 0, lineStyle: { color: "#52525b", width: 1 } }] } })),
  }), [data]);
  return (
    <Panel title={`선행·후행 분석: ${label(metric)} × ${benchName}`} right={<>
      <Select value={metric} onChange={setMetric} options={["score", ...keys].map((k) => [k, label(k)] as [string, string])} />
      <Select value={String(days)} onChange={(v) => setDays(Number(v))} options={[["252", "1년"], ["756", "3년"], ["0", "전체"]]} />
    </>}>
      <Err error={error} />
      {data && bar && roll && (
        <div className="grid gap-3 xl:grid-cols-2">
          <div>
            <div className="text-xs text-zinc-400">시차별 순위상관 {data.peak && <span className="text-zinc-200">· 가장 강한 시차 {data.peak.lag > 0 ? "+" : ""}{data.peak.lag}일 ({data.peak.corr.toFixed(2)})</span>}</div>
            <ReactECharts option={bar} notMerge style={{ height: 240 }} theme="dark" />
            <div className="text-[11px] text-zinc-500">
              막대 k = 그날 지표 값과 (t+k−5 ~ t+k) 5거래일 지수 수익률의 상관. 0 이하 = 이미 지난 움직임을 반영(후행), +5 이상(진한 막대) = 그 뒤의 움직임(선행).
              선행 막대가 후행 막대보다 확실히 클 때만 지표가 시장을 앞선다고 볼 수 있습니다.
            </div>
          </div>
          <div>
            <div className="text-xs text-zinc-400">{data.window}거래일 이동 상관계수 (관계가 언제 바뀌었는지)</div>
            <ReactECharts option={roll} notMerge style={{ height: 240 }} theme="dark" />
            <div className="text-[11px] text-zinc-500">선이 0을 오가면 관계가 안정적이지 않다는 뜻입니다. 이후 20일 선은 미래 수익률을 쓰므로 최근 20일은 비어 있습니다.</div>
          </div>
        </div>
      )}
    </Panel>
  );
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
  const name = label;
  const score = useMemo(() => new Map(flow.data?.score ?? []), [flow.data]);
  const sNow = stats.get("score");
  const benchData = useMemo(() => (bench.map ? dates.map((d) => bench.map!.get(d) ?? null) : []), [bench.map, dates]);

  return (
    <div className="space-y-3">
      <Panel title="지표 흐름 (Indicator flow)" right={<>{srcSel}<RangePicker value={range} onChange={setRange} /></>}>
        <div className="text-[11px] text-zinc-500">
          모든 차트가 같은 날짜 축을 공유합니다 (한 차트에 마우스를 올리면 전부 같은 날짜를 가리킴). 점선 = 기본 강조 기준. 백분위 = 현재 값이 선택 기간 안에서 몇 % 위치인지 (90 이상 / 10 이하는 기간 내 극단).
        </div>
        <Err error={mm.error ?? flow.error} />
        <div className="mt-2">
          <div className="flex flex-wrap items-baseline gap-2 text-xs text-zinc-300">
            <span>{SCORE} (시장 건강도 0~100)</span>
            {sNow && <span className={`font-mono text-sm ${sNow.last >= 70 ? "text-emerald-400" : sNow.last < 30 ? "text-red-400" : "text-zinc-100"}`}>{sNow.last.toFixed(0)}</span>}
            <span className="text-[11px] text-zinc-500">16개 지표 각각의 최근 1년 백분위 평균 (하락형 지표는 뒤집음) · 50 = 이 시장의 보통 날 · 70↑ 폭넓은 강세 · 30↓ 폭넓은 약세 · 그날까지의 데이터만 사용</span>
          </div>
          <ScoreChart dates={dates} score={score} />
        </div>
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
                  {s && <span className={`rounded px-1 font-mono text-[10px] ${pctileTone(d.kind === "down" ? 100 - s.pctile : s.pctile)}`} title={`기간 최소 ${fmt(s.min, digits)} · 평균 ${fmt(s.mean, digits)} · 최대 ${fmt(s.max, digits)}`}>{s.pctile.toFixed(0)}%ile</span>}
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
      {src && <LeadLag src={src} keys={KEYS} benchName={bench.name} />}
    </div>
  );
}
