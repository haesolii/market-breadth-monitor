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

type Vals = Record<string, number | null | undefined>;

/** Stockbee's count thresholds (300, 500, 1,000 ...) were set on the whole US market (~5,000 stocks).
 * US universes (나스닥 included) scale them by universe size; the US keeps the originals. */
export const US_N = 5000;
export const scaleOf = (x: Vals) => Math.min(1, (x.eligible_universe_count || US_N) / US_N);
/** Korea and crypto use calibrated counts instead (docs "시장별 기준값"): the count the market reaches
 * as rarely as the US level is reached in the US (Market Monitor: US current listings 2021-10~;
 * Bear: US incl. delisted 2016~), rounded. Keyed market -> indicator -> US level. */
const CAL: Record<string, Record<string, Record<number, number>>> = {
  kospi: { up4: { 100: 20, 300: 46, 500: 78, 1000: 124 }, down4: { 300: 30, 500: 91, 1000: 225 },
    quarter_up25: { 200: 26, 500: 66 }, month_up25: { 200: 33 }, month_down25: { 200: 10 },
    month_up50: { 20: 3 }, month_down50: { 20: 1 }, bear: { 50: 6, 100: 14, 150: 25 } },
  kosdaq: { up4: { 100: 60, 300: 120, 500: 185, 1000: 280 }, down4: { 300: 85, 500: 225, 1000: 535 },
    quarter_up25: { 200: 75, 500: 165 }, month_up25: { 200: 100 }, month_down25: { 200: 45 },
    month_up50: { 20: 12 }, month_down50: { 20: 1 }, bear: { 50: 20, 100: 55, 150: 105 } },
  crypto: { up4: { 100: 15, 300: 65, 500: 160, 1000: 245 }, down4: { 300: 85, 500: 210, 1000: 320 },
    quarter_up25: { 200: 5, 500: 25 }, month_up25: { 200: 40 }, month_down25: { 200: 45 },
    month_up50: { 20: 3 }, month_down50: { 20: 1 }, bear: { 50: 40, 100: 180, 150: 245 } },
};
/** A "broad" reading needs at least this many stocks: a calibrated 1-3 (e.g. KOSPI 50% movers) is noise. */
export const MIN_N = 5;
/** A US count threshold of indicator `key` expressed for this row's market (rows carry `market`). */
export const cnt = (base: number, x: Vals, key: string) =>
  Math.max(MIN_N, CAL[String((x as Record<string, unknown>).market)]?.[key]?.[base]
    ?? Math.ceil(base * scaleOf(x) - 1e-9));  // round up: small markets stay conservative

export type Levels = Record<string, [number | null, number | null]>;
/** Default highlight levels; count levels scaled to the universe size `n` (latest eligible count). */
export const defaultLevels = (n?: number | null, market?: string): Levels => {
  const x = { eligible_universe_count: n, market } as unknown as Vals;
  return Object.fromEntries(ALL_DEFS.map((d) => {
    const sc = (v: number | null) => (v === null ? null : cnt(v, x, d.key));
    return [d.key, d.kind === "up" || d.kind === "down" ? [sc(d.levels[0]), sc(d.levels[1])] : d.levels];
  }));
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

const at = (x: Vals, k: string) => x[k] ?? 0;
/** This row's market Bear line i (1..3). */
export const bearLv = (x: Vals, i: 1 | 2 | 3) => cnt([50, 100, 150][i - 1], x, "bear");
const f = (v: number) => v.toLocaleString("en-US");
/** Stockbee reading criteria + interpretation per Market Monitor row. Count thresholds are scaled
 * to the row's universe (cnt), so rule(x) prints the thresholds actually applied. */
export const READ: Record<string, { rule: (x: Vals) => string; read: (v: number, x: Vals) => string }> = {
  up4: { rule: (x) => `${f(cnt(300, x, "up4"))}↑ 매수세 강화, ${f(cnt(500, x, "up4"))}↑ 강한 매수세`,
    read: (v, x) => v >= cnt(500, x, "up4") ? "🟢 강한 매수세" : v >= cnt(300, x, "up4") ? "🟢 매수세 강화" : v >= cnt(100, x, "up4") ? "⚪ 보통" : "🔴 매수세 매우 약함" },
  down4: { rule: (x) => `${f(cnt(500, x, "down4"))}~${f(cnt(1000, x, "down4"))} 강한 매도세, ${f(cnt(1000, x, "down4"))}↑ 극단적 투매`,
    read: (v, x) => v >= cnt(1000, x, "down4") ? "🔴 극단적 투매" : v >= cnt(500, x, "down4") ? "🔴 강한 매도세" : v > at(x, "up4") ? "🟠 매도 우위, 극단적 투매는 아님" : "⚪ 매도 압력 낮음" },
  ratio5: { rule: () => "1 미만 매도 우위, 0.5 이하 약세 심화",
    read: (v) => v >= 2 ? "🟢 강한 매수세" : v >= 1 ? "🟢 매수 우위" : v > 0.5 ? "🟠 매도 우위" : "🔴 단기 약세 심화" },
  ratio10: { rule: () => "0.5 이하 약세 신호, 2 이상 강한 매수세",
    read: (v) => v >= 2 ? "🟢 강한 매수세 (thrust)" : v >= 1 ? "🟢 매수 우위" : v <= 0.5 ? "🔴 약세 신호" : v < 0.6 ? "🟠 약세 기준 근접" : "🟠 매도 우위" },
  quarter_up25: { rule: (x) => `${f(cnt(500, x, "quarter_up25"))} 이하 반등 관찰, ${f(cnt(200, x, "quarter_up25"))} 이하 극단적 약세`,
    read: (v, x) => v <= cnt(200, x, "quarter_up25") ? "🔴 극단적 약세" : v <= cnt(500, x, "quarter_up25") ? "🟠 반등 관찰 구간" : v < at(x, "quarter_down25") ? "🟠 중기 상승 종목 부족" : "🟢 중기 상승 우위" },
  quarter_down25: { rule: () => "상승 종목 수와 비교해 중기 추세 판단",
    read: (v, x) => v > 2 * at(x, "quarter_up25") ? "🔴 중기 하락 종목 압도적" : v > at(x, "quarter_up25") ? "🟠 중기 하락 우위" : "🟢 중기 상승 우위" },
  month_up25: { rule: (x) => `${f(cnt(200, x, "month_up25"))}↑ 강한 상승 확산, 하락 종목 수와 비교`,
    read: (v, x) => v >= cnt(200, x, "month_up25") ? "🟢 강한 상승 확산" : v >= at(x, "month_down25") ? "🟢 상승 우위" : v >= at(x, "month_down25") / 2 ? "🟠 상승 탄력 약함" : "🔴 단기 상승 탄력 부족" },
  month_down25: { rule: () => "상승 종목 수와 비교해 하락 확산 평가",
    read: (v, x) => v > 2 * at(x, "month_up25") ? "🔴 하락 종목 우세" : v > at(x, "month_up25") ? "🟠 하락 우위" : "🟢 상승 우위" },
  month_up50: { rule: (x) => `${f(cnt(20, x, "month_up50"))}↑ 과열, 하락 종목 수와 비교`,
    read: (v, x) => v >= cnt(20, x, "month_up50") ? "🟢 강한 상승 확산 (과열 주의)" : v < at(x, "month_down50") ? "🔴 강한 상승 종목 희소" : "⚪ 보통" },
  month_down50: { rule: (x) => `${f(cnt(20, x, "month_down50"))}개 초과 시 극단적 약세, 역추세 반등 관찰`,
    read: (v, x) => v > cnt(20, x, "month_down50") ? "🟠 극단적 하락, 반등 가능성 관찰" : "⚪ 보통" },
  day34_up13: { rule: () => "상승 종목의 증가·감소 추세 확인",
    read: (v, x) => v >= at(x, "day34_down13") ? "🟢 상승 종목 우위" : v >= at(x, "day34_down13") / 3 ? "🟠 반등 종목 존재하나 우세하지 않음" : "🔴 상승 종목 희소" },
  day34_down13: { rule: () => "상승 종목과 비교해 시장 폭 판단",
    read: (v, x) => v > 2 * at(x, "day34_up13") ? "🔴 광범위한 약세" : v > at(x, "day34_up13") ? "🟠 하락 우위" : "🟢 상승 우위" },
  day34_diff: { rule: () => "양수 상승 우위, 음수 하락 우위",
    read: (v) => v > 0 ? "🟢 상승 종목 우위" : v < 0 ? "🔴 하락 압력 우세" : "⚪ 균형" },
  // 20% Bull/Bear: no published Stockbee thresholds; 50/100/150 are this app's US Bear lines (cnt per market).
  bull: { rule: () => "Bear 수와 비교 (앱 기준, 원문 임계값 없음)",
    read: (v, x) => v >= 2 * at(x, "bear") ? "🟢 상승 모멘텀 우위" : v >= at(x, "bear") ? "🟢 상승 우위" : v >= at(x, "bear") / 2 ? "🟠 하락 우위" : "🔴 상승 모멘텀 부족" },
  bear: { rule: (x) => `${f(bearLv(x, 1))}↑ 급락 증가, ${f(bearLv(x, 2))}↑ 극단적 급락 (시장별 기준선)`,
    read: (v, x) => v >= bearLv(x, 2) ? "🔴 극단적 급락, 과매도 반등 관찰" : v >= bearLv(x, 1) ? "🟠 급락 종목 증가" : v > at(x, "bull") ? "🟠 하락 우위" : "⚪ 급락 압력 낮음" },
  t2108: { rule: () => "20% 미만 극단적 과매도, 80% 초과 과매수",
    read: (v) => v < 20 ? "🔴 극단적 과매도, 반등 관찰" : v < 30 ? "🟠 약세·과매도 접근" : v > 80 ? "🟠 과매수" : v >= 50 ? "🟢 양호" : "⚪ 중립" },
};
