"use client";
import dynamic from "next/dynamic";
import { useMemo } from "react";
import { useApi } from "@/lib/api";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

// Yahoo quotes these as yields in percent -> daily change shown in basis points.
const YIELDS = new Set(["^IRX", "^FVX", "^TNX", "^TYX"]);
// Rising = bad for stocks: tooltip colors inverted, same as the world-index table.
const INVERSE = new Set([...YIELDS, "^VIX"]);
const num = (v: number | null | undefined, d = 2) => (v === null || v === undefined ? "—" : v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }));

const sma = (v: number[], n: number) => v.map((_, i) => (i + 1 >= n ? +(v.slice(i + 1 - n, i + 1).reduce((a, b) => a + b, 0) / n).toFixed(2) : null));

/** Daily candles + 50/200-day SMA of a world-index symbol from our own (Yahoo) data —
 * used wherever TradingView's free widget does not carry the index itself.
 * sessions = trading days shown initially (126 ≈ 6개월, 252 ≈ 1년, 756 ≈ 3년); drag/zoom for more. */
export function IndexChart({ symbol, height = 520, compact = false, sessions = 252 }: { symbol: string; height?: number; compact?: boolean; sessions?: number }) {
  // Small (compact) charts only load the visible period plus ~1 year for the 200-day average.
  const since = useMemo(() => {
    if (!compact) return "";
    const d = new Date();
    d.setDate(d.getDate() - Math.round(sessions * 1.45) - 320);
    return `&since=${d.toISOString().slice(0, 10)}`;
  }, [compact, sessions]);
  const { data, error } = useApi<Record<string, [string, number, number, number, number][]>>(
    `/api/world/history?ohlc=true&symbols=${encodeURIComponent(symbol)}${since}`);
  const option = useMemo(() => {
    const rows = data?.[symbol] ?? [];
    if (!rows.length) return null;
    const closes = rows.map((r) => r[4]);
    const start = Math.max(0, 100 - (sessions / rows.length) * 100);
    const ma50 = sma(closes, 50), ma200 = sma(closes, 200);
    const isYield = YIELDS.has(symbol);
    const tip = (ps: { dataIndex: number }[]) => {
      const i = ps[0]?.dataIndex ?? -1;
      const r = rows[i];
      if (!r) return "";
      const prev = i > 0 ? rows[i - 1][4] : null;
      const chg = prev ? (isYield ? (r[4] - prev) * 100 : (r[4] / prev - 1) * 100) : null;
      const good = chg !== null && (INVERSE.has(symbol) ? chg < 0 : chg > 0);
      const col = chg === null || chg === 0 ? "#e4e4e7" : good ? "#34d399" : "#f87171";
      const chgTxt = chg === null ? "—" : `${chg > 0 ? "+" : ""}${chg.toFixed(isYield ? 1 : 2)}${isYield ? "bp" : "%"}`;
      return `<b>${r[0]}</b><br/>종가 <b>${num(r[4])}</b> <span style="color:${col};font-weight:600">${chgTxt}</span> <span style="color:#a1a1aa">(전일 대비)</span>` +
        `<br/><span style="color:#a1a1aa">시 ${num(r[1])} · 고 ${num(r[2])} · 저 ${num(r[3])}</span>` +
        `<br/><span style="color:#38bdf8">50일선 ${num(ma50[i])}</span> · <span style="color:#f59e0b">200일선 ${num(ma200[i])}</span>`;
    };
    return {
      backgroundColor: "transparent", animation: false,
      grid: { left: 8, right: compact ? 52 : 60, top: compact ? 8 : 28, bottom: compact ? 22 : 56, containLabel: false },
      legend: compact ? undefined : { top: 0, textStyle: { color: "#d4d4d8" }, data: ["50일선", "200일선"] },
      tooltip: { trigger: "axis", axisPointer: { type: "cross" }, backgroundColor: "#18181b", borderColor: "#3f3f46", textStyle: { color: "#e4e4e7", fontSize: 11 }, formatter: tip },
      xAxis: { type: "category", data: rows.map((r) => r[0]), boundaryGap: true, axisLabel: { color: "#a1a1aa", fontSize: 10 }, axisLine: { lineStyle: { color: "#3f3f46" } } },
      yAxis: { type: "value", scale: true, position: "right", axisLabel: { color: "#a1a1aa", fontSize: 10 }, splitLine: { lineStyle: { color: "#27272a" } } },
      dataZoom: [{ type: "inside", start, end: 100 }, ...(compact ? [] : [{ type: "slider", start, end: 100, bottom: 8, height: 18, textStyle: { color: "#a1a1aa" } }])],
      series: [
        { name: symbol, type: "candlestick", data: rows.map((r) => [r[1], r[4], r[3], r[2]]),
          itemStyle: { color: "#10b981", color0: "#ef4444", borderColor: "#10b981", borderColor0: "#ef4444" } },
        { name: "50일선", type: "line", data: ma50, showSymbol: false, lineStyle: { color: "#38bdf8", width: 1 } },
        { name: "200일선", type: "line", data: ma200, showSymbol: false, lineStyle: { color: "#f59e0b", width: 1 } },
      ],
    };
  }, [data, symbol, compact, sessions]);
  if (error) return <div className="p-3 text-xs text-red-400">{error}</div>;
  if (!option) return <div className="flex items-center justify-center text-xs text-zinc-500" style={{ height }}>불러오는 중…</div>;
  return <ReactECharts option={option} notMerge style={{ height }} theme="dark" />;
}
