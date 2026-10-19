"use client";
import { useMemo, useState } from "react";
import { DayDetail } from "@/components/DayDetail";
import { Err, Panel, RangePicker, Select, useSource } from "@/components/bits";
import { TimeChart, type S } from "@/components/TimeChart";
import { Input } from "@/components/ui/input";
import { LIVE_MS, useApi, useBench, type Series } from "@/lib/api";
import { downloadCSV } from "@/lib/csv";
import { READ, cnt, fmt, scaleOf } from "@/lib/defs";
import { useSetting } from "@/lib/settings";

const n = (v: unknown) => (typeof v === "number" ? v : null);
const palette = ["#fca5a5", "#f87171", "#dc2626", "#991b1b", "#7f1d1d"];

export default function BullBear() {
  const [src, srcSel, st] = useSource("breadth20", true);
  const b = useApi<Series>(src ? `/api/breadth20?source=${src}` : null, LIVE_MS);
  const [cmp, setCmp] = useState("");
  const c = useApi<Series>(cmp ? `/api/breadth20?source=${cmp}` : null);
  const bench = useBench(st?.source_info[src]?.benchmark ?? "^GSPC");
  const [range, setRange] = useState(252);
  const [sel, setSel] = useState<string | null>(null);
  const [lines, setLines] = useSetting<number[]>("bb.bearLines", [50, 100, 150]);
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
  // Lines are set on the US scale (50/100/150) and drawn scaled to this market's universe size.
  const last = rows.at(-1) as Record<string, number | null> | undefined;
  const scaled = !!last && scaleOf(last) < 1;
  const mk = useMemo(() => [...lines].sort((a, z) => a - z).map((y, i) => {
    const v = last ? cnt(y, last) : y;
    return { y: -v, label: scaled ? `Bear ${v} (미국 ${y})` : `Bear ${y}`, color: palette[i % palette.length] };
  }), [lines, last, scaled]);

  const toggle = (v: number) => setLines(lines.includes(v) ? lines.filter((x) => x !== v) : [...lines, v]);
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
            <span className="text-xs text-zinc-400" title="미국 전체 기준 값 — 다른 시장은 종목 수 비율로 환산해 그립니다">Bear 기준선{scaled ? " (미국 기준)" : ""}:</span>
            {[50, 100, 150].map((v) => (
              <label key={v} className="flex items-center gap-1 text-xs"><input type="checkbox" checked={lines.includes(v)} onChange={() => toggle(v)} />{v}</label>
            ))}
            <Input className="h-7 w-20 text-xs" placeholder="사용자" value={custom} onChange={(e) => setCustom(e.target.value)}
              onKeyDown={(e) => { const v = Number(custom); if (e.key === "Enter" && v > 0 && !lines.includes(v)) { setLines([...lines, v]); setCustom(""); } }} />
            {lines.filter((v) => ![50, 100, 150].includes(v)).map((v) => (
              <button key={v} className="rounded bg-zinc-800 px-1 text-xs" onClick={() => toggle(v)}>{v} ✕</button>
            ))}
            <RangePicker value={range} onChange={setRange} />
          </>
        }
      >
        <TimeChart dates={dates} series={series} spy={spyData} lines={mk} onSelect={setSel} selected={sel} height={520} yName="종목 수" lowerName={bench.name} />
        <div className="mt-1 text-[11px] text-zinc-500">
          녹색 = 20% 급등 종목 수, 빨간색(아래쪽) = 20% 급락 종목 수 · 차트를 클릭하면 날짜 상세가 표시됩니다(기본: 최근 거래일) · 표의 Bull/Bear 숫자에 마우스를 올리면 해석이 보입니다 · Bear 기준선은 미국 전체 기준 값을 시장 규모(종목 수)에 맞춰 환산합니다.
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
                    <td title={be !== null ? READ.bear.read(be, r as Record<string, number | null>) : undefined} className={be !== null && be >= cnt(100, r as Record<string, number | null>) ? "bg-red-700 text-white" : "text-red-400"}>{fmt(be)}</td>
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
