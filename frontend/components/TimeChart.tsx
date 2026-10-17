"use client";
import dynamic from "next/dynamic";
import { useMemo, useRef } from "react";
import type { ECharts, EChartsOption } from "echarts";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

export type S = { name: string; data: (number | null)[]; color: string; type?: "bar" | "line"; mirror?: boolean };

/** Breadth series (top) + optional benchmark index close (bottom) on one shared date axis.
 * mirror=true plots the series below zero (Bear) while tooltips show the real value. */
export function TimeChart({ dates, series, spy, lines = [], onSelect, selected, height = 460, yName, lowerName = "S&P 500", lowerBar = false, lowerColor = "#e4e4e7", rebased = false }: {
  dates: string[];
  series: S[];
  spy?: (number | null)[];
  lines?: { y: number; label: string; color: string }[];
  onSelect?: (d: string) => void;
  selected?: string | null;
  height?: number;
  yName?: string;
  lowerName?: string;
  lowerBar?: boolean;
  lowerColor?: string;
  /** Series are rebased to 100: tooltips also show the % change since the start. */
  rebased?: boolean;
}) {
  const ref = useRef({ dates, onSelect });
  ref.current = { dates, onSelect };
  const option = useMemo<EChartsOption>(() => {
    const two = !!spy;
    // Mirrored (below-zero) series show absolute values; otherwise keep real signs (e.g. negative spreads).
    const mirrored = series.some((s) => s.mirror);
    const fmtV = (v: number) => (mirrored ? Math.abs(v) : v).toLocaleString("en-US", { maximumFractionDigits: 2 });
    const grids = two
      ? [{ left: 56, right: 16, top: 40, height: "54%" }, { left: 56, right: 16, top: "70%", bottom: 56 }]
      : [{ left: 56, right: 16, top: 40, bottom: 56 }];
    const axis = (i: number) => ({
      type: "category" as const, data: dates, gridIndex: i, boundaryGap: true,
      axisLabel: { show: i === grids.length - 1, color: "#a1a1aa" }, axisLine: { lineStyle: { color: "#3f3f46" } },
    });
    return {
      backgroundColor: "transparent",
      animation: false,
      legend: { top: 0, textStyle: { color: "#d4d4d8" } },
      tooltip: {
        trigger: "axis", axisPointer: { type: "cross", link: [{ xAxisIndex: "all" }] },
        backgroundColor: "#18181b", borderColor: "#3f3f46", textStyle: { color: "#e4e4e7", fontSize: 12 },
        valueFormatter: (v) => (v === null || v === undefined ? "—" : fmtV(Number(v))),
        // Rebased (=100) series also show % since the start; the lower panel keeps plain values.
        ...(rebased ? {
          formatter: (ps: { axisValue: string; seriesIndex: number; seriesName: string; value: number | null; color: string }[]) =>
            `<b>${ps[0]?.axisValue ?? ""}</b><br/>` + ps.map((p) => {
              const v = p.value === null || p.value === undefined ? null : Number(p.value);
              const txt = v === null ? "—" : p.seriesIndex < series.length
                ? `${v.toFixed(2)} <span style="color:${v >= 100 ? "#34d399" : "#f87171"};font-weight:600">${v >= 100 ? "+" : ""}${(v - 100).toFixed(2)}%</span>`
                : v.toLocaleString("en-US", { maximumFractionDigits: 2 });
              return `<span style="display:inline-block;width:8px;height:8px;border-radius:4px;background:${p.color};margin-right:4px"></span>${p.seriesName}: ${txt}`;
            }).join("<br/>"),
        } : {}),
      },
      axisPointer: { link: [{ xAxisIndex: "all" }] },
      grid: grids,
      xAxis: grids.map((_, i) => axis(i)),
      yAxis: [
        { type: "value", gridIndex: 0, name: yName, nameGap: 14, nameTextStyle: { color: "#a1a1aa", align: "left" }, axisLabel: { color: "#a1a1aa", formatter: (v: number) => fmtV(v) }, splitLine: { lineStyle: { color: "#27272a" } } },
        ...(two ? [{ type: "value" as const, gridIndex: 1, scale: !lowerBar, axisLabel: { color: "#a1a1aa" }, splitLine: { lineStyle: { color: "#27272a" } } }] : []),
      ],
      dataZoom: [{ type: "inside", xAxisIndex: grids.map((_, i) => i) }, { type: "slider", xAxisIndex: grids.map((_, i) => i), bottom: 8, height: 18, textStyle: { color: "#a1a1aa" } }],
      series: [
        ...series.map((s, i) => ({
          name: s.name, type: s.type ?? "bar", xAxisIndex: 0, yAxisIndex: 0,
          data: s.mirror ? s.data.map((v) => (v === null ? null : -v)) : s.data,
          itemStyle: { color: s.color }, lineStyle: { color: s.color, width: 1.5 }, showSymbol: false, connectNulls: true, barGap: "-100%", large: true,
          markLine: i === 0 ? {
            symbol: "none", silent: true,
            data: [
              ...lines.map((l) => ({ yAxis: l.y, lineStyle: { color: l.color, type: "dashed" as const }, label: { formatter: l.label, color: l.color, position: "insideEndTop" as const, backgroundColor: "rgba(9,9,11,0.85)", padding: [1, 4], borderRadius: 2 } })),
              ...(selected ? [{ xAxis: selected, lineStyle: { color: "#38bdf8" }, label: { formatter: selected, color: "#38bdf8", backgroundColor: "rgba(9,9,11,0.85)", padding: [1, 4] } }] : []),
            ],
          } : undefined,
        })),
        ...(two ? [{ name: lowerName, type: (lowerBar ? "bar" : "line") as "bar", xAxisIndex: 1, yAxisIndex: 1, data: spy, showSymbol: false, lineStyle: { color: lowerColor, width: 1.2 }, itemStyle: { color: lowerColor } }] : []),
      ],
    } as EChartsOption;
  }, [dates, series, spy, lines, selected, yName, lowerName, lowerBar, lowerColor, rebased]);

  // Clicking anywhere in a plot selects the date under the axis pointer (not only on bars).
  const hover = useRef<string | null>(null);
  const events = useMemo(() => ({
    updateAxisPointer: (e: { axesInfo?: { axisDim: string; value: number }[] }) => {
      const x = e.axesInfo?.find((a) => a.axisDim === "x");
      if (x) hover.current = ref.current.dates[x.value] ?? null;
    },
  }), []);
  const onReady = (chart: ECharts) => {
    chart.getZr().on("click", () => {
      if (hover.current) ref.current.onSelect?.(hover.current);
    });
  };

  return <ReactECharts option={option} notMerge style={{ height }} onChartReady={onReady} onEvents={events} theme="dark" />;
}
