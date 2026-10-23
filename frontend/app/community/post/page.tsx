"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Fragment, Suspense, useState } from "react";
import { Err, Panel } from "@/components/bits";
import { useApi } from "@/lib/api";
import { BanForm } from "@/components/BanForm";
import { author, call, useMe, when, type Comment, type Post } from "@/lib/board";

type Res = { post: Post; comments: Comment[]; liked: boolean; admin: boolean };

/** Plain text with line breaks; $NVDA / $005930 become links to the stock page. */
function Body({ text }: { text: string }) {
  return (
    <div className="whitespace-pre-wrap break-words text-[15px] leading-relaxed text-zinc-200">
      {text.split(/(\$[A-Za-z]{1,6}(?:\.[A-Z])?\b|\$\d{6}\b)/g).map((part, i) =>
        i % 2 ? <Link key={i} href={`/stock?t=${encodeURIComponent(part.slice(1).toUpperCase())}`} className="text-sky-400 hover:underline">{part}</Link> : <Fragment key={i}>{part}</Fragment>)}
    </div>
  );
}

const input = "rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-100 placeholder:text-zinc-500";

/** Guest fields (nickname + password) shown only when not signed in. */
function GuestFields({ nick, setNick, pw, setPw }: { nick: string; setNick: (v: string) => void; pw: string; setPw: (v: string) => void }) {
  return (
    <div className="flex gap-2">
      <input className={`${input} w-28`} placeholder="닉네임" value={nick} onChange={(e) => setNick(e.target.value)} maxLength={12} />
      <input className={`${input} w-28`} placeholder="비밀번호" type="password" value={pw} onChange={(e) => setPw(e.target.value)} />
    </div>
  );
}

function CommentForm({ pid, parent, onDone, member }: { pid: number; parent?: number; onDone: () => void; member: boolean }) {
  const [body, setBody] = useState(""), [nick, setNick] = useState(""), [pw, setPw] = useState(""), [hp, setHp] = useState("");
  const [err, setErr] = useState<string | null>(null), [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      await call(`/api/board/posts/${pid}/comments`, "POST", { body, parent_id: parent ?? null, nick, password: pw, website: hp });
      setBody(""); onDone();
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-2 rounded border border-zinc-800 bg-zinc-900/40 p-2">
      {!member && <GuestFields nick={nick} setNick={setNick} pw={pw} setPw={setPw} />}
      <input className="hidden" tabIndex={-1} autoComplete="off" value={hp} onChange={(e) => setHp(e.target.value)} aria-hidden />
      <textarea className={`${input} h-20 w-full resize-y`} placeholder={parent ? "답글" : "댓글을 입력하세요"} value={body} onChange={(e) => setBody(e.target.value)} maxLength={2000} />
      <div className="flex items-center gap-2">
        {err && <span className="text-xs text-red-400">{err}</span>}
        <button disabled={busy || !body.trim()} onClick={submit} className="ml-auto rounded bg-sky-700 px-3 py-1 text-xs text-white disabled:opacity-40">등록</button>
      </div>
    </div>
  );
}

/** Delete (members: own / admin; guests: password) with an inline password box instead of a browser dialog. */
function DeleteButton({ url, guest, onDone, label = "삭제" }: { url: string; guest: boolean; onDone: () => void; label?: string }) {
  const [open, setOpen] = useState(false), [pw, setPw] = useState(""), [err, setErr] = useState<string | null>(null);
  const go = async () => { try { await call(url, "POST", { password: pw }); onDone(); } catch (e) { setErr((e as Error).message); } };
  if (!open) return <button onClick={() => (guest ? setOpen(true) : go())} className="text-xs text-zinc-500 hover:text-red-400">{label}</button>;
  return (
    <span className="flex items-center gap-1">
      <input autoFocus className={`${input} w-24 py-0.5 text-xs`} type="password" placeholder="비밀번호" value={pw} onChange={(e) => setPw(e.target.value)} onKeyDown={(e) => e.key === "Enter" && go()} />
      <button onClick={go} className="text-xs text-red-400">확인</button>
      <button onClick={() => setOpen(false)} className="text-xs text-zinc-500">취소</button>
      {err && <span className="text-xs text-red-400">{err}</span>}
    </span>
  );
}

function ReportButton({ kind, id }: { kind: "post" | "comment"; id: number }) {
  const [open, setOpen] = useState(false), [reason, setReason] = useState(""), [done, setDone] = useState(false);
  if (done) return <span className="text-xs text-zinc-500">신고됨</span>;
  if (!open) return <button onClick={() => setOpen(true)} className="text-xs text-zinc-500 hover:text-amber-400">신고</button>;
  return (
    <span className="flex items-center gap-1">
      <input autoFocus className={`${input} w-40 py-0.5 text-xs`} placeholder="신고 사유" value={reason} onChange={(e) => setReason(e.target.value)} />
      <button disabled={!reason.trim()} onClick={async () => { await call("/api/board/report", "POST", { kind, target_id: id, reason }); setDone(true); }} className="text-xs text-amber-400 disabled:opacity-40">보내기</button>
    </span>
  );
}

function View() {
  const id = Number(useSearchParams().get("id")), router = useRouter();
  const { data, error, reload } = useApi<Res>(id ? `/api/board/posts/${id}` : null);
  const me = useMe();
  const [reply, setReply] = useState<number | null>(null), [likeErr, setLikeErr] = useState<string | null>(null), [likes, setLikes] = useState<number | null>(null);
  if (error) return <div className="mx-auto max-w-4xl"><Err error={error} /><Link href="/community" className="text-sm text-sky-400">목록으로</Link></div>;
  if (!data) return <div className="text-xs text-zinc-500">불러오는 중…</div>;
  const p = data.post, member = !!me.data?.user, boards = me.data?.boards ?? {};
  const roots = data.comments.filter((c) => !c.parent_id), kids = (cid: number) => data.comments.filter((c) => c.parent_id === cid);
  const like = async () => { try { setLikes((await call<{ likes: number }>(`/api/board/posts/${id}/like`)).likes); } catch (e) { setLikeErr((e as Error).message); } };

  const CommentRow = ({ c, child = false }: { c: Comment; child?: boolean }) => (
    <div className={`border-t border-zinc-900 py-2 ${child ? "ml-6 border-l border-l-zinc-800 pl-3" : ""}`}>
      {c.deleted ? <div className="text-xs text-zinc-600">삭제된 댓글입니다.</div> : <>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className={c.member ? "font-medium text-sky-300" : "text-zinc-300"}>{author(c)}</span>
          <span className="text-zinc-600">{when(c.created_at)}</span>
          {data.admin && c.ip && <span className="font-mono text-[10px] text-zinc-600">{c.ip}</span>}
          <span className="ml-auto flex items-center gap-2">
            {!child && <button onClick={() => setReply(reply === c.id ? null : c.id)} className="text-xs text-zinc-500 hover:text-zinc-200">답글</button>}
            <ReportButton kind="comment" id={c.id} />
            {(c.mine || data.admin || !c.member) && <DeleteButton url={`/api/board/comments/${c.id}/delete`} guest={!c.member && !data.admin} onDone={reload} />}
          </span>
        </div>
        <div className="whitespace-pre-wrap break-words pt-0.5 text-sm text-zinc-200">{c.body}</div>
      </>}
      {!child && reply === c.id && <div className="pt-2"><CommentForm pid={id} parent={c.id} member={member} onDone={() => { setReply(null); reload(); }} /></div>}
    </div>
  );

  return (
    <div className="mx-auto max-w-4xl space-y-3">
      <Panel>
        <div className="text-xs text-sky-400"><Link href={`/community?b=${p.board}`} className="hover:underline">{boards[p.board] ?? p.board}</Link></div>
        <h1 className="pt-1 text-xl font-semibold leading-snug text-zinc-50">{p.title}</h1>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-zinc-800 pb-2 pt-2 text-xs text-zinc-500">
          <span className={p.member ? "font-medium text-sky-300" : "text-zinc-300"}>{author(p)}</span>
          <span>{new Date(p.created_at).toLocaleString("ko-KR", { hour12: false })}{p.updated_at && " (수정됨)"}</span>
          <span>조회 {p.views}</span><span>추천 {likes ?? p.likes}</span><span>댓글 {p.comments}</span>
          {data.admin && p.ip && <span className="font-mono text-zinc-600">{p.ip}</span>}
        </div>
        {data.admin && <div className="pt-2"><BanForm target={p.member ? `user:${p.user_id}` : `ip:${p.ip}`} /></div>}
        <div className="min-h-32 py-4"><Body text={p.body} /></div>
        <div className="flex flex-col items-center gap-1 py-3">
          <button onClick={like} disabled={data.liked || likes !== null} className="rounded-full border border-amber-700 px-5 py-2 text-sm text-amber-300 hover:bg-amber-950 disabled:opacity-50">
            👍 추천 {likes ?? p.likes}
          </button>
          {likeErr && <span className="text-xs text-zinc-500">{likeErr}</span>}
        </div>
        <div className="flex flex-wrap items-center gap-3 border-t border-zinc-800 pt-2">
          <Link href={`/community?b=${p.board}`} className="text-xs text-zinc-400 hover:text-zinc-200">목록</Link>
          <span className="ml-auto flex items-center gap-3">
            <ReportButton kind="post" id={p.id} />
            {(p.mine || data.admin || !p.member) && <Link href={`/community/write?id=${p.id}`} className="text-xs text-zinc-500 hover:text-zinc-200">수정</Link>}
            {(p.mine || data.admin || !p.member) && <DeleteButton url={`/api/board/posts/${p.id}/delete`} guest={!p.member && !data.admin} onDone={() => router.push(`/community?b=${p.board}`)} />}
          </span>
        </div>
      </Panel>

      <Panel title={`댓글 ${p.comments}`}>
        {roots.map((c) => <Fragment key={c.id}><CommentRow c={c} />{kids(c.id).map((k) => <CommentRow key={k.id} c={k} child />)}</Fragment>)}
        {!roots.length && <div className="pb-2 text-xs text-zinc-500">첫 댓글을 남겨 보세요.</div>}
        <div className="pt-3"><CommentForm pid={id} member={member} onDone={reload} /></div>
      </Panel>
    </div>
  );
}

export default function Page() {
  return <Suspense><View /></Suspense>;
}
