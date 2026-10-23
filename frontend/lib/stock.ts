export type Who = "foreign" | "inst" | "indiv";
export const WHO: [Who, string, string][] = [["foreign", "외국인", "#38bdf8"], ["inst", "기관", "#f59e0b"], ["indiv", "개인", "#a78bfa"]];
/** 억원 with sign. */
export const eok = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${v > 0 ? "+" : ""}${Math.round(v).toLocaleString("ko-KR")}억`);
/** Stock detail page; `q` (a name) when the ticker is unknown (Korean ETF holdings carry names only). */
export const stockHref = (ticker: string, market?: string) => `/stock?t=${encodeURIComponent(ticker)}${market ? `&m=${market}` : ""}`;
export const stockByName = (name: string) => `/stock?q=${encodeURIComponent(name)}`;
export const MK: Record<string, string> = { yahoo: "미국", nasdaq: "나스닥", kospi: "코스피", kosdaq: "코스닥", crypto: "크립토" };
