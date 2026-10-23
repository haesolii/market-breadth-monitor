"use client";
import Link from "next/link";
import { useState } from "react";
import { Err, Panel } from "@/components/bits";
import { useApi } from "@/lib/api";
import { call, useMe, when } from "@/lib/board";
import { BanForm } from "@/components/BanForm";

type Report = { id: number; kind: "post" | "comment"; target_id: number; reason: string; created_at: string; post_id: number | null;
  text: string; nick: string; ip: string; user_id: number | null; deleted: number };

export default function Admin() {
  const me = useMe();
  const { data, error, reload } = useApi<Report[]>(me.data?.admin ? "/api/board/admin/reports" : null);
  const [ban, setBan] = useState<string | null>(null);
  if (me.data && !me.data.admin) return <div className="mx-auto max-w-3xl"><Panel title="게시판 관리"><div className="text-sm text-zinc-400">관리자만 볼 수 있습니다.</div></Panel></div>;
  const done = async (id: number) => { await call(`/api/board/admin/reports/${id}/done`); reload(); };
  const del = async (r: Report) => {
    await call(r.kind === "post" ? `/api/board/posts/${r.target_id}/delete` : `/api/board/comments/${r.target_id}/delete`, "POST", { password: "" });
    await done(r.id);
  };
  return (
    <div className="mx-auto max-w-4xl space-y-3">
      <Panel title={`신고 목록 ${data?.length ?? ""}`} right={<Link href="/community" className="text-xs text-zinc-400 hover:text-zinc-200">게시판으로</Link>}>
        <Err error={error} />
        {data && !data.length && <div className="py-6 text-center text-xs text-zinc-500">처리할 신고가 없습니다.</div>}
        <div className="divide-y divide-zinc-900">
          {data?.map((r) => (
            <div key={r.id} className="space-y-1 py-2 text-xs">
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded bg-amber-900/60 px-1.5 text-amber-200">{r.kind === "post" ? "글" : "댓글"}</span>
                <span className="text-zinc-300">사유: {r.reason}</span>
                <span className="text-zinc-600">{when(r.created_at)}</span>
                {r.deleted ? <span className="text-zinc-500">(이미 삭제됨)</span> : null}
                <span className="ml-auto flex gap-2">
                  {r.post_id && <Link href={`/community/post?id=${r.post_id}`} className="text-sky-400 hover:underline">보기</Link>}
                  {!r.deleted && <button onClick={() => del(r)} className="text-red-400 hover:underline">삭제</button>}
                  <button onClick={() => setBan(ban === `r${r.id}` ? null : `r${r.id}`)} className="text-red-300 hover:underline">차단</button>
                  <button onClick={() => done(r.id)} className="text-zinc-400 hover:underline">처리 완료</button>
                </span>
              </div>
              <div className="rounded bg-zinc-900/60 p-2 text-zinc-300">{r.text}</div>
              <div className="font-mono text-[11px] text-zinc-500">{r.nick} · {r.user_id ? `user:${r.user_id}` : "유동"} · {r.ip}</div>
              {ban === `r${r.id}` && <BanForm target={r.user_id ? `user:${r.user_id}` : `ip:${r.ip}`} />}
            </div>
          ))}
        </div>
      </Panel>
      <Panel title="직접 차단">
        <BanForm />
        <div className="pt-2 text-[11px] text-zinc-500">글·댓글 화면에서 관리자에게만 보이는 IP를 복사해 <code>ip:주소</code>로, 회원은 <code>user:번호</code>로 입력합니다. 차단된 IP·회원은 기간 동안 글·댓글·가입을 할 수 없습니다.</div>
      </Panel>
    </div>
  );
}
