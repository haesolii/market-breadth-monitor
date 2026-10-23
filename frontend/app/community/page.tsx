"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Err, Pager, Panel, TabBar } from "@/components/bits";
import { useApi } from "@/lib/api";
import { author, useMe, when, type Row } from "@/lib/board";

type List = { total: number; page: number; pages: number; rows: Row[]; notices: Row[] };

function Line({ r, boards, notice = false }: { r: Row; boards: Record<string, string>; notice?: boolean }) {
  return (
    <Link href={`/community/post?id=${r.id}`} className={`flex items-center gap-3 border-t border-zinc-900 px-2 py-2.5 hover:bg-zinc-900/60 ${notice ? "bg-sky-950/30" : ""}`}>
      <span className="hidden w-12 shrink-0 text-center font-mono text-xs text-zinc-500 sm:block">{notice ? "공지" : r.id}</span>
      <span className="hidden w-16 shrink-0 text-xs text-zinc-500 md:block">{boards[r.board] ?? r.board}</span>
      <span className="min-w-0 flex-1">
        <span className={`block truncate text-sm ${notice ? "font-semibold text-sky-200" : "text-zinc-100"}`}>
          {r.title}{r.comments > 0 && <span className="ml-1 text-xs text-sky-400">[{r.comments}]</span>}
        </span>
        <span className="text-[11px] text-zinc-500 sm:hidden">{author(r)} · {when(r.created_at)} · 조회 {r.views} · 추천 {r.likes}</span>
      </span>
      <span className="hidden w-32 shrink-0 truncate text-xs text-zinc-400 sm:block">{author(r)}</span>
      <span className="hidden w-14 shrink-0 text-right text-xs text-zinc-500 sm:block">{when(r.created_at)}</span>
      <span className="hidden w-10 shrink-0 text-right font-mono text-xs text-zinc-500 sm:block">{r.views}</span>
      <span className={`hidden w-10 shrink-0 text-right font-mono text-xs sm:block ${r.likes >= 5 ? "text-amber-300" : "text-zinc-500"}`}>{r.likes}</span>
    </Link>
  );
}

function BoardList() {
  const sp = useSearchParams(), router = useRouter();
  const board = sp.get("b") ?? "", page = Number(sp.get("p") ?? 1), q = sp.get("q") ?? "", best = sp.get("best") === "1";
  const [term, setTerm] = useState(q);
  const me = useMe();
  const go = (o: Record<string, string | number | undefined>) => {
    const p = new URLSearchParams({ ...(board && { b: board }), ...(q && { q }), ...(best && { best: "1" }), ...Object.fromEntries(Object.entries(o).map(([k, v]) => [k, String(v ?? "")])) });
    [...p.entries()].forEach(([k, v]) => !v && p.delete(k));
    router.push(`/community?${p}`);
  };
  const { data, error } = useApi<List>(`/api/board/posts?board=${board}&page=${page}&q=${encodeURIComponent(q)}${best ? "&best=true" : ""}`);
  const boards = me.data?.boards ?? {};
  const tab = best ? "best" : board || "all";

  return (
    <div className="mx-auto max-w-5xl space-y-3">
      <Panel title="게시판" right={<>
        <span className="text-xs text-zinc-400">{me.data?.user ? <>{me.data.user.nickname} ✔{me.data.admin && " (관리자)"}</> : "비회원 (유동)"}</span>
        {me.data?.admin && <Link href="/community/admin" className="text-xs text-amber-300 hover:underline">관리</Link>}
        <Link href="/community/account" className="text-xs text-sky-400 hover:underline">{me.data?.user ? "내 계정" : "로그인 · 가입"}</Link>
        <Link href={`/community/write${board && board !== "notice" ? `?b=${board}` : ""}`} className="rounded bg-sky-700 px-3 py-1 text-xs text-white hover:bg-sky-600">글쓰기</Link>
      </>}>
        <TabBar value={tab} onChange={(v) => router.push(v === "all" ? "/community" : v === "best" ? "/community?best=1" : `/community?b=${v}`)}
          tabs={[["all", "전체"], ...Object.entries(boards).map(([k, v]) => [k, v] as [string, string]), ["best", "개념글"]]} />
        <form className="flex gap-2 pt-3" onSubmit={(e) => { e.preventDefault(); go({ q: term.trim(), p: 1 }); }}>
          <input value={term} onChange={(e) => setTerm(e.target.value)} placeholder="제목·내용·글쓴이 검색"
            className="min-w-0 flex-1 rounded border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-100 placeholder:text-zinc-500" />
          <button className="rounded border border-zinc-700 px-3 text-xs text-zinc-300 hover:bg-zinc-800">검색</button>
          {q && <button type="button" onClick={() => { setTerm(""); go({ q: "", p: 1 }); }} className="text-xs text-zinc-500">초기화</button>}
        </form>
        <Err error={error} />
        <div className="mt-3">
          <div className="hidden items-center gap-3 px-2 pb-1 text-[11px] text-zinc-500 sm:flex">
            <span className="w-12 text-center">번호</span><span className="hidden w-16 md:block">게시판</span><span className="flex-1">제목</span>
            <span className="w-32">글쓴이</span><span className="w-14 text-right">작성일</span><span className="w-10 text-right">조회</span><span className="w-10 text-right">추천</span>
          </div>
          {data?.notices.map((r) => <Line key={`n${r.id}`} r={r} boards={boards} notice />)}
          {data?.rows.map((r) => <Line key={r.id} r={r} boards={boards} />)}
          {data && !data.rows.length && <div className="border-t border-zinc-900 py-10 text-center text-sm text-zinc-500">{q ? "검색 결과가 없습니다." : "첫 글을 써 보세요."}</div>}
        </div>
        {data && <Pager page={page - 1} pages={data.pages} onChange={(p) => go({ p: p + 1 })} />}
        <div className="pt-2 text-center text-[11px] text-zinc-600">
          비회원은 닉네임 옆에 IP 앞자리가 표시되고 링크·연락처를 쓸 수 없습니다. 추천 5개 이상은 개념글. 리딩방·광고·비방 글은 삭제되고 이용이 제한됩니다.
        </div>
      </Panel>
    </div>
  );
}

export default function Page() {
  return <Suspense><BoardList /></Suspense>;
}
