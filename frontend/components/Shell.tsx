"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { send, useApi, type Status } from "@/lib/api";
import { Button } from "@/components/ui/button";

const MENU = [
  ["/", "1. 종합 시장 현황", "Market Overview"],
  ["/bullbear", "2. 20% 급등락 분석", "20% Bull/Bear Study"],
  ["/monitor", "3. 시장 모니터", "Market Monitor"],
  ["/research", "4. 과거 시장 통계", "Historical Research"],
  ["/scanner", "5. 조건 충족 종목 검색", "Scanner Results"],
  ["/world", "6. 세계 지수", "World Indices"],
  ["/macro", "7. 매크로", "Macro"],
  ["/board", "8. 차트 보드", "Chart Board"],
];

export const localTime = (iso?: string | null) => (iso ? new Date(iso).toLocaleString("ko-KR", { hour12: false }) : "—");

export function StatusBar() {
  const { data: st, error, reload } = useApi<Status>("/api/status", 20000);
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
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-zinc-800 bg-zinc-950 px-4 py-2 text-xs">
      <span>
        최신 완료 거래일 (Expected session): <b className="text-zinc-100">{st.expected_session}</b>
      </span>
      {["public_repo", "yahoo", "kospi", "kosdaq", "massive", "indices"]
        .filter((s) => st.sources[s]?.enabled)
        .map((s) => (
          <span key={s} className={st.sources[s].latest_date === (st.sources[s].expected ?? st.expected_session) ? "text-emerald-400" : "text-amber-400"}>
            {st.source_info[s]?.short ?? (s === "indices" ? "세계 지수" : s)}: {st.sources[s].latest_date ?? "없음"}
            {st.sources[s].running ? " ⟳" : ""}
          </span>
        ))}
      <span className="text-zinc-400">마지막 성공 (Last success): {localTime(lastOk)}</span>
      {errs.length > 0 && (
        <Link href="/data" className="text-red-400 underline">
          오류 {errs.length}건 (errors)
        </Link>
      )}
      {msg && <span className="text-sky-400">{msg}</span>}
      {process.env.NEXT_PUBLIC_AUTH === "1" ? (
        <span className="ml-auto text-[11px] text-zinc-500">매일 자동 갱신</span>
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
  if (path === "/login") return <>{children}</>;
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <nav className="shrink-0 border-zinc-800 bg-zinc-950 md:w-56 md:border-r">
        <div className="px-4 py-3">
          <div className="font-mono text-sm font-bold text-emerald-400">MARKET BREADTH</div>
          <div className="text-[10px] text-zinc-500">시장 폭 (Market Breadth) 연구용 · 투자 권유 아님</div>
        </div>
        <ul className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col">
          {MENU.map(([href, ko, en]) => (
            <li key={href}>
              <Link
                href={href}
                className={`block whitespace-nowrap rounded px-3 py-2 text-sm ${path === href ? "bg-zinc-800 text-white" : "text-zinc-400 hover:bg-zinc-900"}`}
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
