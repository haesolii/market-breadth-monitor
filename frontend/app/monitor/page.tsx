"use client";
import { useMemo, useState } from "react";
import { Err, Panel, RangePicker, useSource } from "@/components/bits";
import { LevelsEditor } from "@/components/LevelsEditor";
import { TimeChart } from "@/components/TimeChart";
import { Input } from "@/components/ui/input";
import { LIVE_MS, useApi, useBench, type Series } from "@/lib/api";
import { downloadCSV } from "@/lib/csv";
import { BB_DEFS, DEFS, READ, US_N, cellClass, defOf, defaultLevels, fmt, type Levels } from "@/lib/defs";
import { useSetting } from "@/lib/settings";

const COLS = [...DEFS, ...BB_DEFS];
const n = (v: unknown) => (typeof v === "number" ? v : null);
const readOf = (k: string, r: Record<string, unknown>) => {
  const v = r[k];
  return READ[k] && typeof v === "number" ? READ[k].read(v, r as Record<string, number | null>) : undefined;
};

export default function Monitor() {
  const [src, srcSel, st] = useSource("monitor", true);
  const mm = useApi<Series>(src ? `/api/monitor?source=${src}` : null, LIVE_MS);
  // Comparison panel: the market's ETF by default (tradeable), or the index itself.
  const [benchKind, setBenchKind] = useSetting<"etf" | "index">("mm.benchKind", "etf");
  const bench = useBench(benchKind === "etf" ? st?.source_info[src]?.etf ?? "SPY" : st?.source_info[src]?.benchmark ?? "^GSPC");
  const [storedLevels] = useSetting<Levels | null>(`mm.levels.${src}`, null);
  const [metric, setMetric] = useState("t2108");
  const [range, setRange] = useState(252);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [limit, setLimit] = useState(120);
  const [editLevels, setEditLevels] = useState(false);

  const rows = useMemo(() => mm.data?.rows ?? [], [mm.data]);
  const filtered = useMemo(() => rows.filter((r) => (!from || String(r.date) >= from) && (!to || String(r.date) <= to)), [rows, from, to]);
  const table = useMemo(() => [...filtered].reverse(), [filtered]);
  const latest = rows.at(-1);
  const universeN = n(latest?.eligible_universe_count);
  const levels = storedLevels ?? defaultLevels(universeN);
  const chartRows = useMemo(() => (range && !from && !to ? filtered.slice(-range) : filtered), [filtered, range, from, to]);
  const dates = useMemo(() => chartRows.map((r) => String(r.date)), [chartRows]);
  const d = defOf(metric)!;
  const series = useMemo(() => {
    if (metric === "up4" || metric === "down4")
      return [
        { name: "4% 상승 (Up)", data: chartRows.map((r) => n(r.up4)), color: "#10b981" },
        { name: "4% 하락 (Down)", data: chartRows.map((r) => n(r.down4)), color: "#ef4444", mirror: true },
      ];
    const color = d.kind === "down" ? "#ef4444" : d.kind === "up" ? "#10b981" : "#38bdf8";
    return [{ name: `${d.ko} (${d.en})`, data: chartRows.map((r) => n(r[metric])), color, type: (d.kind === "up" || d.kind === "down" ? "bar" : "line") as "bar" | "line" }];
  }, [chartRows, metric, d]);
  const spyData = useMemo(() => (bench.map ? dates.map((x) => bench.map!.get(x) ?? null) : undefined), [bench.map, dates]);
  const info = st?.source_info[src];
  const lv = levels[metric] ?? d.levels;
  const lines = (d.kind === "up" || d.kind === "down" ? [lv[0], lv[1]] : [lv[0], lv[1]])
    .filter((v): v is number => v !== null)
    .map((y) => ({ y: metric === "down4" ? -y : y, label: `기준 ${y}`, color: "#a1a1aa" }));

  return (
    <div className="space-y-3">
      <Err error={mm.error} />
      <Panel
        title={<>지표 시계열: <span className="text-sky-400">{d.ko} ({d.en})</span></>}
        right={<>
          <span className="text-xs text-zinc-400">시장 (Universe)</span>{srcSel}
          <div className="flex overflow-hidden rounded border border-zinc-700 text-xs" title="아래 비교 패널">
            {(["etf", "index"] as const).map((k) => (
              <button key={k} onClick={() => setBenchKind(k)} className={`px-2 py-1 ${benchKind === k ? "bg-zinc-700 text-white" : "text-zinc-400 hover:bg-zinc-800"}`}>
                {k === "etf" ? "ETF" : "지수"}
              </button>
            ))}
          </div>
          <RangePicker value={range} onChange={setRange} /></>}
      >
        <TimeChart dates={dates} series={series} spy={spyData} lines={lines} height={400} lowerName={bench.name} />
        <div className="mt-1 text-[11px] text-zinc-500">
          {info?.label} · 아래 표의 지표 이름을 클릭하면 차트가 바뀝니다 · 기준선은 사용자 설정이며 매매 신호가 아닙니다.
        </div>
      </Panel>

      {latest && (
        <Panel title={<>지표 해석 (Stockbee 기준): <span className="font-mono text-sky-400">{String(latest.date)}</span></>}>
          <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {DEFS.map((c) => (
              <button key={c.key} onClick={() => setMetric(c.key)}
                className={`rounded border px-2 py-1.5 text-left text-xs ${metric === c.key ? "border-sky-700 bg-zinc-800/60" : "border-zinc-800 hover:bg-zinc-800/40"}`}>
                <div className="flex justify-between gap-2"><span className="text-zinc-400">{c.ko}</span>
                  <span className="font-mono text-zinc-200">{fmt(latest[c.key], c.kind === "ratio" || c.kind === "pct" ? 2 : 0)}</span></div>
                <div className="text-zinc-200">{readOf(c.key, latest) ?? "—"}</div>
                <div className="text-[10px] text-zinc-600">기준: {READ[c.key]?.rule(latest as Record<string, number | null>)}</div>
              </button>
            ))}
          </div>
          <div className="mt-2 text-[11px] text-zinc-500">
            가장 최근 거래일 값으로 자동 해석 · 종목 수 기준(미국 원문 300·500·1,000 등)은 시장 규모에 맞춰 환산 ({universeN?.toLocaleString("en-US") ?? "—"}종목 ÷ 미국 {US_N.toLocaleString("en-US")}종목 기준) · 아래 표 셀에 마우스를 올리면 그날의 해석이 보입니다.
          </div>
        </Panel>
      )}

      <Panel
        title="시장 모니터 히스토리 (Market Monitor History)"
        right={
          <>
            <span className="text-xs text-zinc-400">기간</span>
            <Input type="date" className="h-7 w-36 text-xs" value={from} onChange={(e) => setFrom(e.target.value)} />
            <span className="text-xs">~</span>
            <Input type="date" className="h-7 w-36 text-xs" value={to} onChange={(e) => setTo(e.target.value)} />
            <button className="text-xs text-sky-400" onClick={() => setEditLevels(!editLevels)}>{editLevels ? "강조 기준 닫기" : "강조 기준 설정"}</button>
            <button className="text-xs text-sky-400" onClick={() => downloadCSV(`market_monitor_${src}.csv`, filtered)}>CSV 다운로드</button>
          </>
        }
      >
        {editLevels && <div className="mb-2"><LevelsEditor market={src} label={info?.short ?? src} n={universeN} /></div>}
        <div className="max-h-[70vh] overflow-auto">
          <table className="w-full border-collapse font-mono text-xs">
            <thead className="sticky top-0 z-10 bg-zinc-900 text-zinc-300">
              <tr>
                <th className="px-2 py-1 text-left">날짜 (Date)</th>
                {COLS.map((c) => (
                  <th key={c.key} className={`cursor-pointer px-2 py-1 ${metric === c.key ? "text-sky-400" : ""}`} onClick={() => setMetric(c.key)}>
                    <span title={`${c.ko} (${c.en})`}>{c.short}</span>
                  </th>
                ))}
                <th className="px-2 py-1" title="해당 날짜 데이터가 있는 보통주 수 (eligible universe)">대상 종목</th>
              </tr>
            </thead>
            <tbody>
              {table.slice(0, limit).map((r) => (
                <tr key={String(r.date)} className="border-b border-zinc-900 text-center">
                  <td className="whitespace-nowrap px-2 py-0.5 text-left text-zinc-400">
                    {String(r.date)}
                    {st?.sources[src]?.provisional && String(r.date) === st.sources[src].latest_date && (
                      <span className="ml-1 rounded bg-sky-900 px-1 text-sky-200" title="장중 값으로 계산한 잠정치 — 장 마감 확정 후 다시 계산됩니다">잠정</span>
                    )}
                  </td>
                  {COLS.map((c) => (
                    <td key={c.key} title={readOf(c.key, r)} className={`px-2 py-0.5 ${cellClass(c, r[c.key], levels)}`}>{fmt(r[c.key], c.kind === "ratio" || c.kind === "pct" ? 2 : 0)}</td>
                  ))}
                  <td className="px-2 py-0.5 text-zinc-500">{fmt(r.eligible_universe_count)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {table.length > limit && (
            <button className="mt-2 w-full rounded border border-zinc-800 py-1 text-xs text-zinc-400" onClick={() => setLimit(limit + 250)}>
              더 보기 ({table.length - limit}행 남음)
            </button>
          )}
        </div>
        <div className="mt-2 text-[11px] text-zinc-500">
          녹색 = 상승 계열, 빨간색 = 하락 계열, 진한 색 = 강조 기준 초과 (“강조 기준 설정”에서 변경) · “—” = 값 없음.
        </div>
      </Panel>
    </div>
  );
}
