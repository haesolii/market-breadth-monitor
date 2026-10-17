// Indicator definitions shown in tooltips / headers. Formulas = the original
// published TC2000 scans (v12.4 thresholds); see docs/indicator-definitions.md.

export type Kind = "up" | "down" | "ratio" | "diff" | "pct";

export type Def = {
  key: string;
  ko: string;
  en: string;
  short: string;
  kind: Kind;
  formula: string;
  note?: string;
  /** Default highlight levels. up/down: [strong, extreme] (value >=). ratio/diff/pct: [low, high]. */
  levels: [number | null, number | null];
};

const LIQ = "AVGC20 * AVGV20 >= 250000";

export const DEFS: Def[] = [
  { key: "up4", ko: "일간 4% 상승", en: "Daily 4% Up", short: "4%↑", kind: "up",
    formula: "100*(C-C1)/C1 >= 4 AND V >= 100000 AND V > V1",
    note: "원문 해석 참고: 300 이상 높음, 1000 이상 극단 (공식 매매 신호 아님)", levels: [300, 1000] },
  { key: "down4", ko: "일간 4% 하락", en: "Daily 4% Down", short: "4%↓", kind: "down",
    formula: "100*(C-C1)/C1 <= -4 AND V >= 100000 AND V > V1",
    note: "원문 해석 참고: 300 이상 높음, 1000 이상 극단", levels: [300, 1000] },
  { key: "ratio5", ko: "5일 매수·매도 강도 비율", en: "5 Day Breadth Ratio", short: "5D 비율", kind: "ratio",
    formula: "SUM(4% Up, 5일) / SUM(4% Down, 5일)  — 분모 0이면 표시 안 함(N/A)",
    note: "원문은 10일 비율만 해석(>2 강세 추진, <0.5 약세). 5일 비율 공식은 원문에 없음", levels: [0.5, 2] },
  { key: "ratio10", ko: "10일 매수·매도 강도 비율", en: "10 Day Breadth Ratio", short: "10D 비율", kind: "ratio",
    formula: "SUM(4% Up, 10일) / SUM(4% Down, 10일)  — 분모 0이면 N/A",
    note: "원문 해석 참고: 2 이상 강세 추진(thrust), 0.5 이하 약세 전환", levels: [0.5, 2] },
  { key: "quarter_up25", ko: "분기 25% 상승", en: "25% Up in Quarter", short: "Q 25%↑", kind: "up",
    formula: `100*((C+.01)-(MINC65+.01))/(MINC65+.01) >= 25 AND ${LIQ}`,
    note: "주요 지표(primary). 65거래일 최저 종가 대비", levels: [null, null] },
  { key: "quarter_down25", ko: "분기 25% 하락", en: "25% Down in Quarter", short: "Q 25%↓", kind: "down",
    formula: `100*((C+.01)-(MAXC65+.01))/(MAXC65+.01) <= -25 AND ${LIQ}`,
    note: "주요 지표(primary). 65거래일 최고 종가 대비", levels: [null, null] },
  { key: "month_up25", ko: "월간 25% 상승", en: "25% Up in Month", short: "M 25%↑", kind: "up",
    formula: `C20 >= 5 AND ${LIQ} AND 100*(C-C20)/C20 >= 25`, note: "원문: 200 이상은 드묾", levels: [200, null] },
  { key: "month_down25", ko: "월간 25% 하락", en: "25% Down in Month", short: "M 25%↓", kind: "down",
    formula: `C20 >= 5 AND ${LIQ} AND 100*(C-C20)/C20 <= -25`, note: "원문: 200 이상은 드묾", levels: [200, null] },
  { key: "month_up50", ko: "월간 50% 상승", en: "50% Up in Month", short: "M 50%↑", kind: "up",
    formula: `C20 >= 5 AND ${LIQ} AND 100*(C-C20)/C20 >= 50`, note: "원문 해석 참고: 20 이상 과열", levels: [20, null] },
  { key: "month_down50", ko: "월간 50% 하락", en: "50% Down in Month", short: "M 50%↓", kind: "down",
    formula: `C20 >= 5 AND ${LIQ} AND 100*(C-C20)/C20 <= -50`, note: "원문 해석 참고: 20 이상 과매도 반등 가능", levels: [20, null] },
  { key: "day34_up13", ko: "34일 13% 상승", en: "13% Up in 34 Days", short: "34/13↑", kind: "up",
    formula: `100*((C+.01)-(MINC34+.01))/(MINC34+.01) >= 13 AND ${LIQ}`, note: "원문: 고정 임계값 없음", levels: [null, null] },
  { key: "day34_down13", ko: "34일 13% 하락", en: "13% Down in 34 Days", short: "34/13↓", kind: "down",
    formula: `100*((C+.01)-(MAXC34+.01))/(MAXC34+.01) <= -13 AND ${LIQ}`, note: "원문: 고정 임계값 없음", levels: [null, null] },
  { key: "day34_diff", ko: "34/13 차이", en: "34/13 Differential", short: "34/13 Δ", kind: "diff",
    formula: "13% Up in 34 Days − 13% Down in 34 Days", levels: [null, null] },
  { key: "t2108", ko: "40일선 위 종목 비율", en: "T2108 (% above 40-day MA)", short: "T2108", kind: "pct",
    formula: "100 * COUNT(C > AVGC40) / COUNT(40거래일 이상 데이터 보유 종목)",
    note: "Worden T2108 재현(자체 정의, 원문 공식 없음). 기본 강조 20/80은 사용자 설정", levels: [20, 80] },
];

export const BB_DEFS: Def[] = [
  { key: "bull", ko: "20% 급등 (Bull)", en: "5-Day 20% Up", short: "Bull", kind: "up",
    formula: "C/C5 >= 1.2 AND MINV3.1 > 100000 AND C >= 5", levels: [null, null] },
  { key: "bear", ko: "20% 급락 (Bear)", en: "5-Day 20% Down", short: "Bear", kind: "down",
    formula: "C/C5 < 0.8 AND MINV3.1 > 100000 AND C >= 5", levels: [50, 100] },
];

export const ALL_DEFS = [...DEFS, ...BB_DEFS];
export const defOf = (k: string) => ALL_DEFS.find((d) => d.key === k);

export const SIGNALS: Record<string, string> = {
  bull20: "20% 급등", bear20: "20% 급락", up4: "4% 상승", down4: "4% 하락",
  q_up25: "분기 25%↑", q_down25: "분기 25%↓", m_up25: "월 25%↑", m_down25: "월 25%↓",
  m_up50: "월 50%↑", m_down50: "월 50%↓", d34_up13: "34일 13%↑", d34_down13: "34일 13%↓",
};

export const fmt = (v: unknown, digits = 0) =>
  v === null || v === undefined || v === "" || Number.isNaN(v as number)
    ? "—"
    : typeof v === "number"
      ? v.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits })
      : String(v);

export type Levels = Record<string, [number | null, number | null]>;
/** Default highlight levels. Count thresholds come from the original US readings, so for other
 * markets (나스닥·코스피·코스닥, different universe sizes) only scale-free ones (ratios, T2108) are preset. */
export const defaultLevels = (market = "yahoo"): Levels => {
  const us = market === "yahoo" || market === "massive" || market === "public_repo";
  return Object.fromEntries(ALL_DEFS.map((d) => [d.key, us || d.kind === "ratio" || d.kind === "pct" ? d.levels : [null, null]]));
};

/** Tailwind classes for a cell: green for up-type, red for down-type, darker past the user's levels. */
export function cellClass(d: Def, v: unknown, levels: Levels): string {
  if (typeof v !== "number") return "text-zinc-600";
  const [a, b] = levels[d.key] ?? d.levels;
  if (d.kind === "up" || d.kind === "down") {
    const g = d.kind === "up";
    if (b !== null && v >= b) return g ? "bg-emerald-600 text-white font-semibold" : "bg-red-600 text-white font-semibold";
    if (a !== null && v >= a) return g ? "bg-emerald-900/70 text-emerald-200" : "bg-red-900/70 text-red-200";
    return g ? "text-emerald-400" : "text-red-400";
  }
  const mid = d.kind === "ratio" ? 1 : d.kind === "pct" ? 50 : 0;
  if (b !== null && v >= b) return "bg-emerald-700 text-white font-semibold";
  if (a !== null && v <= a) return "bg-red-700 text-white font-semibold";
  return v >= mid ? "text-emerald-400" : "text-red-400";
}
