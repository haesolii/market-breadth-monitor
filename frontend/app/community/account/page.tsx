"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Panel, TabBar } from "@/components/bits";
import { call, useMe } from "@/lib/board";

const input = "w-full rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500";

export default function Account() {
  const me = useMe(), router = useRouter();
  const [tab, setTab] = useState<"login" | "signup">("login");
  const [username, setUsername] = useState(""), [nickname, setNickname] = useState(""), [password, setPassword] = useState(""), [hp, setHp] = useState("");
  const [err, setErr] = useState<string | null>(null), [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      await call(tab === "login" ? "/api/board/login" : "/api/board/signup", "POST", tab === "login" ? { username, password } : { username, nickname, password, website: hp });
      router.push("/community");
    } catch (e) { setErr((e as Error).message); setBusy(false); }
  };

  if (me.data?.user) return (
    <div className="mx-auto max-w-md">
      <Panel title="내 계정">
        <div className="space-y-2 text-sm text-zinc-300">
          <div>아이디 <b className="text-zinc-100">{me.data.user.username}</b></div>
          <div>고정닉 <b className="text-sky-300">{me.data.user.nickname} ✔</b>{me.data.admin && <span className="ml-2 text-xs text-amber-300">관리자</span>}</div>
          <div className="flex gap-3 pt-2">
            <Link href="/community" className="text-sky-400 hover:underline">게시판으로</Link>
            <button onClick={async () => { await call("/api/board/logout"); me.reload(); }} className="text-zinc-400 hover:text-zinc-200">로그아웃</button>
          </div>
        </div>
      </Panel>
    </div>
  );

  return (
    <div className="mx-auto max-w-md">
      <Panel title="게시판 회원">
        <TabBar value={tab} onChange={(v) => { setTab(v); setErr(null); }} tabs={[["login", "로그인"], ["signup", "가입 (고정닉)"]]} />
        <form className="space-y-2 pt-3" onSubmit={(e) => { e.preventDefault(); submit(); }}>
          <input className={input} placeholder="아이디 (영문·숫자 4~20자)" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
          {tab === "signup" && <input className={input} placeholder="고정닉 (2~12자)" value={nickname} onChange={(e) => setNickname(e.target.value)} maxLength={12} />}
          <input className={input} type="password" placeholder={tab === "signup" ? "비밀번호 (8자 이상)" : "비밀번호"} value={password} onChange={(e) => setPassword(e.target.value)}
            autoComplete={tab === "signup" ? "new-password" : "current-password"} />
          <input className="hidden" tabIndex={-1} autoComplete="off" value={hp} onChange={(e) => setHp(e.target.value)} aria-hidden />
          {err && <div className="text-xs text-red-400">{err}</div>}
          <button disabled={busy} className="w-full rounded bg-sky-700 py-2 text-sm text-white hover:bg-sky-600 disabled:opacity-40">{tab === "login" ? "로그인" : "가입하고 로그인"}</button>
        </form>
        <div className="pt-3 text-[11px] leading-relaxed text-zinc-500">
          가입 없이도 닉네임·비밀번호로 글을 쓸 수 있습니다 (유동, IP 앞자리 표시). 회원은 고정닉으로 표시되고 링크를 쓸 수 있습니다.
          비밀번호는 복원 불가능한 방식(scrypt)으로만 저장됩니다. 이메일 등 다른 개인정보는 받지 않습니다.
        </div>
      </Panel>
    </div>
  );
}
