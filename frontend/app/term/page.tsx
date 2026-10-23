"use client";
import dynamic from "next/dynamic";
import { useMemo } from "react";
import { Err, Kpi, Panel } from "@/components/bits";
import { TimeChart } from "@/components/TimeChart";
import { useApi } from "@/lib/api";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

type Pt = { expiry: string; price: number };
type Res = {
  labels: Record<string, string>; pairs: Record<string, string>;
  vol?: { dates: string[]; series: Record<string, (number | null)[]> };
  vol_curve?: { labels: string[]; now: (number | null)[]; w1: (number | null)[] | null; m1: (number | null)[] | null; date: string };
  vix_ratio?: { now: number; pctile: number; days_inverted_1y: number };
  vix_futures?: { date: string; curves: Record<"now" | "w1" | "m1", Pt[]> };
  vix_m1m2?: [string, number, number][];
  basis?: Record<string, [string, number][]>;
  basis_now?: { pair: string; date: string; fut: number; spot: number; basis: number }[];
  crude?: { contract: string; price: number; date: string }[];
};

const SNAP: ["now" | "w1" | "m1", string, string][] = [["now", "현재", "#f4f4f5"], ["w1", "1주 전", "#38bdf8"], ["m1", "1개월 전", "#a78bfa"]];
const PAIR_COLOR: Record<string, string> = { ES: "#f4f4f5", NQ: "#38bdf8", RTY: "#f59e0b", YM: "#a78bfa", K200: "#10b981" };
const TIP = { trigger: "axis", backgroundColor: "#18181b", borderColor: "#3f3f46", textStyle: { color: "#e4e4e7", fontSize: 12 } };
const AX = { axisLabel: { color: "#a1a1aa", fontSize: 11 }, axisLine: { lineStyle: { color: "#3f3f46" } }, splitLine: { lineStyle: { color: "#27272a" } } };

/** A term curve: x = horizon / expiry, one line per snapshot (now, 1 week, 1 month ago). */
function Curve({ x, lines, height = 300, yName }: { x: string[]; lines: { name: string; color: string; data: (number | null)[] }[]; height?: number; yName?: string }) {
  const option = useMemo(() => ({
    backgroundColor: "transparent", animation: false, grid: { left: 48, right: 16, top: 30, bottom: 30 },
    legend: { top: 0, textStyle: { color: "#a1a1aa", fontSize: 11 } }, tooltip: TIP,
    xAxis: { type: "category", data: x, ...AX, splitLine: { show: false } },
    yAxis: { type: "value", scale: true, name: yName, nameTextStyle: { color: "#71717a" }, ...AX },
    series: lines.map((l, i) => ({ name: l.name, type: "line", data: l.data, connectNulls: true, symbolSize: i ? 5 : 8,
      lineStyle: { color: l.color, width: i ? 1.5 : 2.5, type: i ? "dashed" : "solid" }, itemStyle: { color: l.color } })),
  }), [x, lines, yName]);
  return <ReactECharts option={option} notMerge style={{ height }} theme="dark" />;
}

const state = (inv: boolean) => (inv ? "백워데이션 (단기 > 장기: 스트레스)" : "콘탱고 (단기 < 장기: 평상시)");

export default function Term() {
  const { data, error } = useApi<Res>("/api/term?days=504");
  const v = data?.vol;
  const ratio = useMemo(() => (v ? v.series["^VIX"]?.map((x, i) => (x && v.series["^VIX3M"]?.[i] ? Math.round((x / v.series["^VIX3M"][i]!) * 1000) / 1000 : null)) : []), [v]);
  const vc = data?.vol_curve, vf = data?.vix_futures;
  const inverted = (data?.vix_ratio?.now ?? 0) > 1;
  const f = vf?.curves.now ?? [];
  const m1m2 = data?.vix_m1m2?.at(-1);

  return (
    <div className="space-y-3">
      <Panel title="변동성·선물 기간구조 (콘탱고 / 백워데이션)">
        <Err error={error} />
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
          {data?.vix_ratio && <Kpi label="VIX ÷ VIX 3개월" value={data.vix_ratio.now.toFixed(3)} tone={inverted ? "down" : "up"}
            sub={`${state(inverted)} · 기간 내 ${data.vix_ratio.pctile.toFixed(0)}%ile · 최근 1년 역전 ${data.vix_ratio.days_inverted_1y}일`} />}
          {vc && <Kpi label={`VIX 30일 (${vc.date})`} value={vc.now[1]?.toFixed(2) ?? "—"} sub={`9일 ${vc.now[0] ?? "—"} · 3개월 ${vc.now[2] ?? "—"} · 6개월 ${vc.now[3] ?? "—"}`} />}
          {m1m2 && <Kpi label="VIX 선물 2번째 ÷ 1번째 월물" value={`${m1m2[1] > 0 ? "+" : ""}${m1m2[1].toFixed(1)}%`} tone={m1m2[1] < 0 ? "down" : "up"}
            sub={`${state(m1m2[1] < 0)} · 근월물 ${m1m2[2]} (${m1m2[0]})`} />}
          {data?.basis_now?.filter((b) => b.pair === "ES" || b.pair === "K200").map((b) => (
            <Kpi key={b.pair} label={`${data.pairs[b.pair]} 선물 베이시스 (${b.date})`} value={`${b.basis > 0 ? "+" : ""}${b.basis.toFixed(2)}%`} tone={b.basis < 0 ? "down" : "flat"}
              sub={`선물 ${b.fut.toLocaleString()} · 현물 ${b.spot.toLocaleString()} · ${b.basis < 0 ? "백워데이션" : "콘탱고"}`} />
          ))}
        </div>
        <div className="mt-2 text-[11px] text-zinc-500">
          평상시에는 먼 만기가 더 비쌉니다(콘탱고). 단기 공포가 커지면 가까운 만기가 더 비싸지는 백워데이션이 되고, VIX 곡선 역전은 급락장 한가운데에서 자주 나타납니다(이후 반등 국면과 겹치는 경우도 많음).
          주가지수 선물은 금리·배당 때문에 보통 현물보다 약간 비싸고, 현물보다 싸면 선물 매도 압력(헤지)이 강하다는 뜻입니다. 매매 신호 아님.
        </div>
      </Panel>

      <div className="grid gap-3 xl:grid-cols-2">
        {vc && (
          <Panel title="VIX 기간구조 (만기별 변동성 지수)">
            <Curve x={vc.labels} lines={SNAP.filter(([k]) => vc[k]).map(([k, l, c]) => ({ name: l, color: c, data: vc[k]! }))} />
          </Panel>
        )}
        {vf && f.length > 0 && (
          <Panel title={`VIX 선물 곡선 (CBOE 정산가, ${vf.date})`}>
            <Curve x={f.map((p) => p.expiry.slice(0, 7))} lines={SNAP.filter(([k]) => vf.curves[k]).map(([k, l, c]) => {
              const m = new Map(vf.curves[k].map((p) => [p.expiry.slice(0, 7), p.price]));
              return { name: l, color: c, data: f.map((p) => m.get(p.expiry.slice(0, 7)) ?? null) };
            })} />
            <div className="text-[11px] text-zinc-500">x축 = 만기 월. 이전 시점 곡선은 같은 만기끼리 비교합니다 (지나간 만기는 없음).</div>
          </Panel>
        )}
        {v && (
          <Panel title="VIX ÷ VIX 3개월 (1 위 = 변동성 곡선 역전)">
            <TimeChart dates={v.dates} series={[{ name: "VIX/VIX3M", color: "#f59e0b", type: "line", data: ratio }]} lines={[{ y: 1, label: "1.0", color: "#ef4444" }]}
              spy={v.series["^VIX"]} lowerName="VIX" height={380} />
          </Panel>
        )}
        {data?.vix_m1m2 && (
          <Panel title="VIX 선물 2번째 ÷ 1번째 월물 − 1 (%, 0 아래 = 백워데이션)">
            <TimeChart dates={data.vix_m1m2.map((x) => x[0])} series={[{ name: "M2/M1 − 1", color: "#38bdf8", type: "line", data: data.vix_m1m2.map((x) => x[1]) }]}
              lines={[{ y: 0, label: "0", color: "#ef4444" }]} spy={data.vix_m1m2.map((x) => x[2])} lowerName="VIX 근월물" height={380} yName="%" />
          </Panel>
        )}
        {data?.basis && (
          <Panel title="주가지수 선물 베이시스 (선물 ÷ 현물 − 1, %)">
            {(() => {
              const dates = [...new Set(Object.values(data.basis).flatMap((s) => s.map((x) => x[0])))].sort();
              const series = Object.entries(data.basis).map(([k, s]) => {
                const m = new Map(s);
                return { name: data.pairs[k] ?? k, color: PAIR_COLOR[k] ?? "#a1a1aa", type: "line" as const, data: dates.map((d) => m.get(d) ?? null) };
              });
              return <TimeChart dates={dates} series={series} lines={[{ y: 0, label: "0", color: "#ef4444" }]} height={380} yName="%" />;
            })()}
            <div className="text-[11px] text-zinc-500">미국: Yahoo 연속 근월물(만기 교체일에 튐), 한국: 네이버 코스피 200 선물. 선물과 현물 종가 시각이 달라 일별 값은 근사치입니다.</div>
          </Panel>
        )}
        {data?.crude && (
          <Panel title="WTI 원유 선물 곡선 (월물별)">
            <Curve x={data.crude.map((c) => c.contract)} lines={[{ name: "현재 가격 ($)", color: "#f59e0b", data: data.crude.map((c) => c.price) }]} />
            <div className="text-[11px] text-zinc-500">
              {data.crude.length > 1 && (data.crude[0].price > data.crude.at(-1)!.price ? "근월물이 원월물보다 비쌈 = 백워데이션 (현물 수급이 빡빡함)." : "근월물이 원월물보다 쌈 = 콘탱고 (공급 여유).")}
              {" "}근월물 {data.crude[0].price.toFixed(2)} → {data.crude.length}번째 월물 {data.crude.at(-1)!.price.toFixed(2)}.
            </div>
          </Panel>
        )}
        {v && (
          <Panel title="VVIX · VXN · VIX">
            <TimeChart dates={v.dates} series={[["^VIX", "VIX", "#f4f4f5"], ["^VXN", "VXN (나스닥 100)", "#38bdf8"]].map(([k, n, c]) => ({ name: n, color: c, type: "line" as const, data: v.series[k] ?? [] }))}
              spy={v.series["^VVIX"]} lowerName="VVIX" lowerColor="#f472b6" height={380} />
          </Panel>
        )}
      </div>
    </div>
  );
}
