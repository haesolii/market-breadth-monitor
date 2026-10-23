"use client";
import Link from "next/link";
import { call, useMe } from "@/lib/board";

/** Board account in the menu: "로그인 · 가입" for visitors, "닉네임 · 로그아웃" for members. */
export function AccountLink({ className = "" }: { className?: string }) {
  const { data } = useMe();
  if (!data) return null;
  if (!data.user) return <Link href="/community/account" className={`text-sky-400 hover:underline ${className}`}>로그인 · 가입</Link>;
  return (
    <span className={`flex items-center gap-2 ${className}`}>
      <Link href="/community/account" className="truncate text-zinc-300 hover:underline">{data.user.nickname} ✔{data.admin ? " (운영자)" : ""}</Link>
      <button onClick={async () => { await call("/api/board/logout"); window.location.reload(); }} className="shrink-0 text-zinc-500 hover:text-zinc-200">로그아웃</button>
    </span>
  );
}
