"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Err, Panel } from "@/components/bits";
import { useApi } from "@/lib/api";
import { useSetting } from "@/lib/settings";
import { stockHref } from "@/lib/stock";

type Row = { date: string; time: string; kind: string; title: string; detail: string; ticker: string | null; market: string; mcap?: number | null; watch: boolean };
type Res = { today: string; fred: boolean; rows: Row[] };

const KINDS: [string, string, string][] = [
  ["FOMC", "FOMC", "bg-red-900/60 text-red-200"], ["매크로", "미국 매크로", "bg-sky-900/60 text-sky-200"],
  ["미국 실적", "미국 실적", "bg-amber-900/60 text-amber-200"], ["한국 실적 IR", "한국 실적 IR", "bg-emerald-900/60 text-emerald-200"],
  ["한국 IR", "한국 기타 IR", "bg-zinc-800 text-zinc-300"],
];
const COLOR = Object.fromEntries(KINDS.map(([k, , c]) => [k, c]));
const DOW = ["일", "월", "화", "수", "목", "금", "토"];

export default function Calendar() {
  const [ahead, setAhead] = useSetting("calendar.ahead", "21");
  const [cap, setCap] = useSetting("calendar.cap", "5e10");
  const [off, setOff] = useState<string[]>(["한국 IR"]);
  const [mine, setMine] = useState(false);
  const { data, error } = useApi<Res>(`/api/calendar?back=3&ahead=${ahead}&min_cap=${cap}`);
  const days = useMemo(() => {
    const m = new Map<string, Row[]>();
    for (const r of data?.rows ?? []) if (!off.includes(r.kind) && (!mine || r.watch || r.ticker === null)) m.set(r.date, [...(m.get(r.date) ?? []), r]);
    return [...m.entries()];
  }, [data, off, mine]);
  const toggle = (k: string) => setOff(off.includes(k) ? off.filter((x) => x !== k) : [...off, k]);

  return (
    <div className="space-y-3">
      <Panel title="일정 캘린더 (실적·매크로·FOMC)" right={<>
        <select value={ahead} onChange={(e) => setAhead(e.target.value)} className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200">
          {[["7", "1주"], ["21", "3주"], ["45", "6주"], ["90", "3개월"]].map(([v, l]) => <option key={v} value={v}>앞으로 {l}</option>)}
        </select>
        <select value={cap} onChange={(e) => setCap(e.target.value)} className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200">
          {[["2e11", "$200B 이상"], ["5e10", "$50B 이상"], ["1e10", "$10B 이상"], ["2e9", "$2B 이상"]].map(([v, l]) => <option key={v} value={v}>미국 실적: 시총 {l}</option>)}
        </select>
      </>}>
        <Err error={error} />
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {KINDS.map(([k, l, c]) => (
            <button key={k} onClick={() => toggle(k)} className={`rounded px-2 py-0.5 ${off.includes(k) ? "bg-zinc-900 text-zinc-600 line-through" : c}`}>{l}</button>
          ))}
          <label className="ml-2 flex items-center gap-1 text-zinc-400"><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} /> 관심종목만 (매크로·FOMC는 항상 표시)</label>
        </div>
        <div className="mt-2 text-[11px] text-zinc-500">
          미국 매크로: BEA 발표 일정(GDP·PCE 물가·무역수지)과 연준 FOMC.{data && !data.fred && " CPI·고용·PPI·소매판매 일정은 FRED 무료 키(GitHub Secret FRED_API_KEY)를 넣으면 추가됩니다."}
          {" "}미국 실적: Nasdaq 캘린더 (시총 필터 + 관심종목). 한국: DART &ldquo;기업설명회(IR) 개최&rdquo; 공시에서 읽은 일정 — 대형주 대부분은 실적 발표일에 IR을 엽니다 (IR 없이 공시만 하는 종목은 빠짐).
        </div>
      </Panel>

      {days.map(([d, rows]) => {
        const dt = new Date(d + "T00:00:00"), today = d === data?.today, past = data && d < data.today;
        return (
          <Panel key={d} title={<span className={today ? "text-sky-300" : past ? "text-zinc-500" : ""}>{d} ({DOW[dt.getDay()]}){today ? " · 오늘" : past ? " · 지남" : ""}</span>}>
            <div className="space-y-1">
              {rows.map((r, i) => (
                <div key={i} className={`flex flex-wrap items-baseline gap-2 text-xs ${past ? "opacity-70" : ""}`}>
                  <span className={`w-24 shrink-0 rounded px-1.5 text-center text-[10px] ${COLOR[r.kind] ?? "bg-zinc-800 text-zinc-300"}`}>{r.kind}</span>
                  <span className="w-20 shrink-0 font-mono text-zinc-500">{r.time || "—"}</span>
                  {r.ticker ? <Link className="text-sky-300 hover:underline" href={stockHref(r.ticker, r.market)}>{r.watch ? "★ " : ""}{r.title}</Link> : <b className="text-zinc-100">{r.title}</b>}
                  <span className="text-zinc-400">{r.detail}</span>
                </div>
              ))}
            </div>
          </Panel>
        );
      })}
      {data && !days.length && <div className="text-xs text-zinc-500">표시할 일정이 없습니다.</div>}
    </div>
  );
}
