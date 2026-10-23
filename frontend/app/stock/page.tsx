"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo } from "react";
import { Err, Kpi, Panel } from "@/components/bits";
import { TimeChart } from "@/components/TimeChart";
import { StockSearch, type Hit } from "@/components/StockSearch";
import { TVChart, tvLink, tvStock } from "@/components/TVChart";
import { WatchStar } from "@/components/WatchStar";
import { useApi } from "@/lib/api";
import { MK, WHO, eok, stockHref } from "@/lib/stock";

type Rep = { nid: number; date: string; broker: string; title: string; summary: string; goal: number | null; prev_goal: number | null; goal_chg: number | null; opinion: string; react1d: number | null };
type D = {
  ticker: string; name: string; market: string; exchange: string; sector: string; industry: string; size: number; close: number; date: string;
  returns: Record<string, number | null>; ranks: Record<string, { rank: number; of: number; mkt_pctile: number }>; sector_above: number | null;
  peers: ({ ticker: string; name: string; size: number } & Record<string, number | null>)[];
  etf: { holders: { etf: string; etf_name: string; shares: number | null; weight: number | null; date: string }[];
    changes: { date: string; etf_name: string; kind: string; shares_prev: number | null; shares: number | null; weight_prev: number | null; weight: number | null }[] };
  analyst: { rows: Rep[]; consensus: { brokers: number; mean: number; high: number; low: number; upside: number | null } | null } | null;
  dart: { date: string; title: string; url: string; react: number | null; ret_since: number | null }[];
  earnings: { date: string; quarter: string; eps: number | null; eps_forecast: number | null; surprise: number | null; react: number | null; ret_since: number | null }[];
  flow: { dates: string[]; close: (number | null)[]; foreign: number[]; inst: number[]; indiv: number[]; hold_ratio: (number | null)[]; sum5: Record<string, number>; sum20: Record<string, number> } | null;
};

const P: [string, string][] = [["r1d", "1일"], ["r1w", "1주"], ["r1m", "1개월"], ["r3m", "3개월"], ["r1y", "1년"], ["ytd", "연초 대비"]];
const pct = (v: number | null | undefined, d = 1) => (v === null || v === undefined ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(d)}%`);
const tone = (v: number | null | undefined) => (!v ? "text-zinc-400" : v > 0 ? "text-emerald-400" : "text-red-400");
const kr = (m: string) => m === "kospi" || m === "kosdaq";
const money = (v: number, m: string) => (kr(m) ? `${(v / 1e12).toLocaleString("ko-KR", { maximumFractionDigits: 2 })}조 원` : v >= 1e9 ? `$${(v / 1e9).toFixed(1)}B` : `$${(v / 1e6).toFixed(0)}M`);
const num = (v: number | null | undefined, d = 0) => (v === null || v === undefined ? "—" : v.toLocaleString("en-US", { maximumFractionDigits: d }));
const cum = (a: number[]) => a.reduce<number[]>((o, v) => [...o, (o.at(-1) ?? 0) + v], []);

/** ?q=name (from lists that carry names only): jump to the exact-name match. */
function ByName({ q }: { q: string }) {
  const { data } = useApi<Hit[]>(`/api/stock/search?q=${encodeURIComponent(q)}`);
  const router = useRouter();
  const hit = data?.find((h) => h.name === q) ?? data?.[0];
  useEffect(() => { if (hit) router.replace(stockHref(hit.ticker, hit.market)); }, [hit, router]);
  return data && !data.length ? <div className="text-sm text-zinc-500">&lsquo;{q}&rsquo;에 해당하는 종목이 없습니다.</div> : null;
}

function Detail({ t, m }: { t: string; m: string }) {
  const { data: d, error } = useApi<D>(`/api/stock?ticker=${encodeURIComponent(t)}${m ? `&market=${m}` : ""}`);
  const flow = useMemo(() => d?.flow?.dates.length ? {
    series: WHO.map(([k, l, c]) => ({ name: `${l} 누적`, data: cum(d.flow![k]), color: c, type: "line" as const })), spy: d.flow.close,
  } : null, [d]);
  if (error) return <Err error={error} />;
  if (!d) return <div className="text-xs text-zinc-500">불러오는 중…</div>;
  const tv = tvStock(d.ticker, d.exchange);
  const c = d.analyst?.consensus;
  return (
    <div className="space-y-3">
      <Panel title={<>{d.name} <span className="font-mono text-zinc-400">{d.ticker}</span> <span className="text-xs font-normal text-zinc-500">{MK[d.market] ?? d.market} · {d.sector}{d.industry && d.industry !== d.sector ? ` · ${d.industry}` : ""}</span></>}
        right={<><WatchStar ticker={d.ticker} market={d.market} /><a className="text-xs text-sky-400 hover:underline" target="_blank" rel="noreferrer" href={tvLink(kr(d.market) ? `KRX:${d.ticker}` : (tv ?? d.ticker))}>TradingView ↗</a></>}>
        <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-8">
          <Kpi label={`종가 (${d.date})`} value={num(d.close, kr(d.market) ? 0 : 2)} />
          <Kpi label={d.market === "crypto" ? "20일 평균 거래대금" : "시가총액"} value={<span className="text-lg">{money(d.size, d.market)}</span>} />
          {P.map(([k, l]) => {
            const r = d.ranks[k];
            return <Kpi key={k} label={l} value={<span className="text-lg">{pct(d.returns[k])}</span>} tone={(d.returns[k] ?? 0) > 0 ? "up" : (d.returns[k] ?? 0) < 0 ? "down" : "flat"}
              sub={r ? `업종 ${r.rank}/${r.of}위 · 시장 ${r.mkt_pctile.toFixed(0)}%ile` : undefined} />;
          }).slice(0, 6)}
        </div>
        {d.sector_above !== null && <div className="mt-2 text-[11px] text-zinc-500">{d.sector} 업종 종목 중 40일선 위 비율 {d.sector_above.toFixed(0)}% · %ile = 같은 시장 전체 종목 중 위치 (100 = 가장 많이 오름)</div>}
        {tv && <div className="mt-3"><TVChart symbol={tv} height={460} /></div>}
      </Panel>

      {flow && d.flow && (
        <Panel title="투자자별 누적 순매수 (억원)" right={<span className="text-xs text-zinc-400">
          {WHO.map(([k, l]) => <span key={k} className="ml-3">{l} 5일 <b className={tone(d.flow!.sum5[k])}>{eok(d.flow!.sum5[k])}</b> · 20일 <b className={tone(d.flow!.sum20[k])}>{eok(d.flow!.sum20[k])}</b></span>)}
        </span>}>
          <TimeChart dates={d.flow.dates} series={flow.series} spy={flow.spy} lowerName="종가" height={420} />
          <div className="text-[11px] text-zinc-500">외국인 지분율 {num(d.flow.hold_ratio.at(-1), 2)}% (120거래일 전 {num(d.flow.hold_ratio[0], 2)}%) · 순매수 = 순매수 주식 수 × 그날 종가</div>
        </Panel>
      )}

      <div className="grid gap-3 xl:grid-cols-2">
        <Panel title={`같은 업종 대형주 (${d.sector})`}>
          <table className="w-full font-mono text-xs">
            <thead className="text-zinc-400"><tr><th className="text-left">종목</th>{P.slice(0, 5).map(([k, l]) => <th key={k}>{l}</th>)}</tr></thead>
            <tbody>
              {d.peers.map((p) => (
                <tr key={p.ticker} className={`border-t border-zinc-900 text-center ${p.ticker === d.ticker ? "bg-zinc-900" : ""}`}>
                  <td className="max-w-40 truncate text-left font-sans"><Link className="text-sky-300 hover:underline" href={stockHref(p.ticker, d.market)}>{p.name}</Link></td>
                  {P.slice(0, 5).map(([k]) => <td key={k} className={tone(p[k])}>{pct(p[k])}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <Panel title="액티브 ETF 보유·매매">
          {!d.etf.holders.length && !d.etf.changes.length ? <div className="text-xs text-zinc-500">추적 중인 액티브 ETF가 보유하지 않습니다.</div> : (
            <div className="space-y-3">
              <table className="w-full font-mono text-xs">
                <thead className="text-zinc-400"><tr><th className="text-left">보유 ETF</th><th>비중</th><th>수량</th><th>기준일</th></tr></thead>
                <tbody>{d.etf.holders.map((h) => (
                  <tr key={h.etf} className="border-t border-zinc-900 text-center"><td className="text-left font-sans">{h.etf_name}</td><td>{h.weight === null ? "—" : `${h.weight.toFixed(2)}%`}</td><td>{num(h.shares)}</td><td className="text-zinc-500">{h.date}</td></tr>
                ))}</tbody>
              </table>
              {d.etf.changes.length > 0 && (
                <table className="w-full font-mono text-xs">
                  <thead className="text-zinc-400"><tr><th className="text-left">날짜</th><th className="text-left">ETF</th><th>구분</th><th>수량</th><th>비중</th></tr></thead>
                  <tbody>{d.etf.changes.map((x, i) => (
                    <tr key={i} className="border-t border-zinc-900 text-center"><td className="text-left">{x.date}</td><td className="text-left font-sans">{x.etf_name}</td>
                      <td className={x.kind === "편입" || x.kind === "증가" ? "text-emerald-400" : "text-red-400"}>{x.kind}</td>
                      <td>{num(x.shares_prev)} → {num(x.shares)}</td><td>{x.weight_prev === null ? "—" : x.weight_prev.toFixed(2)} → {x.weight === null ? "—" : x.weight.toFixed(2)}</td></tr>
                  ))}</tbody>
                </table>
              )}
            </div>
          )}
        </Panel>
      </div>

      {d.analyst && (
        <Panel title="증권사 리포트" right={c && <span className="text-xs text-zinc-400">최근 90일 {c.brokers}곳 평균 목표가 <b className="text-zinc-100">{num(c.mean)}</b> ({num(c.low)} ~ {num(c.high)}) · 괴리율 <b className={tone(c.upside)}>{pct(c.upside)}</b></span>}>
          {!d.analyst.rows.length ? <div className="text-xs text-zinc-500">최근 리포트가 없습니다.</div> : (
            <div className="max-h-[420px] overflow-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-zinc-900 text-zinc-400"><tr><th className="text-left">날짜</th><th className="text-left">증권사</th><th className="text-left">제목</th><th>목표가</th><th>변경</th><th>의견</th><th title="리포트 당일 주가 반응">당일 반응</th></tr></thead>
                <tbody>{d.analyst.rows.map((r) => (
                  <tr key={r.nid} className="border-t border-zinc-900 text-center align-top">
                    <td className="whitespace-nowrap text-left font-mono">{r.date}</td><td className="whitespace-nowrap text-left">{r.broker}</td>
                    <td className="text-left"><details><summary className="cursor-pointer text-zinc-200">{r.title}</summary><div className="whitespace-pre-line py-1 text-zinc-400">{r.summary}</div></details></td>
                    <td className="font-mono">{num(r.goal)}</td><td className={`font-mono ${tone(r.goal_chg)}`}>{r.goal_chg === null ? (r.prev_goal === null && r.goal ? "신규" : "—") : pct(r.goal_chg)}</td>
                    <td>{r.opinion}</td><td className={`font-mono ${tone(r.react1d)}`}>{pct(r.react1d)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </Panel>
      )}

      {kr(d.market) ? (
        <Panel title="잠정실적 공시 (DART)">
          {!d.dart.length ? <div className="text-xs text-zinc-500">최근 잠정실적 공시가 없거나 DART 수집이 꺼져 있습니다.</div> : (
            <table className="w-full font-mono text-xs">
              <thead className="text-zinc-400"><tr><th className="text-left">공시일</th><th className="text-left">공시</th><th title="공시 전 종가 → 공시 다음 거래일 종가">반응</th><th>이후</th></tr></thead>
              <tbody>{d.dart.map((x) => (
                <tr key={x.url} className="border-t border-zinc-900 text-center"><td className="text-left">{x.date}</td>
                  <td className="text-left font-sans"><a className="text-sky-300 hover:underline" href={x.url} target="_blank" rel="noreferrer">{x.title}</a></td>
                  <td className={tone(x.react)}>{pct(x.react)}</td><td className={tone(x.ret_since)}>{pct(x.ret_since)}</td></tr>
              ))}</tbody>
            </table>
          )}
        </Panel>
      ) : d.earnings.length > 0 && (
        <Panel title="실적 발표">
          <table className="w-full font-mono text-xs">
            <thead className="text-zinc-400"><tr><th className="text-left">발표일</th><th>분기</th><th>EPS</th><th>예상</th><th>서프라이즈</th><th>반응</th><th>이후</th></tr></thead>
            <tbody>{d.earnings.map((e) => (
              <tr key={e.date} className="border-t border-zinc-900 text-center"><td className="text-left">{e.date}</td><td>{e.quarter}</td><td>{num(e.eps, 2)}</td><td>{num(e.eps_forecast, 2)}</td>
                <td className={tone(e.surprise)}>{pct(e.surprise)}</td><td className={tone(e.react)}>{pct(e.react)}</td><td className={tone(e.ret_since)}>{pct(e.ret_since)}</td></tr>
            ))}</tbody>
          </table>
        </Panel>
      )}
    </div>
  );
}

function StockPage() {
  const sp = useSearchParams();
  const t = sp.get("t") ?? "", m = sp.get("m") ?? "", q = sp.get("q") ?? "";
  return (
    <div className="space-y-3">
      <Panel title="종목 상세 (Stock)" right={<StockSearch />}>
        <div className="text-[11px] text-zinc-500">한 종목의 수익률·업종 내 순위, 투자자별 수급(한국 전 종목), 증권사 리포트, 액티브 ETF 보유·매매, 실적을 모아 봅니다. 섹터 히트맵에서 종목을 더블클릭해도 열립니다.</div>
      </Panel>
      {q && !t && <ByName q={q} />}
      {t && <Detail key={t + m} t={t} m={m} />}
    </div>
  );
}

export default function Page() {
  return <Suspense><StockPage /></Suspense>;
}
