"use client";
import { useMemo, useState } from "react";
import { DayDetail } from "@/components/DayDetail";
import { Err, Kpi, Panel, RangePicker, useSource } from "@/components/bits";
import { TimeChart } from "@/components/TimeChart";
import { LIVE_MS, useApi, useBench, type Series } from "@/lib/api";
import { READ, bearLv, defOf, fmt } from "@/lib/defs";

const n = (v: unknown) => (typeof v === "number" ? v : null);
const delta = (a: number | null, b: number | null) => (a === null || b === null ? "—" : `${a - b >= 0 ? "+" : ""}${fmt(a - b)}`);

export default function Overview() {
  const [src, srcSel, st] = useSource("breadth20");
  const [mmSrc, mmSel] = useSource("monitor");
  const b = useApi<Series>(src ? `/api/breadth20?source=${src}` : null, LIVE_MS);
  const mm = useApi<Series>(mmSrc ? `/api/monitor?source=${mmSrc}` : null, LIVE_MS);

  const [range, setRange] = useState(126);
  const [sel, setSel] = useState<string | null>(null);

  const rows = useMemo(() => b.data?.rows ?? [], [b.data]);
  const last = rows.at(-1), prev = rows.at(-2);
  const m = mm.data?.rows.at(-1), mp = mm.data?.rows.at(-2);
  const view = useMemo(() => (range ? rows.slice(-range) : rows), [rows, range]);
  const dates = view.map((r) => String(r.date));
  const bull = n(last?.bull), bear = n(last?.bear);
  const bench = useBench(st?.source_info[src]?.benchmark ?? "^GSPC");
  const bear100 = last ? bearLv(last as Record<string, number | null>, 2) : 100;

  const series = useMemo(() => [
    { name: "Bull (20%↑)", data: view.map((r) => n(r.bull)), color: "#10b981" },
    { name: "Bear (20%↓)", data: view.map((r) => n(r.bear)), color: "#ef4444", mirror: true },
  ], [view]);
  const spyData = useMemo(() => (bench.map ? dates.map((d) => bench.map!.get(d) ?? null) : undefined), [bench.map, dates]);

  const mmKpi = (key: string, digits = 0) => {
    const d = defOf(key)!, v = m?.[key];
    const read = m && typeof v === "number" ? READ[key]?.read(v, m as Record<string, number | null>) : undefined;
    return <Kpi key={key} label={<>{d.ko} <span className="text-zinc-600">({d.en})</span></>}
      value={fmt(m?.[key], digits)} tone={d.kind === "down" ? "down" : d.kind === "up" ? "up" : "flat"}
      sub={<>전일 {fmt(mp?.[key], digits)}{read && <div className="text-zinc-300" title={`기준: ${READ[key].rule(m as Record<string, number | null>)}`}>{read}</div>}</>} />;
  };

  return (
    <div className="space-y-3">
      <Err error={b.error} />
      <Panel title="20% 급등락 (20% Bull/Bear Study) — 최신" right={<>{srcSel}</>}>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
          <Kpi label="Bull Count (20% 급등)" value={fmt(bull)} tone="up" sub={`전일 대비 ${delta(bull, n(prev?.bull))}`} />
          <Kpi label="Bear Count (20% 급락)" value={fmt(bear)} tone="down" sub={`전일 대비 ${delta(bear, n(prev?.bear))}`} />
          <Kpi label="순 시장 폭 (Net Breadth)" value={bull !== null && bear !== null ? `${bull - bear >= 0 ? "+" : ""}${bull - bear}` : "—"} tone={bull !== null && bear !== null ? (bull >= bear ? "up" : "down") : "flat"}
            sub={`전일 ${prev ? fmt(n(prev.bull)! - n(prev.bear)!) : "—"}`} />
          <Kpi label="Bull/Bear 비율 (Ratio)" value={bull !== null && bear ? fmt(bull / bear, 2) : bear === 0 ? "N/A (Bear 0)" : "—"} />
          <Kpi label="마지막 데이터 날짜 (Last date)" value={<span className="text-lg">{String(last?.date ?? "—")}</span>} sub={`기대 거래일 ${st?.sources[src]?.expected ?? st?.expected_session ?? "—"}${st?.sources[src]?.provisional ? " · 장중 잠정" : ""}`} />
        </div>
      </Panel>

      <Panel title="시장 모니터 핵심 지표 (Market Monitor)" right={<>{mmSel}<span className="text-xs text-zinc-500">{String(m?.date ?? "")} · 대상 {fmt(m?.eligible_universe_count)}종목</span></>}>
        {mm.error ? <Err error={mm.error} /> : (
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-8">
            {mmKpi("up4")}{mmKpi("down4")}{mmKpi("ratio5", 2)}{mmKpi("ratio10", 2)}
            {mmKpi("quarter_up25")}{mmKpi("quarter_down25")}{mmKpi("t2108", 1)}{mmKpi("day34_diff")}
          </div>
        )}
      </Panel>

      <div className="grid gap-3 xl:grid-cols-3">
        <Panel className="xl:col-span-2" title={`20% Bull / Bear 추이 + ${bench.name}`} right={<RangePicker value={range} onChange={setRange} />}>
          <TimeChart dates={dates} series={series} spy={spyData} onSelect={setSel} selected={sel} lowerName={bench.name}
            lines={[{ y: -bear100, label: `Bear ${bear100}`, color: "#f87171" }]} />
        </Panel>
        <DayDetail date={sel ?? (last ? String(last.date) : null)} mmSource={mmSrc} />
      </div>
    </div>
  );
}
