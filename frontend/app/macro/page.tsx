"use client";
import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import { Err, Panel, Select } from "@/components/bits";
import { localTime } from "@/components/Shell";
import { TimeChart } from "@/components/TimeChart";
import { useApi, useBench, type Series } from "@/lib/api";
import { useSetting } from "@/lib/settings";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

type Flag = { code: string; label: string; level: "up" | "down" | "warn" | "stale"; strong: boolean };
type Card = {
  id: string; name: string; group: string; unit: string; good: "up" | "down" | "neutral";
  date?: string; monthly?: boolean; value?: number; prev?: number; chg?: number; chg_1y?: number | null; flags: Flag[];
};
type Macro = { cards: Card[]; groups: string[]; last_success?: string; last_error?: string };
type Hist = Record<string, [string, number][]>;

const YEARS: [string, number][] = [["1년", 1], ["3년", 3], ["10년", 10]];
const BADGE: Record<string, [string, string]> = {
  up: ["border border-emerald-500 text-emerald-300", "bg-emerald-600 text-white"],
  down: ["border border-red-500 text-red-300", "bg-red-600 text-white"],
  warn: ["border border-amber-500 text-amber-300", "bg-amber-500 text-black"],
  stale: ["border border-zinc-500 text-zinc-400", "bg-zinc-600 text-white"],
};

const digits = (u: string) => (u === "천 명" || u === "천 건" ? 0 : 2);
const num = (v: number | null | undefined, d: number) =>
  v === null || v === undefined ? "—" : v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const period = (c: Card) => (!c.date ? "—" : c.monthly ? `${c.date.slice(0, 4)}년 ${Number(c.date.slice(5, 7))}월` : c.date);
// Change of a rate/percent series is in percentage points.
const chgUnit = (u: string) => (u === "%" || u === "%p" ? "%p" : u);

function Chg({ v, c }: { v: number | null | undefined; c: Card }) {
  if (v === null || v === undefined) return <span className="text-zinc-600">—</span>;
  const good = c.good === "neutral" ? null : c.good === "up" ? v > 0 : v < 0;
  const col = v === 0 || good === null ? "text-zinc-300" : good ? "text-emerald-400" : "text-red-400";
  return <span className={col}>{v > 0 ? "+" : ""}{num(v, digits(c.unit))}{chgUnit(c.unit) && ` ${chgUnit(c.unit)}`}</span>;
}

function tone(flags: Flag[]) {
  const f = [...flags].sort((a, b) => +b.strong - +a.strong)[0];
  if (!f) return "border-zinc-800";
  return { down: f.strong ? "border-red-500 bg-red-950/40" : "border-red-700", up: "border-emerald-600", warn: "border-amber-500 bg-amber-950/30", stale: "border-zinc-600 opacity-60" }[f.level];
}

function Spark({ data, unit }: { data: [string, number][]; unit: string }) {
  const opt = useMemo(() => ({
    backgroundColor: "transparent", animation: false,
    grid: { left: 2, right: 2, top: 4, bottom: 2 },
    tooltip: { trigger: "axis", backgroundColor: "#18181b", borderColor: "#3f3f46", textStyle: { color: "#e4e4e7", fontSize: 11 },
      formatter: (p: { axisValue: string; value: number }[]) => `${p[0].axisValue}<br/><b>${num(p[0].value, digits(unit))} ${unit}</b>` },
    xAxis: { type: "category", data: data.map((d) => d[0]), show: false, boundaryGap: false },
    yAxis: { type: "value", scale: true, show: false },
    series: [{ type: "line", data: data.map((d) => d[1]), showSymbol: false, lineStyle: { color: "#38bdf8", width: 1.2 },
      areaStyle: { color: "rgba(56,189,248,0.08)" } }],
  }), [data, unit]);
  if (!data.length) return <div className="h-[70px]" />;
  return <ReactECharts option={opt} style={{ height: 70 }} theme="dark" />;
}

export default function MacroPage() {
  const m = useApi<Macro>("/api/macro", 10 * 60 * 1000);
  const [years, setYears] = useSetting("macro.years", 3);
  const since = useMemo(() => { const d = new Date(); d.setFullYear(d.getFullYear() - 10); return d.toISOString().slice(0, 10); }, []);
  const ids = (m.data?.cards ?? []).map((c) => c.id).join(",");
  const hist = useApi<Hist>(ids ? `/api/macro/history?ids=${ids}&since=${since}` : null);
  const [sel, setSel] = useState<Card | null>(null);

  const cutoff = useMemo(() => { const d = new Date(); d.setFullYear(d.getFullYear() - years); return d.toISOString().slice(0, 10); }, [years]);
  const cards = m.data?.cards ?? [];
  const flagged = cards.filter((c) => c.flags.some((f) => f.level !== "stale"));

  return (
    <div className="space-y-3">
      <Err error={m.error ?? m.data?.last_error ?? null} />
      {sel && <BigChart card={sel} onClose={() => setSel(null)} />}
      <Panel
        title="미국 매크로 지표 (Macro)"
        right={
          <>
            <span className="text-xs text-zinc-400">추이 기간</span>
            <div className="flex overflow-hidden rounded border border-zinc-700 text-xs">
              {YEARS.map(([l, y]) => (
                <button key={l} onClick={() => setYears(y)} className={`px-3 py-1 ${years === y ? "bg-sky-700 text-white" : "text-zinc-300 hover:bg-zinc-800"}`}>{l}</button>
              ))}
            </div>
            <span className="text-xs text-zinc-500">갱신 {localTime(m.data?.last_success)}</span>
          </>
        }
      >
        {flagged.length > 0 && (
          <div className="mb-3 flex flex-wrap items-center gap-1 text-xs">
            <span className="text-zinc-400">특이사항:</span>
            {flagged.flatMap((c) => c.flags.map((f) => (
              <button key={c.id + f.code} onClick={() => setSel(c)} className={`rounded px-1.5 ${BADGE[f.level][f.strong ? 1 : 0]}`}>{c.name}: {f.label}</button>
            )))}
          </div>
        )}
        {(m.data?.groups ?? []).map((g) => (
          <section key={g} className="mb-4">
            <h3 className="mb-1 text-xs font-semibold text-zinc-400">{g}</h3>
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-4">
              {cards.filter((c) => c.group === g).map((c) => (
                <button key={c.id} onClick={() => setSel(c)} className={`rounded border bg-zinc-950 p-2 text-left hover:bg-zinc-900 ${tone(c.flags)}`}>
                  <div className="flex items-baseline gap-1">
                    <span className="truncate text-xs text-zinc-300">{c.name}</span>
                    <span className="ml-auto shrink-0 text-[10px] text-zinc-500">{period(c)}</span>
                  </div>
                  <div className="font-mono text-xl font-semibold text-zinc-100">
                    {num(c.value, digits(c.unit))}<span className="ml-1 text-xs text-zinc-400">{c.unit}</span>
                  </div>
                  <div className="flex gap-3 font-mono text-[11px] text-zinc-500">
                    <span>직전 대비 <Chg v={c.chg} c={c} /></span>
                    <span>1년 전 대비 <Chg v={c.chg_1y} c={c} /></span>
                  </div>
                  <Spark data={(hist.data?.[c.id] ?? []).filter((d) => d[0] >= cutoff)} unit={c.unit} />
                  {c.flags.length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {c.flags.map((f) => <span key={f.code} className={`rounded px-1.5 text-[10px] ${BADGE[f.level][f.strong ? 1 : 0]}`}>{f.label}</span>)}
                    </div>
                  )}
                </button>
              ))}
            </div>
          </section>
        ))}
        <div className="text-[11px] text-zinc-500">
          출처: FRED (세인트루이스 연은) · 월간 지표는 해당 월 기준값(다음 달 발표) · 변화 색상: 경제에 좋은 방향 = 녹색, 나쁜 방향 = 빨간색, 중립 지표 = 회색 · 카드를 누르면 큰 차트 · 참고용이며 매매 신호가 아닙니다.
        </div>
      </Panel>
    </div>
  );
}

/** Full-history chart of one macro series, with S&P 500 or the US 20% Bear count underneath. */
function BigChart({ card, onClose }: { card: Card; onClose: () => void }) {
  const h = useApi<Hist>(`/api/macro/history?ids=${card.id}`);
  const [years, setYears] = useState(10);
  const [lower, setLower] = useState("spx");
  const spx = useBench("^GSPC");
  const bear = useApi<Series>(lower === "bear" ? "/api/breadth20?source=public_repo" : null);

  const view = useMemo(() => {
    const rows = h.data?.[card.id] ?? [];
    const cut = new Date(); cut.setFullYear(cut.getFullYear() - years);
    const from = years ? cut.toISOString().slice(0, 10) : "";
    const r = rows.filter((x) => x[0] >= from);
    return { dates: r.map((x) => x[0]), values: r.map((x) => x[1]) };
  }, [h.data, card.id, years]);

  // Lower panel: value on each macro date (last available on or before it).
  const lowerData = useMemo(() => {
    let m: Map<string, number> | null = null;
    if (lower === "spx") m = spx.map;
    else if (lower === "bear" && bear.data) m = new Map(bear.data.rows.map((r) => [String(r.date), r.bear as number]));
    if (!m) return undefined;
    const keys = [...m.keys()].sort();
    let j = 0, last: number | null = null;
    return view.dates.map((d) => {
      while (j < keys.length && keys[j] <= d) { last = m!.get(keys[j]) ?? last; j++; }
      return last;
    });
  }, [lower, spx.map, bear.data, view.dates]);

  return (
    <Panel
      title={<>{card.name} <span className="text-xs text-zinc-500">({card.unit || "지수"})</span></>}
      right={
        <>
          <div className="flex overflow-hidden rounded border border-zinc-700 text-xs">
            {([["1년", 1], ["3년", 3], ["10년", 10], ["전체", 0]] as [string, number][]).map(([l, y]) => (
              <button key={l} onClick={() => setYears(y)} className={`px-3 py-1 ${years === y ? "bg-sky-700 text-white" : "text-zinc-300 hover:bg-zinc-800"}`}>{l}</button>
            ))}
          </div>
          <Select value={lower} onChange={setLower} options={[["spx", "아래: S&P 500"], ["bear", "아래: 미국 20% Bear 수 (상장폐지 포함)"], ["none", "아래 패널 없음"]]} />
          <button className="text-xs text-zinc-400 hover:text-white" onClick={onClose}>닫기 ✕</button>
        </>
      }
    >
      <TimeChart dates={view.dates} series={[{ name: card.name, data: view.values, color: "#38bdf8", type: "line" }]}
        spy={lower === "none" ? undefined : lowerData} lowerName={lower === "bear" ? "미국 Bear 수" : "S&P 500"}
        lowerBar={lower === "bear"} lowerColor={lower === "bear" ? "#ef4444" : "#e4e4e7"} height={460} />
    </Panel>
  );
}
