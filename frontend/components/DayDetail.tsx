"use client";
import { useApi, type Status } from "@/lib/api";
import { DEFS, READ, fmt } from "@/lib/defs";
import { Panel } from "./bits";

type Day = {
  date: string;
  breadth20: Record<string, Record<string, number | null>>;
  monitor: null | { source: string; values: Record<string, number | null>; chg5?: Record<string, number | null>; chg10?: Record<string, number | null> };
};

const chg = (v: number | null | undefined, d = 0) =>
  v === null || v === undefined ? <span className="text-zinc-600">—</span> : <span className={v > 0 ? "text-emerald-400" : v < 0 ? "text-red-400" : "text-zinc-500"}>{v > 0 ? "+" : ""}{fmt(v, d)}</span>;
/** "🔴 극단적 급락, 과매도 반등 관찰" -> [dot, text]. */
const split = (s: string) => [s.slice(0, s.indexOf(" ")), s.slice(s.indexOf(" ") + 1)] as const;

/** Snapshot for a clicked date. Deliberately shows NO forward returns (decision screen).
 * One line per market / indicator; criteria and English names live in tooltips. */
export function DayDetail({ date, mmSource }: { date: string | null; mmSource?: string }) {
  const { data: st } = useApi<Status>("/api/status");
  const { data, error } = useApi<Day>(date ? `/api/day?date=${date}${mmSource ? `&mm_source=${mmSource}` : ""}` : null);
  if (!date) return <Panel title="선택한 날짜 상세 (Day detail)"><div className="text-sm text-zinc-500">차트에서 날짜를 클릭하세요.</div></Panel>;
  const mon = data?.monitor;
  return (
    <Panel title={<>선택한 날짜 상세: <span className="font-mono text-sky-400">{date}</span></>}>
      {error && <div className="text-sm text-red-400">{error}</div>}
      {data && (
        <div className="space-y-4 text-xs">
          <table className="w-full">
            <thead className="text-[11px] text-zinc-500">
              <tr><th className="pb-1 text-left font-normal">20% 급등락</th><th className="font-normal">Bull</th><th className="font-normal" title="5거래일 전 대비">5일Δ</th>
                <th className="font-normal">Bear</th><th className="font-normal" title="5거래일 전 대비">5일Δ</th><th className="pl-2 text-left font-normal">해석 (Bear 기준)</th></tr>
            </thead>
            <tbody className="font-mono">
              {Object.entries(data.breadth20).map(([s, r]) => {
                const rd = typeof r.bear === "number" ? split(READ.bear.read(r.bear, r)) : null;
                const tip = typeof r.bull === "number" && typeof r.bear === "number"
                  ? `Bull: ${READ.bull.read(r.bull, r)}\nBear: ${READ.bear.read(r.bear, r)}\n기준 — Bear: ${READ.bear.rule(r)}` : undefined;
                return (
                  <tr key={s} className="border-t border-zinc-900 text-center" title={tip}>
                    <td className="py-0.5 text-left font-sans text-zinc-400">{st?.source_info[s]?.short ?? (s === "public_repo" ? "미국 전체 (상장폐지 포함)" : s)}</td>
                    <td className="text-emerald-400">{fmt(r.bull)}</td><td>{chg(r.bull_chg5)}</td>
                    <td className="text-red-400">{fmt(r.bear)}</td><td>{chg(r.bear_chg5)}</td>
                    <td className="truncate pl-2 text-left font-sans text-zinc-300">{rd ? <>{rd[0]} {rd[1]}</> : "—"}</td>
                  </tr>
                );
              })}
              {!Object.keys(data.breadth20).length && <tr><td colSpan={6} className="text-zinc-500">해당 날짜 데이터 없음</td></tr>}
            </tbody>
          </table>
          {mon ? (
            <table className="w-full">
              <thead className="text-[11px] text-zinc-500">
                <tr><th className="pb-1 text-left font-normal">시장 모니터 · {st?.source_info[mon.source]?.short ?? mon.source}</th><th className="font-normal">값</th>
                  <th className="font-normal" title="5거래일 전 대비">5일Δ</th><th className="pl-2 text-left font-normal">해석</th></tr>
              </thead>
              <tbody>
                {DEFS.map((d) => {
                  const dig = d.kind === "ratio" || d.kind === "pct" ? 2 : 0;
                  const v = mon.values[d.key], r = READ[d.key];
                  const rd = r && typeof v === "number" ? split(r.read(v, mon.values)) : null;
                  return (
                    <tr key={d.key} className="border-t border-zinc-900" title={r ? `${d.en}\n기준: ${r.rule(mon.values)}` : d.en}>
                      <td className="py-0.5 text-zinc-400">{d.ko}</td>
                      <td className="text-right font-mono">{fmt(v, dig)}</td>
                      <td className="text-right font-mono">{chg(mon.chg5?.[d.key], dig)}</td>
                      <td className="truncate pl-2 text-zinc-300">{rd ? <>{rd[0]} {rd[1]}</> : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : <div className="text-zinc-500">시장 모니터 데이터 없음 (Market Monitor needs per-ticker source)</div>}
          <div className="text-[11px] text-zinc-600">
            행에 마우스를 올리면 기준이 보입니다 · 종목 수 기준은 시장 규모{mon ? ` (${fmt(mon.values.eligible_universe_count)}종목)` : ""}에 맞춰 환산 ·
            이후 지수 수익률은 “과거 시장 통계”에서 확인하세요.
          </div>
        </div>
      )}
    </Panel>
  );
}
