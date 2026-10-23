"use client";
import { useState } from "react";
import { Err, Panel, Select } from "@/components/bits";
import { localTime } from "@/components/Shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { send, useApi, type Status } from "@/lib/api";
import { ALL_DEFS } from "@/lib/defs";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Val = { expected_session: string; sources: Record<string, any>; source_diff: Record<string, any>; reference: any[] };

const REF_METRICS = ["bull", "bear", "up4", "down4", "ratio5", "ratio10", "quarter_up25", "quarter_down25", "month_up25", "month_down25", "month_up50", "month_down50", "day34_up13", "day34_down13", "t2108"];
const J = ({ v }: { v: unknown }) => <pre className="max-h-60 overflow-auto whitespace-pre-wrap rounded bg-zinc-900 p-2 text-[11px] text-zinc-300">{JSON.stringify(v, null, 1)}</pre>;

export default function DataPage() {
  const st = useApi<Status>("/api/status", 5000);
  const val = useApi<Val>("/api/validation");
  const [msg, setMsg] = useState("");
  const [ref, setRef] = useState({ date: "", metric: "bear", value: "", note: "" });

  const refresh = async (source?: string) => {
    const r = await send<{ started: boolean; reason?: string }>(`/api/refresh${source ? `?source=${source}` : ""}`, "POST").catch((e) => ({ started: false, reason: String(e) }));
    setMsg(r.started ? `갱신 시작: ${source ?? "전체"}` : r.reason ?? "");
    setTimeout(st.reload, 1000);
  };
  const addRef = async () => {
    try {
      await send("/api/reference", "POST", { ...ref, value: Number(ref.value) });
      setMsg("기준값 저장됨");
      setRef({ ...ref, value: "", note: "" });
      val.reload();
    } catch (e) { setMsg(String(e)); }
  };
  const delRef = async (date: string, metric: string) => {
    await send(`/api/reference?date=${date}&metric=${metric}`, "DELETE");
    val.reload();
  };

  const s = st.data;
  return (
    <div className="space-y-3">
      <Err error={st.error} />
      <Panel title="데이터 소스 상태 (Data sources)" right={<>{msg && <span className="text-xs text-sky-400">{msg}</span>}<Button size="sm" variant="outline" onClick={() => refresh()}>전체 갱신</Button></>}>
        {s && (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-zinc-400"><tr><th className="text-left">소스</th><th>사용</th><th>최신 데이터 날짜</th><th>마지막 성공</th><th>마지막 시도</th><th>상태 / 진행</th><th className="text-left">마지막 오류</th><th /></tr></thead>
              <tbody>
                {Object.entries(s.sources).map(([k, v]) => (
                  <tr key={k} className="border-t border-zinc-900 text-center">
                    <td className="text-left font-mono">{k}<div className="text-[10px] text-zinc-500">{s.source_info[k]?.label ?? (k === "indices" ? "세계 지수·유가·금리 (Yahoo)" : "")}</div></td>
                    <td>{v.enabled ? "✔" : k === "massive" ? "API 키 없음" : "꺼짐"}</td>
                    <td className={v.latest_date === s.expected_session ? "text-emerald-400" : "text-amber-400"}>{v.latest_date ?? "—"}</td>
                    <td>{localTime(v.last_success)}</td><td>{localTime(v.last_attempt)}</td>
                    <td>{v.running ? `실행 중 ${v.progress ?? ""}` : "대기"}</td>
                    <td className="max-w-96 text-left text-red-400">{v.last_error ? `${v.last_error} (${localTime(v.last_error_at)})` : ""}</td>
                    <td>{v.enabled && <Button size="sm" variant="ghost" onClick={() => refresh(k)} disabled={s.busy}>갱신</Button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="mt-2 text-[11px] text-zinc-500">
              자동 갱신: 서버 실행 중 {"매 15분"} 확인 → 최신 완료 거래일(뉴욕 18:00 ET 이후 확정, NYSE 휴장일·서머타임 반영)보다 늦은 소스만 수집. 소스가 아직 갱신되지 않았으면 60분 후 재시도.
              마지막 확인: {localTime(s.scheduler?.last_check)} · Massive 키: {s.massive_key ? "설정됨" : "없음 (.env 의 MASSIVE_API_KEY)"}
            </div>
          </div>
        )}
      </Panel>

      <Panel title="원본 수치 비교 (Validation vs TC2000 / 원본 Market Monitor)">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Input type="date" className="h-7 w-36 text-xs" value={ref.date} onChange={(e) => setRef({ ...ref, date: e.target.value })} />
          <Select value={ref.metric} onChange={(m) => setRef({ ...ref, metric: m })} options={REF_METRICS.map((m) => [m, ALL_DEFS.find((d) => d.key === m)?.ko + ` (${m})`])} />
          <Input className="h-7 w-24 text-xs" placeholder="원본 값" value={ref.value} onChange={(e) => setRef({ ...ref, value: e.target.value })} />
          <Input className="h-7 w-56 text-xs" placeholder="메모 (예: TC2000 스캔 결과)" value={ref.note} onChange={(e) => setRef({ ...ref, note: e.target.value })} />
          <Button size="sm" onClick={addRef} disabled={!ref.date || ref.value === ""}>추가</Button>
        </div>
        <table className="mt-2 w-full font-mono text-xs">
          <thead className="text-zinc-400"><tr><th className="text-left">날짜</th><th>지표</th><th>원본 값</th><th className="text-left">소스별 계산값 (차이)</th><th className="text-left">메모</th><th /></tr></thead>
          <tbody>
            {(val.data?.reference ?? []).map((r) => (
              <tr key={r.date + r.metric} className="border-t border-zinc-900 text-center">
                <td className="text-left">{r.date}</td><td>{r.metric}</td><td>{r.reference}</td>
                <td className="text-left">{Object.entries(r.by_source as Record<string, { value: number; diff: number }>).map(([k, v]) => (
                  <span key={k} className="mr-3">{k}: {v.value} <span className={v.diff === 0 ? "text-emerald-400" : "text-amber-400"}>({v.diff > 0 ? "+" : ""}{v.diff})</span></span>
                ))}{!Object.keys(r.by_source).length && <span className="text-zinc-600">해당 날짜 계산값 없음</span>}</td>
                <td className="text-left font-sans text-zinc-400">{r.note}</td>
                <td><button className="text-red-400" onClick={() => delRef(r.date, r.metric)}>삭제</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-2 text-[11px] text-zinc-500">
          차이 발생 시 확인 순서: ① 종목 유니버스 (아래 유형 필터·거래소 구성) ② 주가 조정 방식 (분할 보정) ③ 데이터 누락 (누락 거래일·종목) ④ 거래량 조건 (거래량 0/누락). 원본 수치에 억지로 맞추지 않습니다.
        </div>
      </Panel>

      <Panel title="데이터 검증 리포트 (Data quality)" right={<Button size="sm" variant="ghost" onClick={val.reload}>다시 검사</Button>}>
        <Err error={val.error} />
        {val.loading && <div className="text-xs text-zinc-500">검사 중…</div>}
        {val.data && (
          <div className="space-y-3 text-xs">
            <div>기대 거래일 (NYSE): {val.data.expected_session}</div>
            {Object.entries(val.data.sources).map(([k, v]) => (
              <div key={k} className="rounded border border-zinc-800 p-2">
                <div className="font-mono font-semibold">{k}: {v.first_date} ~ {v.latest_date} · 지연 {v.lag_sessions}거래일 · 누락 거래일 {v.missing_sessions.length}개 {v.missing_sessions.length ? `(${v.missing_sessions.slice(0, 10).join(", ")})` : "✔"}</div>
                {v.bars && (
                  <div className="mt-1 grid gap-2 md:grid-cols-2">
                    <div>
                      <div>행 {v.bars.summary.rows?.toLocaleString()} · 종목 {v.bars.summary.tickers} · {v.bars.summary.first_date} ~ {v.bars.summary.last_date}</div>
                      <div>비정상 가격(≤0): {v.bars.summary.bad_close} · 거래량 0/누락 행: {v.bars.summary.zero_volume} · 중복 (종목,날짜): {v.bars.duplicate_ticker_dates}</div>
                      <div>최신일 {v.bars.latest_day.date}: {v.bars.latest_day.tickers}종목, 거래량 0 {v.bars.latest_day.zero_volume}</div>
                      <div>종목 수 급감 거래일: {v.bars.thin_sessions.length ? v.bars.thin_sessions.map((t: any) => `${t.date}(${t.tickers})`).join(", ") : "없음 ✔"}</div>
                      <div className="mt-1 text-zinc-400">하루 +300% / −80% 초과 변동 (분할 미반영 의심, 최근 50건):</div>
                      <J v={v.bars.extreme_moves} />
                    </div>
                    {v.universe && (
                      <div>
                        <div>유니버스: 전체 심볼 {v.universe.total_symbols} → 보통주 {v.universe.included} · 중복 티커 {v.universe.duplicate_tickers}{v.universe.delisted_tracked !== undefined && ` · 상장폐지 추적 ${v.universe.delisted_tracked}`}</div>
                        <div>거래소별: {JSON.stringify(v.universe.by_exchange)}</div>
                        {v.universe.excluded_by_reason && <div>제외 사유: {JSON.stringify(v.universe.excluded_by_reason)}</div>}
                        <div className="mt-1 text-zinc-400">유형 필터 점검 — 포함됐지만 이름이 의심스러운 종목 {v.universe.suspicious_count}개 (Trust/Partners 등, 대부분 정상 보통주):</div>
                        <J v={v.universe.suspicious_names_included} />
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
            <div className="font-semibold">소스 간 20% Bull/Bear 차이 (최근 250거래일)</div>
            {Object.entries(val.data.source_diff).map(([pair, m]) => (
              <div key={pair} className="font-mono">
                {pair}: {Object.entries(m as Record<string, any>).map(([k, x]) => <span key={k} className="mr-4">{k} 평균절대차 {x.mean_abs_diff} · 상관 {x.corr} · 정확일치 {x.exact_match_pct}%</span>)}
              </div>
            ))}
          </div>
        )}
      </Panel>


      <Panel title="실행 로그 (Log)">
        <div className="max-h-80 overflow-auto font-mono text-[11px]">
          {(s?.log ?? []).map((l, i) => (
            <div key={i} className={l.level === "error" ? "text-red-400" : l.level === "warn" ? "text-amber-400" : "text-zinc-400"}>
              <span className="text-zinc-600">{localTime(l.t)}</span> [{l.source}] <span className="whitespace-pre-wrap">{l.msg}</span>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
