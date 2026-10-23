"use client";
import Link from "next/link";
import { Fragment, useState } from "react";
import { Err, Panel, Select } from "@/components/bits";
import { Input } from "@/components/ui/input";
import { useApi } from "@/lib/api";
import { downloadCSV } from "@/lib/csv";
import { useSetting } from "@/lib/settings";
import { stockHref } from "@/lib/stock";

type Rep = { nid: number; date: string; broker: string; code: string; name: string; title: string; goal: number | null; opinion: string;
  prev_goal: number | null; goal_chg: number | null; react1d: number | null; ret_since: number | null; last_close: number | null; upside: number | null };
type Cov = { code: string; name: string; n: number; brokers: number; react: number | null; upside: number | null };
type Feed = { latest?: string; rows: Rep[]; brokers: string[]; top_covered: Cov[]; up: Rep[]; down: Rep[] };
type StockRes = { code: string; name?: string; rows: Rep[]; consensus: { brokers: number; mean: number; high: number; low: number; last_close: number | null; upside: number | null } | null };
type Earn = { date: string; symbol: string; name: string; time: string; eps: number | null; eps_forecast: number | null; surprise: number | null;
  n_est: number | null; mcap: number | null; quarter: string; react: number | null; react_days: number | null; ret_since: number | null };
type EarnRes = { reported: Earn[]; upcoming: Earn[] };

const pct = (v: number | null | undefined, d = 1) => (v === null || v === undefined ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(d)}%`);
const tone = (v: number | null | undefined) => (v === null || v === undefined ? "text-zinc-600" : v > 0 ? "text-emerald-400" : v < 0 ? "text-red-400" : "");
const won = (v: number | null | undefined) => (v === null || v === undefined ? "—" : v.toLocaleString("ko-KR", { maximumFractionDigits: 0 }));
const usd = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `$${v.toFixed(2)}`);
const cap = (v: number | null) => (v === null ? "—" : v >= 1e12 ? `$${(v / 1e12).toFixed(2)}T` : `$${(v / 1e9).toFixed(1)}B`);
const TIME: Record<string, string> = { pre: "장전", after: "장후", "": "—" };

function Tabs({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: [string, string][] }) {
  return (
    <div className="flex overflow-hidden rounded border border-zinc-700 text-xs">
      {options.map(([k, l]) => <button key={k} onClick={() => onChange(k)} className={`px-3 py-1 ${value === k ? "bg-sky-700 text-white" : "text-zinc-300 hover:bg-zinc-800"}`}>{l}</button>)}
    </div>
  );
}

function Analyst() {
  const [days, setDays] = useSetting("reports.days", "7");
  const [kind, setKind] = useState("all");
  const [broker, setBroker] = useState("");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const [code, setCode] = useState<string | null>(null);
  const { data, error, loading } = useApi<Feed>(`/api/analyst?days=${days}&kind=${kind}&broker=${encodeURIComponent(broker)}&q=${encodeURIComponent(q)}`);
  const st = useApi<StockRes>(code ? `/api/analyst/stock?code=${code}` : null);
  const Name = ({ r }: { r: { code: string; name: string } }) => <button className="text-left text-sky-300 hover:underline" onClick={() => setCode(r.code)}>{r.name}</button>;

  return (
    <div className="space-y-3">
      <Panel title="증권사 리포트 (Korean broker reports)" right={<>
        <Input className="h-7 w-40 text-xs" placeholder="종목·코드·제목 검색" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select value={broker} onChange={setBroker} options={[["", "모든 증권사"], ...(data?.brokers ?? []).map((b) => [b, b] as [string, string])]} />
        <Tabs value={kind} onChange={setKind} options={[["all", "전체"], ["up", "목표가 상향"], ["down", "목표가 하향"], ["new", "첫 목표가"]]} />
        <Select value={days} onChange={setDays} options={[["1", "1일"], ["7", "7일"], ["30", "30일"], ["90", "90일"]]} />
      </>}>
        <div className="text-[11px] text-zinc-500">
          네이버 리서치 기업 리포트 · 최신 {data?.latest ?? "—"} · 발간일 반응 = 발간일 종가 ÷ 전 거래일 종가 · 이후 = 최근 종가 ÷ 발간 전일 종가 · 상승여력 = 목표가 ÷ 최근 종가.
          행을 누르면 네이버 리서치의 리포트 원문으로 연결됩니다. 투자 권유 아님.
        </div>
      </Panel>
      <Err error={error} />
      <div className="grid gap-3 xl:grid-cols-4">
        <Panel className="xl:col-span-3" title={`리포트 ${data?.rows.length ?? 0}건${loading ? " · 불러오는 중…" : ""}`} right={<button className="text-xs text-sky-400" onClick={() => data && downloadCSV(`reports_${days}d.csv`, data.rows)}>CSV</button>}>
          <div className="max-h-[640px] overflow-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-zinc-900 text-zinc-400"><tr>
                <th className="text-left">날짜</th><th className="text-left">증권사</th><th className="text-left">종목</th><th className="text-left">제목</th><th>의견</th>
                <th>목표가</th><th>변경</th><th title="발간일 종가 ÷ 전 거래일 종가">발간일 반응</th><th title="최근 종가 ÷ 발간 전일 종가">이후</th><th>상승여력</th>
              </tr></thead>
              <tbody>
                {(data?.rows ?? []).map((r) => (
                  <Fragment key={r.nid}>
                    <tr className={`cursor-pointer border-t border-zinc-900 text-center hover:bg-zinc-900 ${open === r.nid ? "bg-zinc-900" : ""}`} onClick={() => setOpen(open === r.nid ? null : r.nid)}>
                      <td className="whitespace-nowrap text-left font-mono">{r.date.slice(5)}</td><td className="whitespace-nowrap text-left">{r.broker}</td>
                      <td className="whitespace-nowrap text-left" onClick={(e) => e.stopPropagation()}><Name r={r} /></td>
                      <td className="max-w-80 truncate text-left" title={r.title}>{r.title}</td><td>{r.opinion}</td>
                      <td className="font-mono">{won(r.goal)}</td>
                      <td className={`font-mono ${tone(r.goal_chg)}`} title={r.prev_goal ? `이전 ${won(r.prev_goal)}` : "이 증권사의 첫 목표가"}>{r.prev_goal === null ? "신규" : r.goal_chg ? pct(r.goal_chg) : "유지"}</td>
                      <td className={`font-mono ${tone(r.react1d)}`}>{pct(r.react1d)}</td><td className={`font-mono ${tone(r.ret_since)}`}>{pct(r.ret_since)}</td>
                      <td className={`font-mono ${tone(r.upside)}`}>{pct(r.upside, 0)}</td>
                    </tr>
                    {open === r.nid && <tr><td colSpan={10} className="bg-zinc-950 px-3 py-2 text-left">
                      <a href={`https://stock.naver.com/research/company/${r.nid}`} target="_blank" rel="noreferrer" className="text-sky-400 hover:underline">리포트 원문 보기 (네이버 리서치) ↗</a>
                    </td></tr>}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
        <div className="space-y-3">
          {[["목표가 상향 상위", data?.up], ["목표가 하향 상위", data?.down]].map(([t, rows]) => (
            <Panel key={t as string} title={t as string}>
              <table className="w-full text-xs"><tbody>
                {((rows as Rep[]) ?? []).map((r) => (
                  <tr key={r.nid} className="border-t border-zinc-900">
                    <td><Name r={r} /> <span className="text-zinc-500">{r.broker}</span></td>
                    <td className={`text-right font-mono ${tone(r.goal_chg)}`}>{pct(r.goal_chg, 0)}</td>
                    <td className={`text-right font-mono ${tone(r.react1d)}`} title="발간일 반응">{pct(r.react1d)}</td>
                  </tr>
                ))}
              </tbody></table>
            </Panel>
          ))}
          <Panel title="리포트가 많이 나온 종목">
            <table className="w-full text-xs"><tbody>
              {(data?.top_covered ?? []).map((c) => (
                <tr key={c.code} className="border-t border-zinc-900">
                  <td><Name r={c} /></td><td className="text-right font-mono">{c.n}건 · {c.brokers}곳</td>
                  <td className={`text-right font-mono ${tone(c.react)}`} title="발간일 반응 평균">{pct(c.react)}</td>
                </tr>
              ))}
            </tbody></table>
          </Panel>
        </div>
      </div>
      {code && (
        <Panel title={`${st.data?.name ?? code} (${code}) — 증권사 리포트 이력`} right={<><Link className="text-xs text-sky-400 hover:underline" href={stockHref(code)}>종목 상세 →</Link><button className="text-xs text-zinc-400" onClick={() => setCode(null)}>닫기</button></>}>
          <Err error={st.error} />
          {st.data?.consensus && (
            <div className="mb-2 flex flex-wrap gap-4 font-mono text-xs">
              <span>최근 90일 증권사 {st.data.consensus.brokers}곳 평균 목표가 <b>{won(st.data.consensus.mean)}</b></span>
              <span>최고 {won(st.data.consensus.high)} · 최저 {won(st.data.consensus.low)}</span>
              <span>최근 종가 {won(st.data.consensus.last_close)} · 평균 대비 상승여력 <span className={tone(st.data.consensus.upside)}>{pct(st.data.consensus.upside)}</span></span>
            </div>
          )}
          <div className="max-h-80 overflow-auto">
            <table className="w-full text-xs"><tbody>
              {(st.data?.rows ?? []).map((r) => (
                <tr key={r.nid} className="border-t border-zinc-900 text-center">
                  <td className="text-left font-mono">{r.date}</td><td className="text-left">{r.broker}</td><td className="max-w-96 truncate text-left" title={r.title}>{r.title}</td>
                  <td>{r.opinion}</td><td className="font-mono">{won(r.goal)}</td><td className={`font-mono ${tone(r.goal_chg)}`}>{r.goal_chg ? pct(r.goal_chg) : ""}</td>
                  <td className={`font-mono ${tone(r.react1d)}`}>{pct(r.react1d)}</td>
                </tr>
              ))}
            </tbody></table>
          </div>
        </Panel>
      )}
    </div>
  );
}

function Earnings() {
  const [back, setBack] = useSetting("earn.back", "7");
  const [minCap, setMinCap] = useSetting("earn.cap", "2e9");
  const { data, error } = useApi<EarnRes>(`/api/earnings?back=${back}&ahead=14&min_cap=${minCap}`);
  const byDate = (data?.upcoming ?? []).reduce<Record<string, Earn[]>>((m, e) => ({ ...m, [e.date]: [...(m[e.date] ?? []), e] }), {});
  return (
    <div className="space-y-3">
      <Panel title="미국 실적 발표 (US earnings)" right={<>
        <Select value={minCap} onChange={setMinCap} options={[["1e10", "시총 $10B 이상"], ["2e9", "시총 $2B 이상"], ["3e8", "시총 $300M 이상"]]} />
        <Select value={back} onChange={setBack} options={[["1", "최근 1일"], ["7", "최근 7일"], ["30", "최근 30일"]]} />
      </>}>
        <div className="text-[11px] text-zinc-500">
          Nasdaq 실적 캘린더 · 서프라이즈 = (실제 EPS − 예상) ÷ |예상| · 반응: 장전 발표는 발표일 종가 ÷ 전일, 장후 발표는 다음 날 종가 ÷ 발표일, 시간 미상은 발표 전일→다음 날 2일 반응.
        </div>
      </Panel>
      <Err error={error} />
      <div className="grid gap-3 xl:grid-cols-3">
        <Panel className="xl:col-span-2" title={`발표 완료 (${data?.reported.length ?? 0})`} right={<button className="text-xs text-sky-400" onClick={() => data && downloadCSV(`earnings_${back}d.csv`, data.reported)}>CSV</button>}>
          <div className="max-h-[640px] overflow-auto">
            <table className="w-full font-mono text-xs">
              <thead className="sticky top-0 bg-zinc-900 text-zinc-400"><tr>
                <th className="text-left">날짜</th><th>시간</th><th className="text-left">종목</th><th>EPS</th><th>예상</th><th>서프라이즈</th><th>반응</th><th>이후</th><th>시총</th>
              </tr></thead>
              <tbody>
                {(data?.reported ?? []).map((e) => (
                  <tr key={e.date + e.symbol} className="border-t border-zinc-900 text-center hover:bg-zinc-900">
                    <td className="text-left">{e.date.slice(5)}</td><td className="font-sans">{TIME[e.time]}</td>
                    <td className="max-w-64 truncate text-left" title={e.name}><b>{e.symbol}</b> <span className="font-sans text-zinc-500">{e.name}</span></td>
                    <td>{usd(e.eps)}</td><td className="text-zinc-400">{usd(e.eps_forecast)}</td>
                    <td className={tone(e.surprise)}>{pct(e.surprise)}</td>
                    <td className={tone(e.react)} title={e.react_days === 2 ? "발표 시간 미상: 2일 반응" : "1일 반응"}>{pct(e.react)}{e.react_days === 2 && <sup className="text-zinc-500">2d</sup>}</td>
                    <td className={tone(e.ret_since)}>{pct(e.ret_since)}</td><td>{cap(e.mcap)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
        <Panel title="발표 예정 (14일)">
          <div className="max-h-[640px] space-y-2 overflow-auto text-xs">
            {Object.entries(byDate).map(([d, es]) => (
              <div key={d}>
                <div className="font-mono font-semibold text-zinc-300">{d} <span className="font-sans font-normal text-zinc-500">({es.length})</span></div>
                <div className="mt-0.5 flex flex-wrap gap-1">
                  {es.slice(0, 40).map((e) => (
                    <span key={e.symbol} className="rounded bg-zinc-900 px-1.5 py-0.5 font-mono" title={`${e.name} · ${TIME[e.time]} · 예상 EPS ${usd(e.eps_forecast)} · ${cap(e.mcap)}`}>
                      {e.symbol}<span className="ml-1 text-[10px] text-zinc-500">{TIME[e.time]}</span>
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}

type Dart = { rcept_no: string; date: string; code: string; name: string; market: string; title: string; react: number | null; ret_since: number | null; url: string;
  extra: number; correction: boolean; subsidiary: boolean };

function DartPrelim() {
  const [days, setDays] = useSetting("reports.dart.days", "30");
  const { data, error } = useApi<{ enabled: boolean; rows: Dart[] }>(`/api/dart?days=${days}`);
  return (
    <Panel title="잠정실적 공시 (한국, DART)" right={<Select value={days} onChange={setDays} options={[["7", "7일"], ["30", "30일"], ["90", "90일"]]} />}>
      <Err error={error} />
      {data && !data.enabled ? (
        <div className="text-xs text-zinc-400">
          DART API 키가 없어 꺼져 있습니다. <a className="text-sky-400 hover:underline" href="https://opendart.fss.or.kr" target="_blank" rel="noreferrer">opendart.fss.or.kr</a>에서 무료 인증키를 받아
          GitHub Secret <code>DART_API_KEY</code>(로컬은 .env)에 넣으면 다음 갱신부터 최근 120일 공시가 수집됩니다.
        </div>
      ) : (
        <div className="max-h-[640px] overflow-auto">
          <table className="w-full font-mono text-xs">
            <thead className="sticky top-0 bg-zinc-900 text-zinc-400"><tr><th className="text-left">공시일</th><th className="text-left">종목</th><th className="text-left">공시</th>
              <th title="공시일 전 거래일 종가 → 공시일 다음 거래일 종가 (공시 시각을 몰라 2거래일로 측정)">반응</th><th title="공시 전 종가 → 최근 종가">이후</th></tr></thead>
            <tbody>{(data?.rows ?? []).map((r) => (
              <tr key={r.rcept_no} className="border-t border-zinc-900 text-center hover:bg-zinc-900">
                <td className="text-left">{r.date}</td>
                <td className="text-left font-sans"><Link className="text-sky-300 hover:underline" href={stockHref(r.code, r.market)}>{r.name}</Link> <span className="text-zinc-500">{r.code}</span></td>
                <td className="text-left font-sans"><a className="hover:underline" href={r.url} target="_blank" rel="noreferrer">{r.title}</a>
                  {r.correction && <span className="ml-1 rounded bg-amber-900/60 px-1 text-[10px] text-amber-200">정정</span>}
                  {r.extra > 0 && <span className="ml-1 text-[10px] text-zinc-500" title={r.subsidiary ? "같은 날 별도·자회사 실적 공시 포함" : "같은 날 함께 낸 공시"}>외 {r.extra}건{r.subsidiary ? " (자회사 포함)" : ""}</span>}</td>
                <td className={tone(r.react)}>{pct(r.react)}</td><td className={tone(r.ret_since)}>{pct(r.ret_since)}</td>
              </tr>
            ))}</tbody>
          </table>
          {data && !data.rows.length && <div className="py-6 text-center text-xs text-zinc-500">해당 기간 잠정실적 공시 없음</div>}
          <div className="mt-1 text-[11px] text-zinc-500">DART 목록 API는 실적 수치를 주지 않으므로 공시 제목을 누르면 원문(매출·영업이익)이 열립니다. 같은 회사가 같은 날 낸 연결·별도·자회사·정정 공시는 한 줄로 묶었습니다 (월별 실적을 공시하는 회사는 매달 나옴).</div>
        </div>
      )}
    </Panel>
  );
}

type Ev = Dart & { category: string };

function DartEvents() {
  const [days, setDays] = useSetting("reports.events.days", "7");
  const [cat, setCat] = useState("");
  const { data, error } = useApi<{ categories: string[]; rows: Ev[] }>(`/api/dart/events?days=${days}&category=${encodeURIComponent(cat)}`);
  return (
    <Panel title={`주요 공시 (한국, DART) ${data?.rows.length ?? 0}건`} right={<>
      <Select value={cat} onChange={setCat} options={[["", "전체 유형"], ...(data?.categories ?? []).map((c) => [c, c] as [string, string])]} />
      <Select value={days} onChange={setDays} options={[["3", "3일"], ["7", "7일"], ["30", "30일"]]} />
    </>}>
      <Err error={error} />
      <div className="max-h-[680px] overflow-auto">
        <table className="w-full font-mono text-xs">
          <thead className="sticky top-0 bg-zinc-900 text-zinc-400"><tr><th className="text-left">공시일</th><th className="text-left">종목</th><th className="text-left">유형</th><th className="text-left">공시</th>
            <th title="공시일 전 거래일 종가 → 공시일 다음 거래일 종가">반응</th><th title="공시 전 종가 → 최근 종가">이후</th></tr></thead>
          <tbody>{(data?.rows ?? []).map((r) => (
            <tr key={r.rcept_no} className="border-t border-zinc-900 text-center hover:bg-zinc-900">
              <td className="text-left">{r.date}</td>
              <td className="max-w-40 truncate text-left font-sans"><Link className="text-sky-300 hover:underline" href={stockHref(r.code, r.market)}>{r.name}</Link></td>
              <td className="whitespace-nowrap text-left font-sans text-zinc-300">{r.category}</td>
              <td className="text-left font-sans"><a className="hover:underline" href={r.url} target="_blank" rel="noreferrer">{r.title}</a></td>
              <td className={tone(r.react)}>{pct(r.react)}</td><td className={tone(r.ret_since)}>{pct(r.ret_since)}</td>
            </tr>
          ))}</tbody>
        </table>
        {data && !data.rows.length && <div className="py-6 text-center text-xs text-zinc-500">해당 기간 공시 없음 (DART 키가 없으면 수집되지 않음)</div>}
      </div>
      <div className="mt-1 text-[11px] text-zinc-500">유상증자·무상증자·자사주(매입·처분·소각)·최대주주 변경·공급계약(수주)·CB/BW·합병·분할·감자·공개매수·소송·거래정지 공시를 모았습니다. 반응은 공시 시각을 몰라 2거래일 기준.</div>
    </Panel>
  );
}

export default function Reports() {
  const [tab, setTab] = useSetting("reports.tab", "analyst");
  return (
    <div className="space-y-3">
      <Tabs value={tab} onChange={setTab} options={[["analyst", "증권사 리포트 (한국)"], ["dart", "잠정실적 (한국)"], ["events", "주요 공시 (한국)"], ["earnings", "실적 발표 (미국)"]]} />
      {tab === "analyst" ? <Analyst /> : tab === "dart" ? <DartPrelim /> : tab === "events" ? <DartEvents /> : <Earnings />}
    </div>
  );
}
