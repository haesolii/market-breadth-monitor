"use client";
import { useState } from "react";
import { call } from "@/lib/board";

const input = "rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 placeholder:text-zinc-500";

/** Ban form; prefilled from a report (IP or member of the reported content). */
export function BanForm({ target: initial = "", onDone }: { target?: string; onDone?: () => void }) {
  const [target, setTarget] = useState(initial), [days, setDays] = useState(7), [reason, setReason] = useState("운영 정책 위반");
  const [msg, setMsg] = useState<string | null>(null);
  const go = async () => {
    try { const r = await call<{ until: string }>("/api/board/admin/ban", "POST", { target, days, reason }); setMsg(`${r.until.slice(0, 10)}까지 차단`); onDone?.(); }
    catch (e) { setMsg((e as Error).message); }
  };
  return (
    <div className="flex flex-wrap items-center gap-2">
      <input className={`${input} w-48`} placeholder="ip:1.2.3.4 또는 user:12" value={target} onChange={(e) => setTarget(e.target.value)} />
      <select className={input} value={days} onChange={(e) => setDays(Number(e.target.value))}>
        {[1, 7, 30, 365, 3650].map((d) => <option key={d} value={d}>{d === 3650 ? "영구" : `${d}일`}</option>)}
      </select>
      <input className={`${input} w-40`} value={reason} onChange={(e) => setReason(e.target.value)} />
      <button disabled={!/^(ip|user):.+/.test(target)} onClick={go} className="rounded bg-red-800 px-3 py-1 text-xs text-white disabled:opacity-40">차단</button>
      {msg && <span className="text-xs text-zinc-400">{msg}</span>}
    </div>
  );
}

