"use client";
import { useApi } from "@/lib/api";

export type Row = { id: number; board: string; title: string; nick: string; ip_prefix: string; member: boolean; created_at: string; user_id?: number | null;
  views: number; likes: number; comments: number; mine?: boolean; ip?: string };
export type Post = Row & { body: string; updated_at: string | null; tickers: string };
export type Comment = { id: number; parent_id: number | null; body?: string; nick?: string; ip_prefix?: string; member?: boolean;
  created_at?: string; deleted?: number; mine?: boolean; ip?: string };
export type Me = { user: { username: string; nickname: string } | null; admin: boolean; boards: Record<string, string>; admin_only: string[] };

/** JSON call that surfaces the API's Korean error message (FastAPI `detail`). */
export async function call<T = unknown>(url: string, method = "POST", body?: unknown): Promise<T> {
  const r = await fetch(url, { method, headers: body ? { "Content-Type": "application/json" } : undefined, body: body ? JSON.stringify(body) : undefined });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = (j as { detail?: unknown }).detail;
    throw new Error(typeof d === "string" ? d : Array.isArray(d) ? "입력값을 확인하세요 (길이·형식)" : `${r.status} 오류`);
  }
  return j as T;
}

export const useMe = () => useApi<Me>("/api/board/me");

/** "방금" / "12분 전" / today "14:05" / "10.21". Stored times are UTC ISO. */
export function when(iso: string | undefined) {
  if (!iso) return "";
  const d = new Date(iso), m = Math.floor((Date.now() - d.getTime()) / 60000);
  if (m < 1) return "방금";
  if (m < 60) return `${m}분 전`;
  const today = new Date().toDateString() === d.toDateString();
  return today ? d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false })
    : d.toLocaleDateString("ko-KR", { month: "2-digit", day: "2-digit" }).replace(/\s/g, "").replace(/\.$/, "");
}

/** Author label: members get a mark, guests show the IP prefix (DC style). */
export const author = (r: { nick?: string; member?: boolean; ip_prefix?: string }) => (r.member ? `${r.nick} ✔` : `${r.nick}(${r.ip_prefix})`);
