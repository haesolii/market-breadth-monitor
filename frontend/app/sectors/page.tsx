"use client";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Err, Panel } from "@/components/bits";
import { CorrHeatmap } from "@/components/CorrHeatmap";
import { TimeChart } from "@/components/TimeChart";
import { LIVE_MS, useApi } from "@/lib/api";
import { useSetting } from "@/lib/settings";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

type Stock = { ticker: string; name: string; sector: string; industry: string; size: number; close: number; ret: number };
type Sector = { sector: string; n: number; size: number; ret: number; median: number; up_pct: number; best: [string, string, number]; worst: [string, string, number] };
type Res = { market: string; period: string; date?: string; n?: number; sectors: Sector[]; stocks: Stock[] };

const MARKETS: [string, string][] = [["yahoo", "미국"], ["nasdaq", "나스닥"], ["kospi", "코스피"], ["kosdaq", "코스닥"], ["crypto", "크립토"]];
const PERIODS: [string, string, number][] = [["r1d", "1일", 3], ["r1w", "1주", 6], ["r1m", "1개월", 12], ["r3m", "3개월", 25], ["r1y", "1년", 60], ["ytd", "연초 대비", 40]];
const WINDOWS: [string, string][] = [["21", "1개월"], ["63", "3개월"], ["126", "6개월"], ["252", "1년"]];
// Fixed categorical order (never cycled): the whole market first, then up to 7 sectors.
const LINE = ["#e4e4e7", "#38bdf8", "#f59e0b", "#a78bfa", "#10b981", "#f472b6", "#fb923c", "#2dd4bf"];
const MAX_LINES = LINE.length;
type Hist = { days: number; dates: string[]; picked: string[]; series: Record<string, number[]>;
  stats: { sector: string; n: number | null; ret: number; vol: number; corr: number | null; beta: number | null; above: number | null; above20: number | null }[];
  corr: { sectors: string[]; matrix: (number | null)[][] }; breadth: Record<string, (number | null)[]>;
  rrg: { dates: string[]; tails: Record<string, [number, number][]> } };

const QUAD: [string, string, number, number][] = [["주도 (Leading)", "#10b981", 1, 1], ["약화 (Weakening)", "#f59e0b", 1, -1], ["부진 (Lagging)", "#ef4444", -1, -1], ["개선 (Improving)", "#38bdf8", -1, 1]];

/** Relative rotation: x = strength vs the market (100 = in line), y = whether that strength is rising.
 * Sectors usually rotate clockwise: 개선 → 주도 → 약화 → 부진. */
function Rrg({ rrg, picked }: { rrg: Hist["rrg"]; picked: string[] }) {
  const option = useMemo(() => {
    const secs = picked.filter((p) => rrg.tails[p]?.length);
    const all = secs.flatMap((p) => rrg.tails[p]);
    const ext = (i: 0 | 1) => Math.max(2, ...all.map((v) => Math.abs(v[i] - 100))) * 1.15;
    const ex = ext(0), ey = ext(1);
    return {
      backgroundColor: "transparent", animation: false, grid: { left: 48, right: 16, top: 16, bottom: 40 },
      tooltip: { backgroundColor: "#18181b", borderColor: "#3f3f46", textStyle: { color: "#e4e4e7", fontSize: 12 },
        formatter: (p: { seriesName: string; value: [number, number]; dataIndex: number }) =>
          `<b>${p.seriesName}</b> ${rrg.dates[rrg.dates.length - (rrg.tails[p.seriesName]?.length ?? 0) + p.dataIndex] ?? ""}<br/>상대강도 ${p.value[0].toFixed(1)} · 모멘텀 ${p.value[1].toFixed(1)}` },
      xAxis: { type: "value", min: 100 - ex, max: 100 + ex, name: "상대강도 (RS-Ratio)", nameLocation: "middle", nameGap: 26, nameTextStyle: { color: "#71717a", fontSize: 10 },
        axisLabel: { color: "#71717a", fontSize: 10, formatter: (v: number) => v.toFixed(0) }, splitLine: { show: false } },
      yAxis: { type: "value", min: 100 - ey, max: 100 + ey, name: "모멘텀", nameTextStyle: { color: "#71717a", fontSize: 10 },
        axisLabel: { color: "#71717a", fontSize: 10, formatter: (v: number) => v.toFixed(0) }, splitLine: { show: false } },
      series: [
        { type: "line", data: [], silent: true, markArea: { silent: true, data: QUAD.map(([n, c, sx, sy]) => [
          { coord: [100, 100], itemStyle: { color: c, opacity: 0.06 }, label: { show: true, color: c, fontSize: 11, position: sx > 0 ? (sy > 0 ? "insideTopRight" : "insideBottomRight") : (sy > 0 ? "insideTopLeft" : "insideBottomLeft"), formatter: n } },
          { coord: [100 + sx * ex, 100 + sy * ey] }]) } },
        ...secs.map((p) => {
          const c = LINE[picked.indexOf(p) % LINE.length], t = rrg.tails[p];
          return { name: p, type: "line", data: t, lineStyle: { color: c, width: 2 }, itemStyle: { color: c, borderColor: "#09090b", borderWidth: 2 },
            symbol: "circle", symbolSize: (_: unknown, i: { dataIndex: number }) => (i.dataIndex === t.length - 1 ? 10 : 4),
            label: { show: true, formatter: (x: { dataIndex: number }) => (x.dataIndex === t.length - 1 ? p : ""), color: "#e4e4e7", fontSize: 11, position: "right" } };
        }),
      ],
    };
  }, [rrg, picked]);
  if (!rrg.dates.length) return <div className="text-xs text-zinc-500">기간이 짧아 계산할 수 없습니다 (60거래일 이상 필요).</div>;
  return <ReactECharts option={option} notMerge style={{ height: 440 }} theme="dark" />;
}

/** Sector indexes (=100) on one axis, their correlation matrix, and return / volatility / beta per sector. */
function SectorTrend({ market, picked, setPicked }: { market: string; picked: string[]; setPicked: (p: string[]) => void }) {
  const [win, setWin] = useSetting("sectors.window", "252");
  const q = picked.length ? `&sectors=${encodeURIComponent(picked.join("|"))}` : "";
  const { data, error } = useApi<Hist>(`/api/sectors/history?market=${market}&days=${win}${q}`);
  const series = useMemo(() => (data ? data.picked.map((k, i) => ({ name: k, data: data.series[k], color: LINE[i % LINE.length], type: "line" as const })) : []), [data]);
  const toggle = (sec: string) => {
    const cur = data?.picked ?? [];
    setPicked(cur.includes(sec) ? cur.filter((x) => x !== sec) : [...cur, sec].slice(-MAX_LINES));
  };
  if (!data?.dates.length) return error ? <Err error={error} /> : null;
  return (
    <>
      <Panel title={`섹터 지수 추이 (시작 = 100, 최근 ${data.days}거래일)`} right={<>
        <Tabs value={win} onChange={setWin} options={WINDOWS} />
        <button className="text-xs text-zinc-400" onClick={() => setPicked([])}>기본 선택</button>
      </>}>
        <TimeChart dates={data.dates} series={series} rebased height={420} />
        <div className="mt-1 text-[11px] text-zinc-500">
          섹터 지수 = 현재 시가총액 가중 일간 수익률을 이어 붙인 값 (현재 구성 종목 기준, 상장폐지 종목 없음). 아래 표에서 섹터를 눌러 선 추가/제거 (최대 {MAX_LINES}개).
        </div>
      </Panel>
      <div className="grid gap-3 xl:grid-cols-2">
        <Panel title="섹터별 수익률·변동성·시장 민감도">
          <div className="max-h-[480px] overflow-auto">
            <table className="w-full font-mono text-xs">
              <thead className="sticky top-0 bg-zinc-900 text-zinc-400"><tr>
                <th className="text-left">섹터</th><th>기간 수익률</th><th title="일간 수익률 표준편차 × √연간 거래일">연 변동성</th>
                <th title="시장 전체와의 일간 수익률 상관계수">시장 상관</th><th title="시장이 1% 움직일 때 섹터가 움직인 평균 폭">베타</th>
                <th title="40일 이동평균 위에 있는 종목 비율 (현재 / 20거래일 전)">40일선 위</th>
              </tr></thead>
              <tbody>
                {data.stats.map((s) => {
                  const i = data.picked.indexOf(s.sector);
                  return (
                    <tr key={s.sector} onClick={() => toggle(s.sector)} className={`cursor-pointer border-t border-zinc-900 text-center hover:bg-zinc-900 ${i >= 0 ? "bg-zinc-900" : ""}`}>
                      <td className="text-left font-sans">
                        <span className="mr-1.5 inline-block h-2 w-2 rounded-full align-middle" style={{ background: i >= 0 ? LINE[i % LINE.length] : "transparent", border: "1px solid #52525b" }} />
                        {s.sector}{s.n ? <span className="ml-1 text-zinc-500">{s.n}</span> : null}
                      </td>
                      <td className={tone(s.ret)}>{pct(s.ret, 1)}</td><td>{s.vol.toFixed(1)}%</td>
                      <td>{s.corr === null ? "—" : s.corr.toFixed(2)}</td><td>{s.beta === null ? "—" : s.beta.toFixed(2)}</td>
                      <td className={s.above === null ? "" : s.above >= 70 ? "text-emerald-400" : s.above < 30 ? "text-red-400" : ""}>
                        {s.above === null ? "—" : `${s.above.toFixed(0)}%`}<span className="text-zinc-500">{s.above20 === null ? "" : ` ← ${s.above20.toFixed(0)}`}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>
        <Panel title="섹터 순환 지도 (RRG, 시장 전체 대비)">
          <Rrg rrg={data.rrg} picked={data.picked} />
          <div className="text-[11px] text-zinc-500">
            점 = 주 단위 최근 {data.rrg.dates.length}개 위치, 큰 점 = 현재. 오른쪽 = 시장보다 강함, 위쪽 = 강해지는 중. 섹터는 보통 시계 방향(개선 → 주도 → 약화 → 부진)으로 돕니다.
            JdK RRG 공식은 비공개라 50일 평균 대비 상대강도·10일 변화로 근사했습니다.
          </div>
        </Panel>
        <Panel title="섹터별 40일선 위 종목 비율 (섹터의 T2108, 5일 평균)">
          <TimeChart dates={data.dates} series={data.picked.filter((k) => data.breadth[k]).map((k) => ({ name: k, data: data.breadth[k], color: LINE[data.picked.indexOf(k) % LINE.length], type: "line" as const }))} height={360} />
          <div className="text-[11px] text-zinc-500">지수(시가총액 가중)는 대형주 몇 개로 움직일 수 있습니다. 이 비율은 섹터 안 종목이 고르게 오르는지(동일 가중)를 봅니다. 지수는 오르는데 비율이 떨어지면 소수 종목만 끌어올리는 상태입니다.</div>
        </Panel>
        <Panel title="선택 섹터 간 일간 수익률 상관계수">
          <CorrHeatmap rows={data.corr.sectors} matrix={data.corr.matrix} height={440} left={130} />
          <div className="text-[11px] text-zinc-500">1에 가까울수록 같이 움직임, 0 근처면 무관, 음수면 반대로 움직임. 분산 효과를 볼 때 상관이 낮은 섹터 조합을 찾는 데 씁니다.</div>
        </Panel>
      </div>
    </>
  );
}
// Diverging: red (down) - neutral gray - green (up), the app's up/down convention.
const DIV = ["#b91c1c", "#ef4444", "#3f3f46", "#22c55e", "#15803d"];
const pct = (v: number | null | undefined, d = 1) => (v === null || v === undefined ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(d)}%`);
const tone = (v: number) => (v > 0 ? "text-emerald-400" : v < 0 ? "text-red-400" : "text-zinc-400");
const money = (v: number, market: string) => {
  const kr = market === "kospi" || market === "kosdaq";
  return kr ? `${(v / 1e12).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}조 원` : v >= 1e9 ? `$${(v / 1e9).toFixed(1)}B` : `$${(v / 1e6).toFixed(0)}M`;
};

function Tabs({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: [string, string, ...unknown[]][] }) {
  return (
    <div className="flex overflow-hidden rounded border border-zinc-700 text-xs">
      {options.map(([k, l]) => (
        <button key={k} onClick={() => onChange(k)} className={`px-3 py-1 ${value === k ? "bg-sky-700 text-white" : "text-zinc-300 hover:bg-zinc-800"}`}>{l}</button>
      ))}
    </div>
  );
}

export default function Sectors() {
  const [market, setMarket] = useSetting("sectors.market", "yahoo");
  const [picked, setPicked] = useState<string[]>([]);
  useEffect(() => setPicked([]), [market]);
  const [period, setPeriod] = useSetting("sectors.period", "r1d");
  const router = useRouter();
  const { data, error, loading } = useApi<Res>(`/api/sectors?market=${market}&period=${period}`, LIVE_MS);
  const span = PERIODS.find((p) => p[0] === period)?.[2] ?? 5;
  const sizeLabel = market === "crypto" ? "20일 평균 거래대금" : "시가총액";

  const option = useMemo(() => {
    if (!data) return null;
    const groups = new Map<string, Stock[]>();
    for (const s of data.stocks) groups.set(s.sector, [...(groups.get(s.sector) ?? []), s]);
    const ret = new Map(data.sectors.map((s) => [s.sector, s.ret]));
    const tree = [...groups.entries()].map(([sector, st]) => ({
      name: sector, value: [st.reduce((a, s) => a + s.size, 0), ret.get(sector) ?? 0],
      children: st.map((s) => ({ name: market === "kospi" || market === "kosdaq" || market === "crypto" ? s.name : s.ticker, value: [s.size, s.ret], s })),
    }));
    return {
      backgroundColor: "transparent", animation: false,
      tooltip: {
        backgroundColor: "#18181b", borderColor: "#3f3f46", textStyle: { color: "#e4e4e7", fontSize: 12 },
        formatter: (p: { data: { name: string; value: [number, number]; s?: Stock } }) => {
          const s = p.data.s, [size, r] = p.data.value;
          return s
            ? `<b>${s.name}</b> <span style="color:#a1a1aa">${s.ticker}</span><br/>${s.industry || s.sector}<br/>${pct(r, 2)} · 종가 ${s.close.toLocaleString("en-US", { maximumFractionDigits: 4 })}<br/>${sizeLabel} ${money(size, market)}`
            : `<b>${p.data.name}</b><br/>가중 수익률 ${pct(r, 2)}<br/>${sizeLabel} ${money(size, market)}`;
        },
      },
      visualMap: { show: false, type: "continuous", dimension: 1, min: -span, max: span, inRange: { color: DIV } },
      series: [{
        type: "treemap", data: tree, roam: false, nodeClick: "zoomToNode", width: "100%", height: "100%", top: 28, left: 0, right: 0, bottom: 0,
        leafDepth: 2, visualDimension: 1,
        breadcrumb: { show: true, top: 0, itemStyle: { color: "#27272a", textStyle: { color: "#e4e4e7" } } },
        upperLabel: { show: true, height: 18, color: "#e4e4e7", fontSize: 11, formatter: (p: { name: string; value: [number, number] }) => `${p.name}  ${pct(p.value[1])}` },
        label: { show: true, color: "#fafafa", fontSize: 11, overflow: "truncate", formatter: (p: { name: string; value: [number, number] }) => `${p.name}\n${pct(p.value[1])}` },
        itemStyle: { borderColor: "#09090b", borderWidth: 1, gapWidth: 1 },
        levels: [{ itemStyle: { borderColor: "#09090b", borderWidth: 3, gapWidth: 3 } }, { itemStyle: { borderColor: "#09090b", borderWidth: 1, gapWidth: 1 } }],
      }],
    };
  }, [data, market, span, sizeLabel]);

  return (
    <div className="space-y-3">
      <Panel title="섹터 히트맵 (Sector Heatmap)" right={<><Tabs value={market} onChange={setMarket} options={MARKETS} /><Tabs value={period} onChange={setPeriod} options={PERIODS} /></>}>
        <Err error={error} />
        {loading && !data && <div className="text-xs text-zinc-500">불러오는 중…</div>}
        {data && !data.stocks.length && <div className="text-xs text-zinc-500">데이터가 아직 없습니다 (섹터 갱신 전).</div>}
        {option && data!.stocks.length > 0 && <ReactECharts option={option} notMerge style={{ height: 620 }} theme="dark"
          onEvents={{ dblclick: (p: { data?: { s?: Stock } }) => p.data?.s && router.push(`/stock?t=${encodeURIComponent(p.data.s.ticker)}&m=${market === "nasdaq" ? "yahoo" : market}`) }} />}
        <div className="mt-1 flex flex-wrap items-center gap-3 text-[11px] text-zinc-500">
          <span>기준일 {data?.date ?? "—"} · {data?.n?.toLocaleString() ?? "—"}종목 중 {sizeLabel} 상위 {data?.stocks.length ?? 0}개 표시 · 칸 크기 = {sizeLabel} · 섹터 클릭 시 확대 · 종목 더블클릭 시 종목 상세</span>
          <span className="flex items-center gap-1">{pct(-span, 0)}<span className="inline-block h-2 w-24 rounded" style={{ background: `linear-gradient(90deg, ${DIV.join(",")})` }} />{pct(span, 0)}</span>
          <span>{market === "yahoo" || market === "nasdaq" ? "섹터: Nasdaq 스크리너" : market === "crypto" ? "크립토는 섹터 구분 없음" : "업종: 네이버 업종 분류"}</span>
        </div>
      </Panel>

      {data && data.sectors.length > 0 && (
        <Panel title="섹터별 요약 (전체 종목 기준)">
          <div className="overflow-x-auto">
            <table className="w-full font-mono text-xs">
              <thead className="text-zinc-400"><tr>
                <th className="text-left">섹터</th><th>종목 수</th><th>{sizeLabel}</th><th title="시가총액 가중">가중 수익률</th><th>중앙값</th><th>상승 종목 비율</th><th className="text-left">최고</th><th className="text-left">최저</th>
              </tr></thead>
              <tbody>
                {[...data.sectors].sort((a, b) => b.ret - a.ret).map((s) => (
                  <tr key={s.sector} className="border-t border-zinc-900 text-center hover:bg-zinc-900">
                    <td className="text-left font-sans">{s.sector}</td><td>{s.n}</td><td>{money(s.size, market)}</td>
                    <td className={tone(s.ret)}>{pct(s.ret, 2)}</td><td className={tone(s.median)}>{pct(s.median, 2)}</td>
                    <td><span className="inline-block h-1.5 w-16 rounded bg-zinc-800 align-middle"><span className="block h-1.5 rounded bg-emerald-500" style={{ width: `${s.up_pct}%` }} /></span> {s.up_pct.toFixed(0)}%</td>
                    <td className="text-left"><span className="font-sans">{s.best[1]}</span> <span className={tone(s.best[2])}>{pct(s.best[2])}</span></td>
                    <td className="text-left"><span className="font-sans">{s.worst[1]}</span> <span className={tone(s.worst[2])}>{pct(s.worst[2])}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      <SectorTrend market={market} picked={picked} setPicked={setPicked} />
    </div>
  );
}
