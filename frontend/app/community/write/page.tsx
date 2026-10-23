"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Panel } from "@/components/bits";
import { useApi } from "@/lib/api";
import { call, useMe, type Post } from "@/lib/board";

const input = "rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500";

function Write() {
  const sp = useSearchParams(), router = useRouter();
  const editId = Number(sp.get("id") ?? 0) || null;
  const me = useMe();
  const old = useApi<{ post: Post }>(editId ? `/api/board/posts/${editId}` : null);
  const [board, setBoard] = useState(sp.get("b") ?? "free");
  const [title, setTitle] = useState(""), [body, setBody] = useState(""), [nick, setNick] = useState(""), [pw, setPw] = useState(""), [hp, setHp] = useState("");
  const [err, setErr] = useState<string | null>(null), [busy, setBusy] = useState(false);
  useEffect(() => { const p = old.data?.post; if (p) { setBoard(p.board); setTitle(p.title); setBody(p.body); setNick(p.nick); } }, [old.data]);
  const member = !!me.data?.user, guestEdit = !!editId && old.data && !old.data.post.member;
  const boards = Object.entries(me.data?.boards ?? {}).filter(([k]) => me.data?.admin || !me.data?.admin_only.includes(k));

  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      const payload = { board, title, body, nick, password: pw, website: hp };
      const id = editId ? (await call(`/api/board/posts/${editId}`, "PUT", payload), editId) : (await call<{ id: number }>("/api/board/posts", "POST", payload)).id;
      router.push(`/community/post?id=${id}`);
    } catch (e) { setErr((e as Error).message); setBusy(false); }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <Panel title={editId ? "글 수정" : "글쓰기"} right={<Link href="/community" className="text-xs text-zinc-400 hover:text-zinc-200">목록</Link>}>
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2">
            <select value={board} onChange={(e) => setBoard(e.target.value)} disabled={!!editId} className={`${input} py-1.5`}>
              {boards.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            {!member && !editId && <>
              <input className={`${input} w-32 py-1.5`} placeholder="닉네임" value={nick} onChange={(e) => setNick(e.target.value)} maxLength={12} />
              <input className={`${input} w-32 py-1.5`} placeholder="비밀번호 (수정·삭제용)" type="password" value={pw} onChange={(e) => setPw(e.target.value)} />
            </>}
            {guestEdit && !me.data?.admin && <input className={`${input} w-40 py-1.5`} placeholder="작성 때 비밀번호" type="password" value={pw} onChange={(e) => setPw(e.target.value)} />}
            <span className="self-center text-xs text-zinc-500">{member ? `${me.data!.user!.nickname} ✔ (회원)` : editId ? "" : "비회원: 닉네임 옆에 IP 앞자리가 표시됩니다"}</span>
          </div>
          <input className={`${input} w-full`} placeholder="제목" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={100} />
          <input className="hidden" tabIndex={-1} autoComplete="off" value={hp} onChange={(e) => setHp(e.target.value)} aria-hidden />
          <textarea className={`${input} h-80 w-full resize-y leading-relaxed`} value={body} onChange={(e) => setBody(e.target.value)} maxLength={20000}
            placeholder={"내용을 입력하세요.\n\n$NVDA, $005930 처럼 쓰면 종목 페이지로 연결되고 종목 상세의 '토론' 탭에도 보입니다."} />
          <div className="flex items-center gap-3">
            <span className="text-[11px] text-zinc-500">{!member && "비회원 글의 링크·메신저 아이디는 자동으로 가려집니다. "}리딩방·광고·비방 글은 삭제됩니다.</span>
            {err && <span className="text-xs text-red-400">{err}</span>}
            <button disabled={busy || !title.trim() || !body.trim()} onClick={submit} className="ml-auto rounded bg-sky-700 px-4 py-1.5 text-sm text-white hover:bg-sky-600 disabled:opacity-40">
              {editId ? "수정" : "등록"}
            </button>
          </div>
        </div>
      </Panel>
    </div>
  );
}

export default function Page() {
  return <Suspense><Write /></Suspense>;
}
