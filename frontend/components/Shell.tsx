"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { send, useApi, type Status } from "@/lib/api";
import { StockSearch } from "@/components/StockSearch";
import { Button } from "@/components/ui/button";

/** Menu by purpose (was one numbered list of 19). */
const GROUPS: [string, [string, string][]][] = [
  ["오늘의 시장", [["/", "종합 시장 현황"], ["/monitor", "시장 모니터"], ["/leaders", "주도주·추세"], ["/bullbear", "20% 급등락"], ["/research", "지표 흐름·과거 통계"], ["/scanner", "조건 충족 종목"]]],
  ["섹터·종목", [["/sectors", "섹터 히트맵"], ["/stock", "종목 상세"], ["/watch", "관심종목"], ["/etf", "액티브 ETF"]]],
  ["한국 시장", [["/flows", "수급·증시 자금"], ["/reports", "리포트·실적·공시"]]],
  ["글로벌·매크로", [["/world", "세계 지수"], ["/macro", "매크로"], ["/term", "변동성·선물 구조"], ["/board", "차트 보드"]]],
  ["정보", [["/news", "뉴스"], ["/calendar", "일정 캘린더"]]],
  ["커뮤니티", [["/community", "게시판"]]],
];
const MENU = GROUPS.flatMap(([, items]) => items);
const active = (href: string, path: string) => path === href || (href !== "/" && path.startsWith(href + "/"));

/** Phones have no hover: a tap on anything with a description (title=) shows it in a sheet for a few seconds. */
function TapTitles() {
  const [text, setText] = useState<string | null>(null);
  useEffect(() => {
    if (!window.matchMedia("(hover: none)").matches) return;
    let timer: ReturnType<typeof setTimeout>;
    const onTap = (e: Event) => {
      const el = (e.target as HTMLElement).closest?.("[title]") as HTMLElement | null;
      const t = el?.getAttribute("title");
      if (!t) return;
      setText(t);
      clearTimeout(timer);
      timer = setTimeout(() => setText(null), 5000);
    };
    document.addEventListener("click", onTap, true);
    return () => { document.removeEventListener("click", onTap, true); clearTimeout(timer); };
  }, []);
  if (!text) return null;
  return (
    <div onClick={() => setText(null)} className="fixed inset-x-3 bottom-3 z-50 whitespace-pre-line rounded-lg border border-zinc-700 bg-zinc-900/95 p-3 text-xs leading-relaxed text-zinc-200 shadow-xl">
      {text}<div className="pt-1 text-[10px] text-zinc-500">눌러서 닫기</div>
    </div>
  );
}

export const localTime = (iso?: string | null) => (iso ? new Date(iso).toLocaleString("ko-KR", { hour12: false }) : "—");

export function StatusBar() {
  const { data: st, error, reload } = useApi<Status>("/api/status", 60000);
  const path = usePathname();
  useEffect(() => {  // visitors and page views for the daily report (the cached status call can't count)
    const ping = () => fetch(`/api/visit?page=${encodeURIComponent(path)}`, { cache: "no-store" }).catch(() => {});
    ping();
    const t = setInterval(() => fetch("/api/visit", { cache: "no-store" }).catch(() => {}), 10 * 60 * 1000);
    return () => clearInterval(t);
  }, [path]);
  const [msg, setMsg] = useState<string | null>(null);
  const refresh = async () => {
    try {
      const r = await send<{ started: boolean; reason?: string }>("/api/refresh", "POST");
      setMsg(r.started ? "갱신 시작됨 (Refresh started)" : r.reason ?? "");
      setTimeout(reload, 1500);
    } catch (e) {
      setMsg(String(e));
    }
  };
  if (error)
    return (
      <div className="bg-red-950 px-4 py-2 text-sm text-red-200">
        백엔드 연결 실패 (Backend unreachable): {error} — start.bat 으로 서버를 실행했는지 확인하세요.
      </div>
    );
  if (!st) return <div className="px-4 py-2 text-xs text-zinc-500">상태 확인 중…</div>;
  const errs = Object.entries(st.sources).filter(([, s]) => s.enabled && s.last_error);
  const lastOk = Object.values(st.sources).map((s) => s.last_success).filter(Boolean).sort().pop();
  // One line: overall state + the two markets' sessions; only lagging / provisional sources are named.
  const shown = ["public_repo", "yahoo", "kospi", "kosdaq", "crypto", "massive", "indices"].filter((s) => st.sources[s]?.enabled);
  const label = (s: string) => st.source_info[s]?.short ?? (s === "indices" ? "세계 지수" : s);
  const lag = shown.filter((s) => (st.sources[s].latest_date ?? "") < (st.sources[s].expected ?? st.expected_session));
  const prov = shown.filter((s) => st.sources[s].provisional);
  const schedule = process.env.NEXT_PUBLIC_AUTH === "1"
    ? "갱신: 장중 약 5분마다 (잠정값) · 확정 08:15 (미국) · 18:40 (한국) KST"
    : `갱신: 미국 ${st.final_hours?.NYSE ?? 18}:00 ET · 한국 ${st.final_hours?.XKRX ?? 18}:00 KST 이후 (${st.refresh_min ?? 15}분마다 확인)`;
  const detail = [...shown.map((s) => `${label(s)}: ${st.sources[s].latest_date ?? "없음"}${st.sources[s].provisional ? " (장중 잠정)" : ""}`), schedule].join("\n");
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-zinc-800 bg-zinc-950 px-4 py-2 text-xs">
      <span className="cursor-help" title={detail}>
        <span className={lag.length ? "text-amber-400" : "text-emerald-400"}>●</span>{" "}
        {lag.length ? "일부 지연" : "데이터 최신"}
        <span className="text-zinc-400"> · 완료 거래일 </span><b className="text-zinc-100">미국 {st.expected_session}</b>
        {st.expected_sessions?.XKRX && <b className="text-zinc-100"> · 한국 {st.expected_sessions.XKRX}</b>}
      </span>
      {lag.map((s) => <span key={s} className="text-amber-400">{label(s)} {st.sources[s].latest_date ?? "없음"}</span>)}
      {prov.length > 0 && <span className="text-sky-400" title="장중 값으로 계산한 잠정치 — 장 마감 확정 후 다시 계산됩니다">장중 잠정: {prov.map(label).join(", ")}</span>}
      {shown.some((s) => st.sources[s].running) && <span className="text-sky-400">갱신 중 ⟳</span>}
      <span className="text-zinc-500" title={schedule}>마지막 갱신 {localTime(lastOk)}</span>
      {errs.length > 0 && (
        <Link href="/data" className="text-red-400 underline">
          오류 {errs.length}건 (errors)
        </Link>
      )}
      {msg && <span className="text-sky-400">{msg}</span>}
      <div className="order-first w-full sm:order-none sm:ml-auto sm:w-64"><StockSearch placeholder="종목 검색 (이름·티커)" /></div>
      {process.env.NEXT_PUBLIC_AUTH === "1" ? (
        <span className="text-[11px] text-zinc-500">자동 갱신</span>
      ) : (
        <Button size="sm" variant="outline" className="h-7" onClick={refresh} disabled={st.busy}>
          {st.busy ? "갱신 중…" : "수동 갱신 (Refresh)"}
        </Button>
      )}
    </div>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  if (path === "/login") return <>{children}</>;
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <nav className="shrink-0 border-zinc-800 bg-zinc-950 md:w-56 md:border-r">
        <div className="px-4 py-3">
          <div className="font-mono text-sm font-bold text-emerald-400">MARKET BREADTH</div>
          <div className="text-[10px] text-zinc-500">시장 폭 연구용 · 투자 권유 아님</div>
        </div>
        {/* phones: one native menu (grouped) instead of a long scroll strip */}
        <div className="px-3 pb-2 md:hidden">
          <select value={MENU.find(([h]) => active(h, path))?.[0] ?? ""} onChange={(e) => router.push(e.target.value)} aria-label="메뉴"
            className="w-full rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100">
            {!MENU.some(([h]) => active(h, path)) && <option value="">메뉴 선택</option>}
            {GROUPS.map(([g, items]) => <optgroup key={g} label={g}>{items.map(([href, ko]) => <option key={href} value={href}>{ko}</option>)}</optgroup>)}
          </select>
        </div>
        <div className="hidden px-2 pb-2 md:block">
          {GROUPS.map(([g, items]) => (
            <div key={g} className="pb-2">
              <div className="px-3 pb-1 pt-2 text-[10px] font-semibold tracking-wide text-zinc-500">{g}</div>
              <ul className="space-y-0.5">
                {items.map(([href, ko]) => (
                  <li key={href}>
                    <Link href={href} className={`block whitespace-nowrap rounded px-3 py-1.5 text-sm ${active(href, path) ? "bg-zinc-800 text-white" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"}`}>{ko}</Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <Link href="/privacy" className="block px-5 pb-1 text-[11px] text-zinc-600 hover:text-zinc-300">개인정보처리방침</Link>
        {process.env.NEXT_PUBLIC_AUTH === "1" && (
          <a href="/auth/logout" className="block px-5 pb-3 text-[11px] text-zinc-500 hover:text-zinc-300">로그아웃</a>
        )}
      </nav>
      <div className="min-w-0 flex-1">
        <StatusBar />
        <main className="p-3 md:p-4">{children}</main>
      </div>
      <TapTitles />
    </div>
  );
}
