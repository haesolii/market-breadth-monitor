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
  v === null || v === undefined ? <span className="text-zinc-600">—</span> : <span className={v > 0 ? "text-emerald-400" : v < 0 ? "text-red-400" : "text-zinc-400"}>{v > 0 ? "+" : ""}{fmt(v, d)}</span>;

/** Snapshot for a clicked date. Deliberately shows NO forward returns (decision screen). */
export function DayDetail({ date, mmSource }: { date: string | null; mmSource?: string }) {
  const { data: st } = useApi<Status>("/api/status");
  const { data, error } = useApi<Day>(date ? `/api/day?date=${date}${mmSource ? `&mm_source=${mmSource}` : ""}` : null);
  if (!date) return <Panel title="선택한 날짜 상세 (Day detail)"><div className="text-sm text-zinc-500">차트에서 날짜를 클릭하세요.</div></Panel>;
  return (
    <Panel title={<>선택한 날짜 상세: <span className="font-mono text-sky-400">{date}</span></>}>
      {error && <div className="text-sm text-red-400">{error}</div>}
      {data && (
        <div className="space-y-3 text-xs">
          <table className="w-full font-mono">
            <thead className="text-zinc-500"><tr><th className="text-left">20% 급등락 (Bull/Bear)</th><th>Bull</th><th>5일Δ</th><th>10일Δ</th><th>Bear</th><th>5일Δ</th><th>10일Δ</th></tr></thead>
            <tbody>
              {Object.entries(data.breadth20).map(([s, r]) => (
                <tr key={s} className="text-center">
                  <td className="text-left text-zinc-400">{st?.source_info[s]?.short ?? (s === "public_repo" ? "미국 전체 (상장폐지 포함)" : s)}</td>
                  <td className="text-emerald-400">{fmt(r.bull)}</td><td>{chg(r.bull_chg5)}</td><td>{chg(r.bull_chg10)}</td>
                  <td className="text-red-400">{fmt(r.bear)}</td><td>{chg(r.bear_chg5)}</td><td>{chg(r.bear_chg10)}</td>
                </tr>
              ))}
              {!Object.keys(data.breadth20).length && <tr><td colSpan={7} className="text-zinc-500">해당 날짜 데이터 없음</td></tr>}
            </tbody>
          </table>
          {data.monitor ? (
            <table className="w-full font-mono">
              <thead className="text-zinc-500"><tr><th className="text-left">시장 모니터 ({st?.source_info[data.monitor.source]?.short ?? data.monitor.source})</th><th>값</th><th>5일Δ</th><th>10일Δ</th><th className="text-left">해석</th></tr></thead>
              <tbody>
                {DEFS.map((d) => {
                  const dig = d.kind === "ratio" || d.kind === "pct" ? 2 : 0;
                  const v = data.monitor!.values[d.key], r = READ[d.key];
                  return (
                    <tr key={d.key} className="text-center">
                      <td className="text-left text-zinc-400">{d.ko} <span className="text-zinc-600">({d.en})</span>
                        {r && <div className="font-sans text-[10px] text-zinc-600">기준: {r.rule}</div>}</td>
                      <td>{fmt(v, dig)}</td>
                      <td>{chg(data.monitor!.chg5?.[d.key], dig)}</td>
                      <td>{chg(data.monitor!.chg10?.[d.key], dig)}</td>
                      <td className="text-left font-sans text-zinc-300">{r && typeof v === "number" ? r.read(v, data.monitor!.values) : "—"}</td>
                    </tr>
                  );
                })}
                <tr className="text-center"><td className="text-left text-zinc-400">계산 대상 종목 수 (Universe)</td><td>{fmt(data.monitor.values.eligible_universe_count)}</td><td /><td /><td className="text-left font-sans text-zinc-300">⚪ 시장 폭 계산의 모집단</td></tr>
              </tbody>
            </table>
          ) : <div className="text-zinc-500">시장 모니터 데이터 없음 (Market Monitor needs per-ticker source)</div>}
          <div className="text-[11px] text-zinc-600">※ 해석은 선택한 날짜 값으로 자동 계산됩니다. 종목 수 기준(300·500·1,000 등)은 미국 전체 시장 기준이라 국내 시장엔 그대로 맞지 않을 수 있습니다.</div>
          <div className="text-[11px] text-zinc-600">※ 이후 지수 수익률은 실시간 판단 화면에 표시하지 않습니다. “과거 시장 통계” 메뉴에서 확인하세요.</div>
        </div>
      )}
    </Panel>
  );
}
