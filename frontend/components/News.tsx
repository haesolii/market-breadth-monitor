"use client";
import Link from "next/link";
import { useApi } from "@/lib/api";
import { stockHref } from "@/lib/stock";

export type Item = { time: string; source: string; title: string; summary: string; url: string; ticker?: string; market?: string; name?: string };

/** Headline list: time · source · title (opens the publisher), optional summary and stock tag. */
export function NewsList({ items, summary = true, max = 40 }: { items: Item[]; summary?: boolean; max?: number }) {
  if (!items.length) return <div className="text-xs text-zinc-500">뉴스가 없습니다 (뉴스 소스 응답 없음).</div>;
  return (
    <div className="space-y-2">
      {items.slice(0, max).map((n, i) => (
        <div key={n.url + i} className="border-t border-zinc-900 pt-1.5 text-xs">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className="font-mono text-zinc-500">{n.time.slice(5)}</span>
            <span className="text-zinc-500">{n.source}</span>
            {n.ticker && <Link className="rounded bg-zinc-800 px-1.5 text-[10px] text-sky-300 hover:underline" href={stockHref(n.ticker, n.market)}>{n.name ?? n.ticker}</Link>}
          </div>
          <a href={n.url} target="_blank" rel="noreferrer" className="text-sm text-zinc-100 hover:text-sky-300 hover:underline">{n.title}</a>
          {summary && n.summary && <div className="line-clamp-2 text-zinc-400">{n.summary}</div>}
        </div>
      ))}
    </div>
  );
}

/** News of one stock (Naver for Korea, Google News for the rest). */
export function StockNews({ ticker, market }: { ticker: string; market: string }) {
  const { data } = useApi<Item[]>(`/api/news/stock?ticker=${encodeURIComponent(ticker)}&market=${market}`);
  return data ? <NewsList items={data} max={15} /> : <div className="text-xs text-zinc-500">불러오는 중…</div>;
}
