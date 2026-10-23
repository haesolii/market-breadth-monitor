"use client";
import { useState } from "react";
import { send, useApi } from "@/lib/api";

export type WatchItem = { ticker: string; market: string; name?: string };
type WatchRes = { items: WatchItem[] };

/** ☆ / ★ toggle that adds or removes one stock from the shared watchlist. */
export function WatchStar({ ticker, market }: { ticker: string; market: string }) {
  const { data, reload } = useApi<WatchRes>("/api/watchlist");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const items = data?.items ?? [];
  const on = items.some((x) => x.ticker === ticker && x.market === market);
  const toggle = async () => {
    setBusy(true);
    setErr(null);
    try {
      const next = on ? items.filter((x) => !(x.ticker === ticker && x.market === market)) : [...items, { ticker, market }];
      await send("/api/watchlist", "POST", next.map(({ ticker, market }) => ({ ticker, market })));
      reload();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <button onClick={toggle} disabled={busy || !data} title={err ?? (on ? "관심종목에서 빼기" : "관심종목에 추가")}
      className={`rounded border px-2 py-0.5 text-xs ${on ? "border-amber-600 text-amber-300" : "border-zinc-700 text-zinc-400 hover:text-zinc-200"}`}>
      {on ? "★ 관심종목" : "☆ 관심종목 추가"}{err ? " ⚠" : ""}
    </button>
  );
}
