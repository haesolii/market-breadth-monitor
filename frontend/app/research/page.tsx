"use client";
import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import { Err, Panel, Select } from "@/components/bits";
import { Input } from "@/components/ui/input";
import { useApi, type Status } from "@/lib/api";
import { downloadCSV } from "@/lib/csv";
import { ALL_DEFS, defOf, fmt } from "@/lib/defs";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });
const H = ["1", "3", "5", "10", "20"];

type St = { n: number; mean?: number; median?: number; win_rate?: number; max?: number; min?: number; std?: number; p_vs_baseline?: number | null; hist?: { counts: number[]; edges: number[] } };
type Res = {
  source: string; range: [string, string]; n_days: number; n_events: number;
  events: Record<string, number | string | null>[]; stats: Record<string, St>; baseline: Record<string, St>;
  excursion?: { sessions: number; mae: St; mfe: St };
};

const pct = (v: number | null | undefined, d = 2) => (v === null || v === undefined ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(d)}%`);
const tone = (v: number | null | undefined) => (v === null || v === undefined ? "text-zinc-600" : v > 0 ? "text-emerald-400" : v < 0 ? "text-red-400" : "");

export default function Research() {
  const { data: st } = useApi<Status>("/api/status");
  const [metric, setMetric] = useState("bear");
  const [op, setOp] = useState(">=");
  const [preset, setPreset] = useState("100");
  const [custom, setCustom] = useState("200");
  const [mode, setMode] = useState("independent");
  const [gap, setGap] = useState(5);
  const [source, setSource] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [h, setH] = useState("5");
  const [day, setDay] = useState<string | null>(null);
  const [metric2, setMetric2] = useState("");
  const [op2, setOp2] = useState("<=");
  const [threshold2, setThreshold2] = useState("20");

  const threshold = preset === "custom" ? custom : preset;
  const and = metric2 !== "" && threshold2 !== "" && Number.isFinite(Number(threshold2));
  const isBB = metric === "bull" || metric === "bear";
  const sources = (isBB ? st?.breadth20_sources : st?.monitor_sources) ?? [];
  const src = sources.includes(source) ? source : "";
  const effSrc = src || (isBB ? st?.default_breadth20 : st?.default_monitor) || "";
  const benches = useApi<{ symbol: string; name: string }[]>("/api/benchmarks");
  const [benchSel, setBenchSel] = useState("");
  const bench = benchSel || st?.source_info[effSrc]?.benchmark || "^GSPC";
  const benchName = benches.data?.find((b) => b.symbol === bench)?.name ?? bench;
  const url = `/api/research?benchmark=${encodeURIComponent(bench)}&metric=${metric}&op=${encodeURIComponent(op)}&threshold=${threshold}&mode=${mode}&gap=${gap}${src ? `&source=${src}` : ""}${start ? `&start=${start}` : ""}${end ? `&end=${end}` : ""}${and ? `&metric2=${metric2}&op2=${encodeURIComponent(op2)}&threshold2=${threshold2}` : ""}`;
  const { data, error, loading } = useApi<Res>(Number.isFinite(Number(threshold)) ? url : null);
  const d2 = metric2 ? defOf(metric2) : undefined;
  const fwd = useApi<Record<string, number | null>>(day ? `/api/research/day?date=${day}&benchmark=${encodeURIComponent(bench)}` : null);
  const d = defOf(metric)!;

  const hist = data?.stats[h]?.hist;
  const histOpt = useMemo(() => hist && {
    backgroundColor: "transparent", animation: false,
    grid: { left: 40, right: 10, top: 20, bottom: 40 },
    // Short labels (bin centre) so they never collide; the full range is in the tooltip.
    tooltip: { trigger: "axis", formatter: (p: { dataIndex: number; value: number }[]) => `${hist.edges[p[0].dataIndex].toFixed(1)}% ~ ${hist.edges[p[0].dataIndex + 1].toFixed(1)}%: ${p[0].value}건` },
    xAxis: { type: "category", data: hist.counts.map((_, i) => `${((hist.edges[i] + hist.edges[i + 1]) / 2).toFixed(1)}%`), axisLabel: { color: "#a1a1aa", fontSize: 10, hideOverlap: true } },
    yAxis: { type: "value", axisLabel: { color: "#a1a1aa" }, splitLine: { lineStyle: { color: "#27272a" } } },
    series: [{ type: "bar", data: hist.counts.map((c, i) => ({ value: c, itemStyle: { color: (hist.edges[i] + hist.edges[i + 1]) / 2 >= 0 ? "#10b981" : "#ef4444" } })) }],
  }, [hist]);

  return (
    <div className="space-y-3">
      <Panel title="과거 시장 통계 (Historical Research) — 극단값 이후 벤치마크 성과">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span>지표</span>
          <Select value={metric} onChange={(v) => { setMetric(v); setSource(""); }} options={ALL_DEFS.filter((x) => x.key !== "day34_diff" || true).map((x) => [x.key, `${x.ko} (${x.en})`])} />
          <Select value={op} onChange={setOp} options={[[">=", "≥ 이상"], ["<=", "≤ 이하"]]} />
          <Select value={preset} onChange={setPreset} options={[["50", "50"], ["75", "75"], ["100", "100"], ["150", "150"], ["custom", "사용자 지정 (Custom)"]]} />
          {preset === "custom" && <Input className="h-7 w-24 text-xs" value={custom} onChange={(e) => setCustom(e.target.value)} />}
          <span className="ml-2">그리고 (AND)</span>
          <Select value={metric2} onChange={setMetric2} options={[["", "두 번째 조건 없음"], ...ALL_DEFS.filter((x) => x.key !== metric).map((x) => [x.key, x.ko] as [string, string])]} />
          {metric2 && <>
            <Select value={op2} onChange={setOp2} options={[[">=", "≥ 이상"], ["<=", "≤ 이하"]]} />
            <Input className="h-7 w-20 text-xs" value={threshold2} onChange={(e) => setThreshold2(e.target.value)} />
          </>}
          <span className="ml-2">이벤트 처리</span>
          <Select value={mode} onChange={setMode} options={[["independent", "매일 독립 사건 (Independent)"], ["cluster", "연속 발생은 하나로 묶기 (Cluster)"]]} />
          {mode === "cluster" && <>
            <span>묶음 간격(거래일)</span>
            <Input type="number" className="h-7 w-16 text-xs" value={gap} min={1} max={60} onChange={(e) => setGap(Number(e.target.value) || 1)} />
          </>}
          <span className="ml-2">소스</span>
          <Select value={src} onChange={setSource} options={[["", "기본"], ...sources.map((s) => [s, st?.source_info[s]?.short ?? s] as [string, string])]} />
          <span className="ml-2">벤치마크</span>
          <Select value={benchSel} onChange={setBenchSel} options={[["", `자동 (${st?.source_info[effSrc]?.benchmark ?? "^GSPC"})`], ...(benches.data ?? []).map((b) => [b.symbol, b.name] as [string, string])]} />
          <span className="ml-2">기간</span>
          <Input type="date" className="h-7 w-36 text-xs" value={start} onChange={(e) => setStart(e.target.value)} />
          <Input type="date" className="h-7 w-36 text-xs" value={end} onChange={(e) => setEnd(e.target.value)} />
        </div>
        <div className="mt-2 text-[11px] text-zinc-500">
          조건: <b>{d.ko}</b> {op} {threshold}{and && d2 && <> 그리고 <b>{d2.ko}</b> {op2} {threshold2}</>} · 벤치마크: <b>{benchName}</b> · 이벤트 당일 종가 기준 이후 수익률 · “기준”은 같은 기간 전체 거래일 평균 (비교용).
        </div>
      </Panel>
      <Err error={error} />
      {loading && <div className="text-xs text-zinc-500">계산 중…</div>}
      {data && (
        <>
          <Panel title={<>결과: 이벤트 {data.n_events}건 / 분석일 {data.n_days}일 <span className="text-zinc-500">({data.range[0]} ~ {data.range[1]}, {data.source})</span></>}>
            {data.n_events < 30 && <div className="mb-2 rounded bg-amber-950 px-2 py-1 text-xs text-amber-300">⚠ 표본이 적습니다 (n = {data.n_events} &lt; 30). 평균·p값 모두 신뢰하기 어렵습니다.</div>}
            {mode === "independent" && data.n_events > 1 && (
              <div className="mb-2 rounded bg-zinc-900 px-2 py-1 text-xs text-zinc-400">
                ⓘ “매일 독립 사건”은 연속된 날을 각각 세므로 이후 수익률 구간이 겹칩니다 — 실제 독립 표본은 n보다 적고 p값은 실제보다 작게 나옵니다.
                <button className="ml-1 text-sky-400 underline" onClick={() => setMode("cluster")}>연속 발생 묶기로 보기</button>
              </div>
            )}
            <div className="overflow-x-auto">
              <table className="w-full font-mono text-xs">
                <thead className="text-zinc-400"><tr>
                  <th className="text-left">후속 기간</th><th>표본 수 (n)</th><th>평균</th><th>중앙값</th><th>상승 마감 비율</th><th>최대</th><th>최소</th><th>표준편차</th>
                  <th className="border-l border-zinc-800">기준 평균</th><th>기준 상승비율</th><th>p값</th>
                </tr></thead>
                <tbody>
                  {H.map((k) => {
                    const s = data.stats[k], b = data.baseline[k];
                    return (
                      <tr key={k} className={`cursor-pointer text-center hover:bg-zinc-900 ${h === k ? "bg-zinc-900" : ""}`} onClick={() => setH(k)}>
                        <td className="text-left">{k}거래일</td><td>{s?.n ?? 0}</td>
                        <td className={tone(s?.mean)}>{pct(s?.mean)}</td><td className={tone(s?.median)}>{pct(s?.median)}</td>
                        <td>{s?.win_rate !== undefined ? `${s.win_rate.toFixed(1)}%` : "—"}</td>
                        <td className={tone(s?.max)}>{pct(s?.max)}</td><td className={tone(s?.min)}>{pct(s?.min)}</td><td>{s?.std ? s.std.toFixed(2) : "—"}</td>
                        <td className="border-l border-zinc-800">{pct(b?.mean)}</td><td>{b?.win_rate !== undefined ? `${b.win_rate.toFixed(1)}%` : "—"}</td>
                        <td title="Welch t-검정 (이벤트 이후 수익률 vs 같은 기간 전체 거래일) — 겹치는 구간·적은 표본에선 과대평가됨. 5개 기간을 동시에 보므로 하나쯤은 우연히 0.05 미만이 나올 수 있음 (엄격히 보려면 0.01 미만)"
                          className={s?.p_vs_baseline !== null && s?.p_vs_baseline !== undefined && s.p_vs_baseline < 0.05 && data.n_events >= 30 && mode === "cluster" ? "text-sky-400" : ""}>{s?.p_vs_baseline?.toFixed(3) ?? "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {data.excursion && data.excursion.mae.n > 0 && (
              <div className="mt-2 font-mono text-xs text-zinc-400" title="이벤트 당일 종가 대비, 이후 거래일 종가 중 가장 낮은(MAE) / 가장 높은(MFE) 값">
                이후 {data.excursion.sessions}거래일 안의 최대 낙폭 (MAE): 평균 <span className={tone(data.excursion.mae.mean)}>{pct(data.excursion.mae.mean)}</span> · 중앙값 <span className={tone(data.excursion.mae.median)}>{pct(data.excursion.mae.median)}</span> · 최악 <span className="text-red-400">{pct(data.excursion.mae.min)}</span>
                <span className="mx-2 text-zinc-700">|</span>
                최대 상승폭 (MFE): 평균 <span className={tone(data.excursion.mfe.mean)}>{pct(data.excursion.mfe.mean)}</span> · 중앙값 <span className={tone(data.excursion.mfe.median)}>{pct(data.excursion.mfe.median)}</span> · 최고 <span className="text-emerald-400">{pct(data.excursion.mfe.max)}</span>
              </div>
            )}
          </Panel>
          <div className="grid gap-3 xl:grid-cols-2">
            <Panel title={`수익률 분포 (${h}거래일 후)`}>
              {histOpt ? <ReactECharts option={histOpt} style={{ height: 300 }} theme="dark" /> : <div className="text-xs text-zinc-500">표본 없음</div>}
            </Panel>
            <Panel title="이벤트 목록 (과거 유사 구간)" right={<button className="text-xs text-sky-400" onClick={() => downloadCSV(`events_${metric}_${threshold}.csv`, data.events)}>CSV 다운로드</button>}>
              <div className="max-h-80 overflow-auto">
                <table className="w-full font-mono text-xs">
                  <thead className="sticky top-0 bg-zinc-900 text-zinc-400"><tr><th className="text-left">날짜</th><th>값</th>{and && <th>값 2</th>}<th>{benchName}</th>{H.map((k) => <th key={k}>{k}일</th>)}<th title="20거래일 안 최대 낙폭">MAE</th><th title="20거래일 안 최대 상승폭">MFE</th></tr></thead>
                  <tbody>
                    {[...data.events].reverse().map((e) => (
                      <tr key={String(e.date)} className={`cursor-pointer text-center hover:bg-zinc-900 ${day === e.date ? "bg-zinc-800" : ""}`} onClick={() => setDay(String(e.date))}>
                        <td className="text-left">{String(e.date)}</td><td>{fmt(e.value, 2)}</td>{and && <td>{fmt(e.value2, 2)}</td>}<td>{fmt(e.close, 2)}</td>
                        {H.map((k) => { const v = e[`r${k}`] as number | null; return <td key={k} className={tone(v)}>{pct(v, 1)}</td>; })}
                        <td className={tone(e.mae20 as number | null)}>{pct(e.mae20 as number | null, 1)}</td><td className={tone(e.mfe20 as number | null)}>{pct(e.mfe20 as number | null, 1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {day && fwd.data && (
                <div className="mt-2 rounded border border-zinc-800 p-2 font-mono text-xs">
                  {day} 이후 {benchName}: {H.map((k) => <span key={k} className={`mr-3 ${tone(fwd.data![`r${k}`])}`}>{k}일 {pct(fwd.data![`r${k}`])}</span>)}
                </div>
              )}
            </Panel>
          </div>
        </>
      )}
    </div>
  );
}
