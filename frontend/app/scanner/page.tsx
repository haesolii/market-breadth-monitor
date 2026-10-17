"use client";
import { useMemo, useState } from "react";
import { Err, Panel, Select } from "@/components/bits";
import { Input } from "@/components/ui/input";
import { TVChart, TVUnavailable, tvStock } from "@/components/TVChart";
import { useApi, type Row, type Status } from "@/lib/api";
import { downloadCSV } from "@/lib/csv";
import { SIGNALS, fmt } from "@/lib/defs";

type Scan = { source: string; date: string; rows: Row[] };
const COLS: [string, string, number][] = [
  ["ticker", "티커 (Ticker)", -1], ["name", "회사 (Company)", -1], ["exchange", "거래소 (Exchange)", -1],
  ["close", "종가 (Close)", 2], ["ret1", "1일 %", 2], ["ret5", "5일 수익률 % (5D)", 2], ["ret20", "20일 %", 2], ["volume", "거래량 (Volume)", 0],
];
const BULLISH = new Set(["bull20", "up4", "q_up25", "m_up25", "m_up50", "d34_up13"]);

export default function Scanner() {
  const dates = useApi<Record<string, string[]>>("/api/scan/dates");
  const { data: st } = useApi<Status>("/api/status");
  const srcs = Object.keys(dates.data ?? {});
  const [source, setSource] = useState("");
  const src = srcs.includes(source) ? source : srcs[0] ?? "";
  const list = dates.data?.[src] ?? [];
  const [date, setDate] = useState("");
  const d = list.includes(date) ? date : list.at(-1) ?? "";
  const scan = useApi<Scan>(src && d ? `/api/scan?source=${src}&date=${d}` : null);
  const [signal, setSignal] = useState("bull20|bear20");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<[string, 1 | -1]>(["ret5", -1]);
  const [chart, setChart] = useState<{ ticker: string; name: string; exchange: string } | null>(null);

  const rows = useMemo(() => {
    const want = signal.split("|");
    const qq = q.trim().toLowerCase();
    return (scan.data?.rows ?? [])
      .filter((r) => want.some((s) => r[s]))
      .filter((r) => !qq || String(r.ticker).toLowerCase().includes(qq) || String(r.name ?? "").toLowerCase().includes(qq))
      .sort((a, b) => {
        const x = a[sort[0]], y = b[sort[0]];
        return (typeof x === "number" && typeof y === "number" ? x - y : String(x ?? "").localeCompare(String(y ?? ""))) * sort[1];
      });
  }, [scan.data, signal, q, sort]);

  const sigs = (r: Row) => Object.keys(SIGNALS).filter((s) => r[s]);
  const csv = () => downloadCSV(`scan_${src}_${d}.csv`, rows.map((r) => ({ ...r, signals: sigs(r).join(" ") })),
    ["ticker", "name", "exchange", "close", "ret1", "ret5", "ret20", "volume", "minv3", "signals"]);

  return (
    <div className="space-y-3">
      {!srcs.length && dates.data && (
        <Err error="종목 단위 결과를 제공하는 소스(yahoo 또는 massive)의 데이터가 없습니다. 데이터 관리 메뉴에서 갱신하세요. (public_repo 소스는 종목 수만 제공)" />
      )}
      <Panel
        title="조건 충족 종목 검색 (Scanner Results)"
        right={
          <>
            <Select value={src} onChange={setSource} options={srcs.map((s) => [s, st?.source_info[s]?.short ?? s])} />
            <Select value={d} onChange={setDate} options={[...list].reverse().map((x) => [x, x])} />
            <Select value={signal} onChange={setSignal} options={[
              ["bull20|bear20", "20% 급등 + 급락 (Bull/Bear)"], ["bull20", "20% 급등 (Bull)"], ["bear20", "20% 급락 (Bear)"],
              ...Object.entries(SIGNALS).filter(([k]) => !k.endsWith("20")).map(([k, v]) => [k, v] as [string, string]),
            ]} />
            <Input className="h-7 w-40 text-xs" placeholder="티커/회사 검색" value={q} onChange={(e) => setQ(e.target.value)} />
            <button className="text-xs text-sky-400" onClick={csv}>CSV 다운로드</button>
          </>
        }
      >
        <Err error={scan.error} />
        {scan.loading && <div className="text-xs text-zinc-500">스캔 중…</div>}
        <div className="mb-2 text-xs text-zinc-400">{d} · {rows.length}종목 · {st?.source_info[src]?.label ?? src}{src !== "massive" && " (현재 상장 종목 기준 — 이후 상장폐지된 종목은 누락될 수 있음)"}</div>
        {chart && (
          <div className="mb-3 rounded border border-zinc-800">
            <div className="flex items-center gap-2 border-b border-zinc-800 px-2 py-1 text-xs">
              <span className="font-semibold">{chart.name}</span>
              <span className="font-mono text-zinc-500">{tvStock(chart.ticker, chart.exchange) ?? `KRX:${chart.ticker}`}</span>
              <span className="text-zinc-500">· TradingView 차트 (50·200일 이동평균)</span>
              <button className="ml-auto text-zinc-400 hover:text-white" onClick={() => setChart(null)}>닫기 ✕</button>
            </div>
            {tvStock(chart.ticker, chart.exchange) ? <TVChart symbol={tvStock(chart.ticker, chart.exchange)!} height={480} /> : <TVUnavailable sym={`KRX:${chart.ticker}`} />}
          </div>
        )}
        <div className="mb-1 text-[11px] text-zinc-500">행을 클릭하면 TradingView 차트가 열립니다.</div>
        <div className="max-h-[70vh] overflow-auto">
          <table className="w-full font-mono text-xs">
            <thead className="sticky top-0 bg-zinc-900 text-zinc-300">
              <tr>
                {COLS.map(([k, l]) => (
                  <th key={k} className="cursor-pointer px-2 py-1 text-left" onClick={() => setSort([k, sort[0] === k ? (-sort[1] as 1 | -1) : -1])}>
                    {l}{sort[0] === k ? (sort[1] === 1 ? " ▲" : " ▼") : ""}
                  </th>
                ))}
                <th className="px-2 py-1 text-left">신호 (Signal)</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={String(r.ticker)} onClick={() => setChart({ ticker: String(r.ticker), name: String(r.name ?? r.ticker), exchange: String(r.exchange ?? "") })}
                  className={`cursor-pointer border-b border-zinc-900 hover:bg-zinc-900 ${chart?.ticker === r.ticker ? "bg-zinc-800" : ""}`}>
                  {COLS.map(([k, , dig]) => {
                    const v = r[k];
                    const c = k.startsWith("ret") && typeof v === "number" ? (v >= 0 ? "text-emerald-400" : "text-red-400") : "";
                    return <td key={k} className={`px-2 py-0.5 ${c} ${k === "name" ? "max-w-64 truncate font-sans" : ""}`}>{dig < 0 ? String(v ?? "—") : fmt(v, dig)}</td>;
                  })}
                  <td className="px-2 py-0.5">
                    {sigs(r).map((s) => (
                      <span key={s} className={`mr-1 rounded px-1 ${BULLISH.has(s) ? "bg-emerald-900 text-emerald-200" : "bg-red-900 text-red-200"}`}>{SIGNALS[s]}</span>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
