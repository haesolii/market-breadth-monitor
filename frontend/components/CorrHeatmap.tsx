"use client";
import dynamic from "next/dynamic";
import { useMemo } from "react";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

/** Correlation matrix (rows × cols, -1..1): red (negative) - neutral - green (positive), values in cells. */
export function CorrHeatmap({ rows, cols, matrix, height = 420, left = 120 }: {
  rows: string[]; cols?: string[]; matrix: (number | null)[][]; height?: number; left?: number;
}) {
  const xs = cols ?? rows;
  const option = useMemo(() => ({
    backgroundColor: "transparent", animation: false,
    tooltip: { backgroundColor: "#18181b", borderColor: "#3f3f46", textStyle: { color: "#e4e4e7", fontSize: 12 },
      formatter: (p: { value: [number, number, number | string] }) => `${rows[p.value[1]]} × ${xs[p.value[0]]}<br/><b>상관계수 ${p.value[2]}</b>` },
    grid: { left, right: 10, top: 10, bottom: xs.length > 6 ? 110 : 60 },
    xAxis: { type: "category", data: xs, axisLabel: { color: "#a1a1aa", rotate: xs.length > 6 ? 60 : 0, fontSize: 10, interval: 0 }, splitArea: { show: false } },
    yAxis: { type: "category", data: rows, inverse: true, axisLabel: { color: "#a1a1aa", fontSize: 10, interval: 0 } },
    visualMap: { min: -1, max: 1, calculable: false, orient: "horizontal", left: "center", bottom: 0, itemHeight: 140, textStyle: { color: "#a1a1aa" },
      inRange: { color: ["#dc2626", "#7f1d1d", "#27272a", "#065f46", "#10b981"] } },
    series: [{ type: "heatmap", data: matrix.flatMap((row, i) => row.map((v, j) => [j, i, v === null ? "-" : v.toFixed(2)])),
      label: { show: xs.length * rows.length <= 400, fontSize: 9, color: "#fafafa" }, itemStyle: { borderColor: "#09090b", borderWidth: 1 } }],
  }), [rows, xs, matrix, left]);
  return <ReactECharts option={option} notMerge style={{ height }} theme="dark" />;
}
