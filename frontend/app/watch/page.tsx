"use client";
import Link from "next/link";
import { useState } from "react";
import { Err, Panel } from "@/components/bits";
import { StockSearch, type Hit } from "@/components/StockSearch";
import { send, useApi } from "@/lib/api";
import { MK, stockHref } from "@/lib/stock";

type Item = { ticker: string; market: string; name?: string; sector?: string; close?: number | null; r1d?: number | null; r1w?: number | null; r1m?: number | null; ytd?: number | null };
type Ev = { date: string; ticker: string; name: string; kind: string; text: string; key: string; upcoming: boolean };
type Res = { items: Item[]; events: Ev[] };

const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(1)}%`);
const tone = (v: number | null | undefined) => (!v ? "text-zinc-400" : v > 0 ? "text-emerald-400" : "text-red-400");
const KIND: Record<string, string> = { 리포트: "bg-sky-900/60 text-sky-200", ETF: "bg-violet-900/60 text-violet-200", 수급: "bg-emerald-900/60 text-emerald-200",
  잠정실적: "bg-amber-900/60 text-amber-200", 공시: "bg-cyan-900/60 text-cyan-200", 실적: "bg-amber-900/60 text-amber-200", IR: "bg-amber-900/40 text-amber-200", 급등락: "bg-red-900/60 text-red-200" };

export default function Watch() {
  const { data, error, reload } = useApi<Res>("/api/watchlist");
  const [err, setErr] = useState<string | null>(null);
  const [kind, setKind] = useState("");
  const items = data?.items ?? [];
  const save = async (next: { ticker: string; market: string }[]) => {
    setErr(null);
    try {
      await send("/api/watchlist", "POST", next.map(({ ticker, market }) => ({ ticker, market })));
      reload();
    } catch (e) {
      setErr(String(e));
    }
  };
  const add = (h: Hit) => !items.some((x) => x.ticker === h.ticker && x.market === h.market) && save([...items, h]);
  const remove = (it: Item) => save(items.filter((x) => !(x.ticker === it.ticker && x.market === it.market)));
  const events = (data?.events ?? []).filter((e) => !kind || e.kind === kind);
  const kinds = [...new Set((data?.events ?? []).map((e) => e.kind))];

  return (
    <div className="space-y-3">
      <Panel title="관심종목 (Watchlist)" right={<StockSearch onPick={add} placeholder="관심종목 추가: 종목명 또는 티커" />}>
        <Err error={error ?? err} />
        <div className="text-[11px] text-zinc-500">
          여기 넣은 종목의 리포트·목표가 변경, 액티브 ETF 편입·편출, 외국인·기관 대량 매매(그 종목 평소 60일 평균의 3배 이상), 잠정실적·주요 공시(유상증자, 자사주, 수주 등), 실적·IR 예정(하루 전), 하루 ±5% 급등락을
          텔레그램 &ldquo;시장 폭 신호&rdquo; 메시지에 함께 보내 드립니다 (같은 사건은 한 번만). 종목 상세 화면의 ☆ 버튼으로도 추가할 수 있습니다.
        </div>
        {!items.length ? <div className="py-6 text-center text-sm text-zinc-500">아직 관심종목이 없습니다. 오른쪽 위에서 검색해 추가하세요.</div> : (
          <table className="mt-2 w-full font-mono text-xs">
            <thead className="text-zinc-400"><tr><th className="text-left">종목</th><th className="text-left">시장·섹터</th><th>종가</th><th>1일</th><th>1주</th><th>1개월</th><th>연초 대비</th><th /></tr></thead>
            <tbody>
              {items.map((it) => (
                <tr key={it.market + it.ticker} className="border-t border-zinc-900 text-center hover:bg-zinc-900">
                  <td className="text-left font-sans"><Link className="text-sky-300 hover:underline" href={stockHref(it.ticker, it.market)}>{it.name ?? it.ticker}</Link> <span className="font-mono text-zinc-500">{it.ticker}</span></td>
                  <td className="text-left font-sans text-zinc-400">{MK[it.market] ?? it.market} · {it.sector ?? ""}</td>
                  <td>{it.close?.toLocaleString("en-US", { maximumFractionDigits: 2 }) ?? "—"}</td>
                  {(["r1d", "r1w", "r1m", "ytd"] as const).map((k) => <td key={k} className={tone(it[k])}>{pct(it[k])}</td>)}
                  <td><button className="text-zinc-500 hover:text-red-400" onClick={() => remove(it)} title="빼기">✕</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      {items.length > 0 && (
        <Panel title={`관심종목 소식 (최근 7일 + 예정 14일) ${events.length}건`} right={
          <select value={kind} onChange={(e) => setKind(e.target.value)} className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200">
            <option value="">전체</option>{kinds.map((k) => <option key={k} value={k}>{k}</option>)}
          </select>}>
          {!events.length ? <div className="text-xs text-zinc-500">해당 기간 소식이 없습니다.</div> : (
            <div className="space-y-1">
              {events.map((e) => (
                <div key={e.key} className={`flex flex-wrap items-baseline gap-2 border-t border-zinc-900 py-1 text-xs ${e.upcoming ? "opacity-80" : ""}`}>
                  <span className="w-20 font-mono text-zinc-400">{e.date}{e.upcoming ? " 예정" : ""}</span>
                  <span className={`rounded px-1.5 text-[10px] ${KIND[e.kind] ?? "bg-zinc-800 text-zinc-300"}`}>{e.kind}</span>
                  <Link className="text-sky-300 hover:underline" href={stockHref(e.ticker, items.find((x) => x.ticker === e.ticker)?.market)}>{e.name}</Link>
                  <span className="text-zinc-300">{e.text}</span>
                </div>
              ))}
            </div>
          )}
        </Panel>
      )}
    </div>
  );
}
