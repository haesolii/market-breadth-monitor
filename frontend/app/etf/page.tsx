"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Err, Panel, Select } from "@/components/bits";
import { Input } from "@/components/ui/input";
import { useApi } from "@/lib/api";
import { downloadCSV } from "@/lib/csv";
import { useSetting } from "@/lib/settings";
import { stockByName, stockHref } from "@/lib/stock";

type Fund = { etf: string; name: string; market: string; aum: number | null; ret3m: number | null; date: string | null; holdings: number; changes: number; top: string[] };
type Change = { date: string; etf: string; etf_name: string; market: string; name: string; ticker: string; kind: string;
  shares_prev: number | null; shares: number | null; weight_prev: number | null; weight: number | null; ret1d: number | null };
type Cons = { market: string; name: string; ticker: string; buy: string[]; sell: string[]; ret1d: number | null };
type Res = { funds: Fund[]; changes: Change[]; consensus: Cons[]; days: number; last_success?: string; last_error?: string | null };
type Hold = { etf: string; date: string | null; holdings: { name: string; ticker: string; shares: number | null; weight: number | null; ret1d: number | null }[];
  history: { date: string; name: string; kind: string; shares_prev: number | null; shares: number | null; weight_prev: number | null; weight: number | null }[] };

const KIND: Record<string, string> = { 편입: "bg-emerald-700 text-white", 증가: "bg-emerald-950 text-emerald-300", 감소: "bg-red-950 text-red-300", 편출: "bg-red-700 text-white" };
const pct = (v: number | null | undefined, d = 1) => (v === null || v === undefined ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(d)}%`);
const tone = (v: number | null | undefined) => (v === null || v === undefined ? "text-zinc-600" : v > 0 ? "text-emerald-400" : v < 0 ? "text-red-400" : "");
const num = (v: number | null | undefined) => (v === null || v === undefined ? "—" : v.toLocaleString("en-US", { maximumFractionDigits: 0 }));
const aum = (f: Fund) => (f.aum === null ? "—" : `${(f.aum / 1e8).toLocaleString("ko-KR", { maximumFractionDigits: 0 })}억`);
const shareChg = (a: number | null, b: number | null) => (a && b ? pct((b / a - 1) * 100) : "");
const Badge = ({ k }: { k: string }) => <span className={`rounded px-1.5 py-0.5 font-sans text-[11px] ${KIND[k] ?? ""}`}>{k}</span>;

export default function EtfPage() {
  const [days, setDays] = useSetting("etf.days", "7");
  const [mkt, setMkt] = useSetting("etf.market", "ALL");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<string | null>(null);
  const { data, error } = useApi<Res>(`/api/etf?days=${days}`);
  const hold = useApi<Hold>(sel ? `/api/etf/holdings?etf=${sel}` : null);
  const inMkt = (m: string) => mkt === "ALL" || m === mkt;
  const funds = useMemo(() => (data?.funds ?? []).filter((f) => inMkt(f.market)), [data, mkt]);  // eslint-disable-line react-hooks/exhaustive-deps
  const changes = useMemo(() => (data?.changes ?? []).filter((c) => inMkt(c.market) && (!q || `${c.name} ${c.ticker} ${c.etf_name}`.toLowerCase().includes(q.toLowerCase()))), [data, mkt, q]);  // eslint-disable-line react-hooks/exhaustive-deps
  const selFund = data?.funds.find((f) => f.etf === sel);
  const noHistory = data && data.funds.length > 0 && data.funds.every((f) => f.changes === 0) && !data.changes.length;

  return (
    <div className="space-y-3">
      <Err error={error} />
      <Panel title="액티브 ETF 보유 종목 변화 (Active ETF holdings)" right={<>
        <Select value={mkt} onChange={setMkt} options={[["ALL", "전체"], ["KR", "국내 액티브"], ["US", "ARK (미국)"]]} />
        <Select value={days} onChange={setDays} options={[["1", "최근 1일"], ["7", "최근 7일"], ["30", "최근 30일"], ["90", "최근 90일"]]} />
      </>}>
        <div className="text-[11px] text-zinc-500">
          국내: 주식형 액티브 ETF (규모 상위, 채권·금리·커버드콜 제외) · CU(설정 단위)당 구성 종목 기준 · 미국: ARK 6개 펀드 일별 공시.
          운용사가 과거 구성을 제공하지 않아 변화 이력은 수집을 시작한 날부터 쌓입니다. 마지막 수집 {data?.last_success ? new Date(data.last_success).toLocaleString("ko-KR", { hour12: false }) : "—"}
          {data?.last_error && <span className="text-red-400"> · 오류: {data.last_error}</span>}
        </div>
        {noHistory && <div className="mt-2 rounded bg-zinc-900 px-2 py-1 text-xs text-amber-300">아직 비교할 이전 구성이 없습니다 — 다음 거래일 공시부터 편입·편출이 표시됩니다.</div>}
      </Panel>

      <div className="grid gap-3 xl:grid-cols-5">
        <Panel className="xl:col-span-3" title={`변화 내역 (${changes.length}건)`} right={<>
          <Input className="h-7 w-44 text-xs" placeholder="종목·ETF 검색" value={q} onChange={(e) => setQ(e.target.value)} />
          <button className="text-xs text-sky-400" onClick={() => downloadCSV(`etf_changes_${days}d.csv`, changes)}>CSV</button>
        </>}>
          <div className="max-h-[560px] overflow-auto">
            <table className="w-full font-mono text-xs">
              <thead className="sticky top-0 bg-zinc-900 text-zinc-400"><tr>
                <th className="text-left">날짜</th><th className="text-left">ETF</th><th className="text-left">종목</th><th>구분</th><th>주식수 (CU당)</th><th>비중</th><th title="종목의 최근 거래일 등락률">당일 등락</th>
              </tr></thead>
              <tbody>
                {changes.map((c, i) => (
                  <tr key={i} className="border-t border-zinc-900 text-center hover:bg-zinc-900">
                    <td className="text-left">{c.date.slice(5)}</td>
                    <td className="max-w-48 cursor-pointer truncate text-left font-sans text-sky-300" title={c.etf_name} onClick={() => setSel(c.etf)}>{c.etf_name}</td>
                    <td className="max-w-56 truncate text-left font-sans" title={c.name}><Link className="hover:underline" href={c.ticker ? stockHref(c.ticker) : stockByName(c.name)}>{c.name}</Link>{c.ticker && <span className="ml-1 text-zinc-500">{c.ticker}</span>}</td>
                    <td><Badge k={c.kind} /></td>
                    <td>{num(c.shares_prev)} → {num(c.shares)} <span className={tone(c.shares && c.shares_prev ? c.shares - c.shares_prev : null)}>{shareChg(c.shares_prev, c.shares)}</span></td>
                    <td>{c.weight_prev?.toFixed(2) ?? "—"} → {c.weight?.toFixed(2) ?? "—"}%</td>
                    <td className={tone(c.ret1d)}>{pct(c.ret1d)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!changes.length && <div className="py-6 text-center text-xs leading-relaxed text-zinc-500">해당 기간 변화가 없습니다.<br />
              편입·편출은 같은 펀드의 구성 종목을 이틀 이상 저장해야 계산됩니다 (2026-10-23 수집 시작, 매일 장 마감 후 갱신).</div>}
          </div>
        </Panel>

        <Panel className="xl:col-span-2" title="여러 펀드가 함께 움직인 종목 (2개 이상)">
          <div className="max-h-[560px] overflow-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-zinc-900 text-zinc-400"><tr><th className="text-left">종목</th><th>매수 펀드</th><th>매도 펀드</th><th>당일</th></tr></thead>
              <tbody>
                {(data?.consensus ?? []).filter((c) => inMkt(c.market)).map((c) => (
                  <tr key={c.market + c.name} className="border-t border-zinc-900 text-center">
                    <td className="text-left"><Link className="hover:underline" href={c.ticker ? stockHref(c.ticker) : stockByName(c.name)}>{c.name}</Link></td>
                    <td className="text-emerald-400" title={c.buy.join("\n")}>{c.buy.length || ""}</td>
                    <td className="text-red-400" title={c.sell.join("\n")}>{c.sell.length || ""}</td>
                    <td className={`font-mono ${tone(c.ret1d)}`}>{pct(c.ret1d)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>

      <Panel title={`펀드 목록 (${funds.length})`}>
        <div className="max-h-96 overflow-auto">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-zinc-900 text-zinc-400"><tr>
              <th className="text-left">ETF</th><th>순자산</th><th>3개월 수익률</th><th>구성 종목</th><th>변화</th><th className="text-left">상위 비중</th><th>기준일</th>
            </tr></thead>
            <tbody>
              {funds.map((f) => (
                <tr key={f.etf} onClick={() => setSel(f.etf)} className={`cursor-pointer border-t border-zinc-900 text-center hover:bg-zinc-900 ${sel === f.etf ? "bg-zinc-800" : ""}`}>
                  <td className="text-left">{f.name} <span className="text-zinc-500">{f.etf}</span></td>
                  <td className="font-mono">{aum(f)}</td><td className={`font-mono ${tone(f.ret3m)}`}>{pct(f.ret3m)}</td>
                  <td className="font-mono">{f.holdings}</td><td className="font-mono">{f.changes || ""}</td>
                  <td className="max-w-72 truncate text-left text-zinc-400">{f.top.join(", ")}</td><td className="font-mono">{f.date ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      {sel && (
        <div className="grid gap-3 xl:grid-cols-2">
          <Panel title={`${selFund?.name ?? sel} — 구성 종목 (${hold.data?.date ?? "…"})`} right={<button className="text-xs text-zinc-400" onClick={() => setSel(null)}>닫기</button>}>
            <Err error={hold.error} />
            <div className="max-h-[480px] overflow-auto">
              <table className="w-full font-mono text-xs">
                <thead className="sticky top-0 bg-zinc-900 text-zinc-400"><tr><th className="text-left">종목</th><th>주식수</th><th className="text-left">비중</th><th>당일</th></tr></thead>
                <tbody>
                  {(hold.data?.holdings ?? []).map((h) => (
                    <tr key={h.name} className="border-t border-zinc-900 text-center">
                      <td className="max-w-60 truncate text-left font-sans">{h.name}{h.ticker && <span className="ml-1 text-zinc-500">{h.ticker}</span>}</td>
                      <td>{num(h.shares)}</td>
                      <td className="text-left"><span className="mr-1 inline-block h-1.5 rounded bg-sky-600 align-middle" style={{ width: `${Math.min(100, (h.weight ?? 0) * 3)}px` }} />{h.weight?.toFixed(2) ?? "—"}%</td>
                      <td className={tone(h.ret1d)}>{pct(h.ret1d)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
          <Panel title="이 펀드의 변화 이력">
            <div className="max-h-[480px] overflow-auto">
              <table className="w-full font-mono text-xs">
                <thead className="sticky top-0 bg-zinc-900 text-zinc-400"><tr><th className="text-left">날짜</th><th className="text-left">종목</th><th>구분</th><th>주식수</th><th>비중</th></tr></thead>
                <tbody>
                  {(hold.data?.history ?? []).map((h, i) => (
                    <tr key={i} className="border-t border-zinc-900 text-center">
                      <td className="text-left">{h.date}</td><td className="max-w-56 truncate text-left font-sans">{h.name}</td><td><Badge k={h.kind} /></td>
                      <td>{num(h.shares_prev)} → {num(h.shares)}</td><td>{h.weight_prev?.toFixed(2) ?? "—"} → {h.weight?.toFixed(2) ?? "—"}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {hold.data && !hold.data.history.length && <div className="py-6 text-center text-xs text-zinc-500">아직 변화 이력 없음</div>}
            </div>
          </Panel>
        </div>
      )}
    </div>
  );
}
