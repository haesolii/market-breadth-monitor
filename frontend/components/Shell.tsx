"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { send, useApi, type Status } from "@/lib/api";
import { Button } from "@/components/ui/button";

const MENU = [
  ["/", "1. 종합 시장 현황", "Market Overview"],
  ["/bullbear", "2. 20% 급등락 분석", "20% Bull/Bear Study"],
  ["/monitor", "3. 시장 모니터", "Market Monitor"],
  ["/research", "4. 지표 흐름·과거 통계", "Indicator Flow & Research"],
  ["/scanner", "5. 조건 충족 종목 검색", "Scanner Results"],
  ["/world", "6. 세계 지수", "World Indices"],
  ["/macro", "7. 매크로", "Macro"],
  ["/board", "8. 차트 보드", "Chart Board"],
  ["/sectors", "9. 섹터 히트맵", "Sector Heatmap"],
  ["/etf", "10. 액티브 ETF", "Active ETF Holdings"],
  ["/reports", "11. 리포트·실적", "Reports & Earnings"],
  ["/flows", "12. 한국 수급", "Korea Investor Flows"],
  ["/stock", "13. 종목 상세", "Stock Detail"],
  ["/leaders", "14. 주도주·추세", "Leaders & Trend (Qullamaggie)"],
  ["/watch", "15. 관심종목", "Watchlist & Alerts"],
  ["/calendar", "16. 일정 캘린더", "Earnings & Macro Calendar"],
  ["/term", "17. 변동성·선물 구조", "Volatility & Futures Curve"],
  ["/news", "18. 뉴스", "News"],
  ["/community", "19. 게시판", "Community Board"],
];

export const localTime = (iso?: string | null) => (iso ? new Date(iso).toLocaleString("ko-KR", { hour12: false }) : "—");

export function StatusBar() {
  const { data: st, error, reload } = useApi<Status>("/api/status", 60000);
  useEffect(() => {  // visitor count for the daily report (the cached status call can't count)
    const ping = () => fetch("/api/visit", { cache: "no-store" }).catch(() => {});
    ping();
    const t = setInterval(ping, 10 * 60 * 1000);
    return () => clearInterval(t);
  }, []);
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
      {process.env.NEXT_PUBLIC_AUTH === "1" ? (
        <span className="ml-auto text-[11px] text-zinc-500">자동 갱신</span>
      ) : (
        <Button size="sm" variant="outline" className="ml-auto h-7" onClick={refresh} disabled={st.busy}>
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
          <div className="text-[10px] text-zinc-500">시장 폭 (Market Breadth) 연구용 · 투자 권유 아님</div>
        </div>
        {/* phones: one native menu instead of a 17-item scroll strip */}
        <div className="px-3 pb-2 md:hidden">
          <select value={MENU.some(([h]) => h === path) ? path : ""} onChange={(e) => router.push(e.target.value)} aria-label="메뉴"
            className="w-full rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100">
            {!MENU.some(([h]) => h === path) && <option value="">메뉴 선택</option>}
            {MENU.map(([href, ko]) => <option key={href} value={href}>{ko}</option>)}
          </select>
        </div>
        <ul className="hidden gap-1 px-2 pb-2 md:flex md:flex-col">
          {MENU.map(([href, ko, en]) => (
            <li key={href}>
              <Link
                href={href}
                className={`block whitespace-nowrap rounded px-3 py-2 text-sm ${path === href || (href === "/community" && path.startsWith("/community")) ? "bg-zinc-800 text-white" : "text-zinc-400 hover:bg-zinc-900"}`}
              >
                {ko}
                <div className="text-[10px] text-zinc-500">{en}</div>
              </Link>
            </li>
          ))}
        </ul>
        {process.env.NEXT_PUBLIC_AUTH === "1" && (
          <a href="/auth/logout" className="block px-5 pb-3 text-[11px] text-zinc-500 hover:text-zinc-300">로그아웃</a>
        )}
      </nav>
      <div className="min-w-0 flex-1">
        <StatusBar />
        <main className="p-3 md:p-4">{children}</main>
      </div>
    </div>
  );
}
