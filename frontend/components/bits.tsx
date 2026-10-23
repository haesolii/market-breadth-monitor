"use client";
import { useApi, type Status } from "@/lib/api";
import { useSetting } from "@/lib/settings";

export function Panel({ title, right, children, className = "" }: { title?: React.ReactNode; right?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={`rounded border border-zinc-800 bg-zinc-950/60 ${className}`}>
      {(title || right) && (
        <div className="flex flex-wrap items-center gap-2 border-b border-zinc-800 px-3 py-2">
          <h2 className="text-sm font-semibold text-zinc-200">{title}</h2>
          <div className="ml-auto flex flex-wrap items-center gap-2">{right}</div>
        </div>
      )}
      <div className="p-3">{children}</div>
    </section>
  );
}

export function Kpi({ label, value, sub, tone }: { label: React.ReactNode; value: React.ReactNode; sub?: React.ReactNode; tone?: "up" | "down" | "flat" }) {
  const c = tone === "up" ? "text-emerald-400" : tone === "down" ? "text-red-400" : "text-zinc-100";
  return (
    <div className="rounded border border-zinc-800 bg-zinc-950 px-3 py-2">
      <div className="text-[11px] text-zinc-400">{label}</div>
      <div className={`font-mono text-2xl font-semibold ${c}`}>{value}</div>
      {sub && <div className="text-[11px] text-zinc-500">{sub}</div>}
    </div>
  );
}

export const RANGES: [string, number][] = [["1M", 21], ["3M", 63], ["6M", 126], ["1Y", 252], ["3Y", 756], ["ALL", 0]];

export function RangePicker({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  return (
    <div className="flex overflow-hidden rounded border border-zinc-700 text-xs">
      {RANGES.map(([l, n]) => (
        <button key={l} onClick={() => onChange(n)} className={`px-2 py-1 ${value === n ? "bg-zinc-700 text-white" : "text-zinc-400 hover:bg-zinc-800"}`}>
          {l}
        </button>
      ))}
    </div>
  );
}

export const PERIODS: [string, number][] = [["6개월", 126], ["1년", 252], ["3년", 756]];

/** 6개월 / 1년 / 3년 buttons (value = trading sessions). */
export function PeriodButtons({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  return (
    <div className="flex overflow-hidden rounded border border-zinc-700 text-xs">
      {PERIODS.map(([l, n]) => (
        <button key={l} onClick={() => onChange(n)} className={`px-3 py-1 ${value === n ? "bg-sky-700 text-white" : "text-zinc-300 hover:bg-zinc-800"}`}>{l}</button>
      ))}
    </div>
  );
}

export function Select({ value, onChange, options, className = "" }: { value: string; onChange: (v: string) => void; options: [string, string][]; className?: string }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} className={`rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200 ${className}`}>
      {options.map(([v, l]) => (
        <option key={v} value={v}>
          {l}
        </option>
      ))}
    </select>
  );
}

/** Data-source selector persisted per browser; returns [source, selector, status]. */
const ORDER = ["public_repo", "yahoo", "nasdaq", "kospi", "kosdaq", "crypto", "massive"];
const byOrder = (a: string, b: string) => (ORDER.indexOf(a) + 99 * +(ORDER.indexOf(a) < 0)) - (ORDER.indexOf(b) + 99 * +(ORDER.indexOf(b) < 0));

/** Data-source / market selector persisted per browser; returns [source, selector, status].
 * tabs=true renders market tabs (미국 전체 | 나스닥 | 코스피 | 코스닥 ...) instead of a dropdown. */
export function useSource(kind: "breadth20" | "monitor", tabs = false): [string, React.ReactNode, Status | null] {
  const { data: st } = useApi<Status>("/api/status");
  const [src, setSrc] = useSetting<string>(`source.${kind}`, "");
  const list = st ? [...(kind === "breadth20" ? st.breadth20_sources : st.monitor_sources)].sort(byOrder) : [];
  const def = st ? (kind === "breadth20" ? st.default_breadth20 : st.default_monitor) : "";
  const value = src && list.includes(src) ? src : def;
  const node = !st ? null : tabs ? (
    <div className="flex flex-wrap overflow-hidden rounded border border-zinc-700 text-xs">
      {list.map((s) => (
        <button key={s} title={st.source_info[s]?.label} onClick={() => setSrc(s)}
          className={`px-3 py-1 ${value === s ? "bg-sky-700 text-white" : "text-zinc-300 hover:bg-zinc-800"}`}>
          {st.source_info[s]?.short ?? st.source_info[s]?.label ?? s}
        </button>
      ))}
    </div>
  ) : <Select value={value} onChange={setSrc} options={list.map((s) => [s, st.source_info[s]?.label ?? s])} />;
  return [value, node, st];
}

export function Err({ error }: { error: string | null }) {
  return error ? <div className="rounded border border-red-800 bg-red-950/60 px-3 py-2 text-sm text-red-300">오류 (Error): {error}</div> : null;
}

/** Underlined section tabs (one view at a time instead of a long scroll); counts shown as small badges. */
export function TabBar<T extends string>({ value, onChange, tabs }: { value: T; onChange: (v: T) => void; tabs: [T, string, number?][] }) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-zinc-800 [scrollbar-width:none]">
      {tabs.map(([k, label, n]) => (
        <button key={k} onClick={() => onChange(k)}
          className={`-mb-px shrink-0 whitespace-nowrap border-b-2 px-3 py-2 text-sm ${value === k ? "border-sky-500 text-white" : "border-transparent text-zinc-400 hover:text-zinc-200"}`}>
          {label}{n !== undefined && <span className="ml-1.5 rounded-full bg-zinc-800 px-1.5 text-[10px] text-zinc-400">{n}</span>}
        </button>
      ))}
    </div>
  );
}

/** Page numbers for a list: ‹ 1 2 3 … › (pages counted from 0). */
export function Pager({ page, pages, onChange }: { page: number; pages: number; onChange: (p: number) => void }) {
  if (pages <= 1) return null;
  const near = [...new Set([0, page - 1, page, page + 1, pages - 1])].filter((p) => p >= 0 && p < pages).sort((a, b) => a - b);
  const btn = "min-w-8 rounded px-2 py-1 text-xs";
  return (
    <div className="flex items-center justify-center gap-1 pt-3">
      <button className={`${btn} text-zinc-400 hover:bg-zinc-800 disabled:opacity-30`} disabled={page === 0} onClick={() => onChange(page - 1)}>‹ 이전</button>
      {near.map((p, i) => (
        <span key={p} className="flex items-center gap-1">
          {i > 0 && p - near[i - 1] > 1 && <span className="text-zinc-600">…</span>}
          <button className={`${btn} ${p === page ? "bg-sky-700 text-white" : "text-zinc-300 hover:bg-zinc-800"}`} onClick={() => onChange(p)}>{p + 1}</button>
        </span>
      ))}
      <button className={`${btn} text-zinc-400 hover:bg-zinc-800 disabled:opacity-30`} disabled={page >= pages - 1} onClick={() => onChange(page + 1)}>다음 ›</button>
    </div>
  );
}
