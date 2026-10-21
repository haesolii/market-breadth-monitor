"use client";
import { useMemo, useState } from "react";
import { DayDetail } from "@/components/DayDetail";
import { Err, Panel, RangePicker, Select, useSource } from "@/components/bits";
import { TimeChart, type S } from "@/components/TimeChart";
import { Input } from "@/components/ui/input";
import { LIVE_MS, useApi, useBench, type Series } from "@/lib/api";
import { downloadCSV } from "@/lib/csv";
import { READ, bearLv, fmt } from "@/lib/defs";
import { useSetting } from "@/lib/settings";

const n = (v: unknown) => (typeof v === "number" ? v : null);
const US_LINES = [50, 100, 150];
const palette = ["#fca5a5", "#f87171", "#dc2626", "#991b1b", "#7f1d1d"];

export default function BullBear() {
  const [src, srcSel, st] = useSource("breadth20", true);
  const b = useApi<Series>(src ? `/api/breadth20?source=${src}` : null, LIVE_MS);
  const [cmp, setCmp] = useState("");
  const c = useApi<Series>(cmp ? `/api/breadth20?source=${cmp}` : null);
  const bench = useBench(st?.source_info[src]?.benchmark ?? "^GSPC");
  const [range, setRange] = useState(252);
  const [sel, setSel] = useState<string | null>(null);
  const presets = st?.source_info[src]?.bear_levels ?? US_LINES;
  const [on, setOn] = useSetting<number[]>("bb.bearOn", [0, 1, 2]);  // which of the market's 3 lines
  const [customs, setCustoms] = useSetting<number[]>("bb.bearCustom", []);
  const [custom, setCustom] = useState("");

  const rows = useMemo(() => b.data?.rows ?? [], [b.data]);
  const view = useMemo(() => (range ? rows.slice(-range) : rows), [rows, range]);
  const dates = useMemo(() => view.map((r) => String(r.date)), [view]);
  const series = useMemo(() => {
    const s: S[] = [
      { name: "Bull (20%↑)", data: view.map((r) => n(r.bull)), color: "#10b981" },
      { name: "Bear (20%↓)", data: view.map((r) => n(r.bear)), color: "#ef4444", mirror: true },
    ];
    if (cmp && c.data) {
      const m = new Map(c.data.rows.map((r) => [String(r.date), r]));
      s.push({ name: `Bull · ${cmp}`, data: dates.map((d) => n(m.get(d)?.bull)), color: "#a7f3d0", type: "line" });
      s.push({ name: `Bear · ${cmp}`, data: dates.map((d) => n(m.get(d)?.bear)), color: "#fecaca", type: "line", mirror: true });
    }
    return s;
  }, [view, dates, cmp, c.data]);
  const spyData = useMemo(() => (bench.map ? dates.map((d) => bench.map!.get(d) ?? null) : undefined), [bench.map, dates]);
  const lines = useMemo(() => [...on.map((i) => presets[i]), ...customs], [on, customs, presets]);
  const mk = useMemo(() => [...lines].sort((a, z) => a - z).map((y, i) => ({ y: -y, label: `Bear ${y}`, color: palette[i % palette.length] })), [lines]);
  const toggle = (i: number) => setOn(on.includes(i) ? on.filter((x) => x !== i) : [...on, i]);
  const others = (st?.breadth20_sources ?? []).filter((s) => s !== src);
  const recent = [...view].reverse().slice(0, 30);

  return (
    <div className="space-y-3">
      <Err error={b.error} />
      <Panel
        title="20% 급등락 히스토그램 (Historical Breadth Chart)"
        right={
          <>
            {srcSel}
            <Select value={cmp} onChange={setCmp} options={[["", "비교 소스 없음"], ...others.map((s) => [s, `비교: ${st?.source_info[s]?.short ?? s}`] as [string, string])]} />
            <span className="text-xs text-zinc-400" title="시장별 기준선: 미국 원본 50·100·150이 과거에 나타난 빈도(거래일의 6.9%·2.0%·1.1%)와 같은 빈도로 나타나는 수">Bear 기준선:</span>
            {presets.map((v, i) => (
              <label key={i} className="flex items-center gap-1 text-xs"><input type="checkbox" checked={on.includes(i)} onChange={() => toggle(i)} />{v}</label>
            ))}
            <Input className="h-7 w-20 text-xs" placeholder="사용자" value={custom} onChange={(e) => setCustom(e.target.value)}
              onKeyDown={(e) => { const v = Number(custom); if (e.key === "Enter" && v > 0 && !customs.includes(v)) { setCustoms([...customs, v]); setCustom(""); } }} />
            {customs.map((v) => (
              <button key={v} className="rounded bg-zinc-800 px-1 text-xs" onClick={() => setCustoms(customs.filter((x) => x !== v))}>{v} ✕</button>
            ))}
            <RangePicker value={range} onChange={setRange} />
          </>
        }
      >
        <TimeChart dates={dates} series={series} spy={spyData} lines={mk} onSelect={setSel} selected={sel} height={520} yName="종목 수" lowerName={bench.name} />
        <div className="mt-1 text-[11px] text-zinc-500">
          녹색 = 20% 급등 종목 수, 빨간색(아래쪽) = 20% 급락 종목 수 · 차트를 클릭하면 날짜 상세가 표시됩니다(기본: 최근 거래일) · 표의 Bull/Bear 숫자에 마우스를 올리면 해석이 보입니다 · Bear 기준선은 시장마다 과거 데이터로 정한 값입니다 (미국 원본 50·100·150과 같은 빈도로 나타나는 수).
        </div>
      </Panel>
      <div className="grid gap-3 xl:grid-cols-2">
        <DayDetail date={sel ?? (rows.length ? String(rows.at(-1)!.date) : null)} />
        <Panel title="최근 30거래일" right={<button className="text-xs text-sky-400" onClick={() => downloadCSV(`breadth20_${src}.csv`, rows)}>CSV 다운로드</button>}>
          <table className="w-full font-mono text-xs">
            <thead className="text-zinc-500"><tr><th className="text-left">날짜</th><th>Bull</th><th>Bear</th><th>Net</th><th>Bull/Bear</th></tr></thead>
            <tbody>
              {recent.map((r) => {
                const bu = n(r.bull), be = n(r.bear);
                return (
                  <tr key={String(r.date)} className="cursor-pointer text-center hover:bg-zinc-900" onClick={() => setSel(String(r.date))}>
                    <td className="text-left">{String(r.date)}</td>
                    <td className="text-emerald-400" title={bu !== null ? READ.bull.read(bu, r as Record<string, number | null>) : undefined}>{fmt(bu)}</td>
                    <td title={be !== null ? READ.bear.read(be, r as Record<string, number | null>) : undefined} className={be !== null && be >= bearLv(r as Record<string, number | null>, 2) ? "bg-red-700 text-white" : "text-red-400"}>{fmt(be)}</td>
                    <td className={(bu ?? 0) - (be ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}>{bu !== null && be !== null ? bu - be : "—"}</td>
                    <td>{bu !== null && be ? fmt(bu / be, 2) : "N/A"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Panel>
      </div>
    </div>
  );
}
