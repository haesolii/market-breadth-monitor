"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Err, Kpi, Panel } from "@/components/bits";
import { TimeChart } from "@/components/TimeChart";
import { useApi, useBench } from "@/lib/api";
import { WHO, eok, stockHref, type Who } from "@/lib/stock";

type StockRow = { ticker: string; name: string; market: string; sector: string; foreign?: number; inst?: number; hold_ratio: number | null; hold_chg20: number | null; foreign_pct: number | null };
type Res = {
  latest?: string; tracked?: number; dates: string[]; daily: Record<Who, number[]>; last_success?: string; last_error?: string;
  market: { date: string; market: string; foreign: number; inst: number; indiv: number }[];
  sectors: ({ sector: string } & Record<`${Who}${5 | 20}`, number>)[];
  stocks: Record<string, StockRow[]>;
};

const tone = (v: number | null | undefined) => (!v ? "text-zinc-400" : v > 0 ? "text-emerald-400" : "text-red-400");
const cum = (a: number[]) => a.reduce<number[]>((o, v) => [...o, (o.at(-1) ?? 0) + v], []);
const WINDOWS: [number, string][] = [[20, "1개월"], [60, "3개월"], [120, "6개월"]];

function Top({ title, rows, who }: { title: string; rows: StockRow[]; who: "foreign" | "inst" }) {
  return (
    <Panel title={title}>
      <table className="w-full font-mono text-xs">
        <thead className="text-zinc-400"><tr><th className="text-left">종목</th><th>5일 순매수</th><th title="시가총액 대비 5일 외국인 순매수">시총 대비</th><th title="외국인 지분율 (20거래일 변화)">외국인 지분</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.ticker} className="border-t border-zinc-900 text-center">
              <td className="max-w-40 truncate text-left font-sans"><Link className="text-sky-300 hover:underline" href={stockHref(r.ticker, r.market)}>{r.name}</Link> <span className="text-[10px] text-zinc-500">{r.sector}</span></td>
              <td className={tone(r[who])}>{eok(r[who])}</td>
              <td className={tone(r.foreign_pct)}>{r.foreign_pct === null ? "—" : `${r.foreign_pct > 0 ? "+" : ""}${r.foreign_pct.toFixed(2)}%`}</td>
              <td>{r.hold_ratio === null ? "—" : `${r.hold_ratio.toFixed(1)}%`}<span className={`ml-1 ${tone(r.hold_chg20)}`}>{r.hold_chg20 === null ? "" : `${r.hold_chg20 > 0 ? "+" : ""}${r.hold_chg20.toFixed(2)}`}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

type FundRow = { date: string; deposit: number; margin: number; margin_kospi: number; margin_kosdaq: number; forced: number; forced_pct: number; unsettled: number };
type Funds = { rows: FundRow[]; change?: Record<string, Record<string, number | null>>; margin_to_cap?: Record<string, number | null> };
const jo = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${(v / 10000).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}조`);
const djo = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${v > 0 ? "+" : ""}${(v / 10000).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}조`);

/** Retail leverage and dry powder: investor deposits, margin loans by market, forced liquidations (KOFIA). */
function MarketFunds() {
  const { data, error } = useApi<Funds>("/api/kr/funds?days=756");
  const bench = useBench("^KS11");
  if (error) return <Err error={error} />;
  if (!data?.rows.length) return null;
  const r = data.rows, last = r.at(-1)!, dates = r.map((x) => x.date), c = data.change ?? {};
  return (
    <Panel title={`증시 자금: 예탁금·신용융자·반대매매 (금융투자협회, ${last.date})`}>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
        <Kpi label="투자자예탁금" value={jo(last.deposit)} sub={`5일 ${djo(c.deposit?.["5"])} · 20일 ${djo(c.deposit?.["20"])}`} />
        <Kpi label="신용융자 잔고 (전체)" value={jo(last.margin)} sub={`5일 ${djo(c.margin?.["5"])} · 20일 ${djo(c.margin?.["20"])}`} />
        <Kpi label="신용융자 코스피" value={jo(last.margin_kospi)} sub={`시가총액의 ${data.margin_to_cap?.kospi?.toFixed(2) ?? "—"}% · 20일 ${djo(c.margin_kospi?.["20"])}`} />
        <Kpi label="신용융자 코스닥" value={jo(last.margin_kosdaq)} sub={`시가총액의 ${data.margin_to_cap?.kosdaq?.toFixed(2) ?? "—"}% · 20일 ${djo(c.margin_kosdaq?.["20"])}`} />
        <Kpi label="반대매매 (미수금 대비)" value={`${last.forced_pct.toFixed(1)}%`} tone={last.forced_pct >= 5 ? "down" : "flat"} sub={`${eok(last.forced)} (미수금 ${jo(last.unsettled)})`} />
      </div>
      <div className="mt-3 grid gap-3 xl:grid-cols-2">
        <TimeChart dates={dates} series={[
          { name: "투자자예탁금 (조)", color: "#38bdf8", type: "line", data: r.map((x) => x.deposit / 10000) },
          { name: "신용융자 (조)", color: "#f59e0b", type: "line", data: r.map((x) => x.margin / 10000) },
        ]} spy={bench.map ? dates.map((d) => bench.map!.get(d) ?? null) : undefined} lowerName="코스피" height={380} yName="조원" />
        <TimeChart dates={dates} series={[{ name: "반대매매 비중 (%)", color: "#ef4444", type: "bar", data: r.map((x) => x.forced_pct) }]}
          spy={r.map((x) => x.margin_kosdaq / 10000)} lowerName="코스닥 신용융자 (조)" lowerColor="#f59e0b" height={380} yName="%" />
      </div>
      <div className="mt-1 text-[11px] text-zinc-500">
        예탁금 = 주식을 사려고 증권사에 넣어 둔 돈(대기 매수 자금). 신용융자 = 빚내서 산 주식 잔고. 신용융자가 늘며 지수가 오르면 레버리지 과열, 지수 급락 때 반대매매 비중이 치솟으면
        강제 청산(투매)이 나오는 구간입니다. 공매도 통계는 한국거래소 데이터 포털이 로그인을 요구하게 바뀌어 넣지 못했습니다.
      </div>
    </Panel>
  );
}

export default function Flows() {
  const [win, setWin] = useState(60);
  const { data, error } = useApi<Res>("/api/flows?days=120");
  const bench = useBench("^KS11");
  const view = useMemo(() => {
    if (!data?.dates.length) return null;
    const n = Math.min(win, data.dates.length), dates = data.dates.slice(-n);
    return { dates, series: WHO.map(([k, l, c]) => ({ name: `${l} 누적`, data: cum(data.daily[k].slice(-n)), color: c, type: "line" as const })),
      spy: bench.map ? dates.map((d) => bench.map!.get(d) ?? null) : undefined };
  }, [data, win, bench.map]);
  const today = (data?.market ?? []).filter((m) => m.date === data?.market.at(-1)?.date);

  return (
    <div className="space-y-3">
      <Panel title="한국 투자자별 순매수 (외국인·기관·개인)" right={
        <div className="flex overflow-hidden rounded border border-zinc-700 text-xs">
          {WINDOWS.map(([n, l]) => <button key={n} onClick={() => setWin(n)} className={`px-3 py-1 ${win === n ? "bg-sky-700 text-white" : "text-zinc-300 hover:bg-zinc-800"}`}>{l}</button>)}
        </div>}>
        <Err error={error ?? data?.last_error ?? null} />
        {data && !data.dates.length && <div className="text-xs text-zinc-500">아직 수급 데이터가 없습니다 (갱신 전).</div>}
        <div className="mb-3 grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
          {today.flatMap((m) => WHO.map(([k, l]) => (
            <Kpi key={m.market + k} label={`${m.market === "kospi" ? "코스피" : "코스닥"} ${l} (${m.date})`} value={eok(m[k])} tone={m[k] > 0 ? "up" : m[k] < 0 ? "down" : "flat"} />
          )))}
        </div>
        {view && <TimeChart dates={view.dates} series={view.series} spy={view.spy} lowerName={bench.name} height={460} yName="억원" />}
        <div className="mt-1 text-[11px] text-zinc-500">
          위 칸 = 오늘 시장 전체 순매수 (네이버, 장중에는 잠정치). 차트 = 코스피·코스닥 전 종목({data?.tracked?.toLocaleString() ?? "—"}개)의 투자자별 순매수(주식 수 × 그날 종가)를 누적한 값, 아래 = 코스피 지수. 종목별 값은 매일 18시(KST) 이후 확정치로 갱신.
          기준일 {data?.latest ?? "—"}. 개인 + 외국인 + 기관 합은 기타법인 때문에 0이 아닐 수 있습니다.
        </div>
      </Panel>

      {data && data.sectors.length > 0 && (
        <Panel title="업종별 순매수 (전 종목 합계)">
          <div className="max-h-[420px] overflow-auto">
            <table className="w-full font-mono text-xs">
              <thead className="sticky top-0 bg-zinc-900 text-zinc-400"><tr>
                <th className="text-left">업종</th><th>외국인 5일</th><th>기관 5일</th><th>개인 5일</th><th>외국인 20일</th><th>기관 20일</th><th>개인 20일</th>
              </tr></thead>
              <tbody>
                {data.sectors.map((s) => (
                  <tr key={s.sector} className="border-t border-zinc-900 text-center hover:bg-zinc-900">
                    <td className="text-left font-sans">{s.sector}</td>
                    {(["foreign5", "inst5", "indiv5", "foreign20", "inst20", "indiv20"] as const).map((k) => <td key={k} className={tone(s[k])}>{eok(s[k])}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="text-[11px] text-zinc-500">외국인 20일 순매수 순으로 정렬. 외국인과 기관이 같은 방향이면 수급이 강한 업종입니다.</div>
        </Panel>
      )}

      <MarketFunds />

      {data?.stocks.foreign_nlargest && (
        <div className="grid gap-3 lg:grid-cols-2">
          <Top title="외국인 순매수 상위 (5일)" rows={data.stocks.foreign_nlargest} who="foreign" />
          <Top title="외국인 순매도 상위 (5일)" rows={data.stocks.foreign_nsmallest} who="foreign" />
          <Top title="기관 순매수 상위 (5일)" rows={data.stocks.inst_nlargest} who="inst" />
          <Top title="기관 순매도 상위 (5일)" rows={data.stocks.inst_nsmallest} who="inst" />
        </div>
      )}
    </div>
  );
}
