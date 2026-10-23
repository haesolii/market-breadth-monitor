"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Pager } from "@/components/bits";
import { useApi } from "@/lib/api";
import { stockHref } from "@/lib/stock";

export type Item = { time: string; source: string; title: string; summary: string; url: string; thumb?: string; ticker?: string; market?: string; name?: string };

/** "12분 전" for today's news, else "10-21 14:05" (times are KST "YYYY-MM-DD HH:MM"). */
export function ago(t: string) {
  const ms = Date.now() - new Date(t.replace(" ", "T") + ":00+09:00").getTime();
  if (Number.isNaN(ms)) return t;
  const m = Math.floor(ms / 60000);
  return m < 1 ? "방금" : m < 60 ? `${m}분 전` : m < 24 * 60 ? `${Math.floor(m / 60)}시간 전` : t.slice(5);
}

function Meta({ n }: { n: Item }) {
  const router = useRouter();
  return (
    <div className="flex flex-wrap items-center gap-x-2 text-[11px] text-zinc-500">
      <span className="font-medium text-zinc-400">{n.source}</span>
      <span title={n.time}>{ago(n.time)}</span>
      {/* inside the card's <a>: a nested link is invalid HTML, so the stock tag navigates by script */}
      {n.ticker && <span role="link" tabIndex={0} className="cursor-pointer rounded bg-zinc-800 px-1.5 text-sky-300 hover:underline"
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); router.push(stockHref(n.ticker!, n.market)); }}>{n.name ?? n.ticker}</span>}
    </div>
  );
}

/** First story large (image + summary), the rest as compact rows with a thumbnail. */
function Featured({ n }: { n: Item }) {
  return (
    <a href={n.url} target="_blank" rel="noreferrer" className="group flex flex-col gap-3 rounded-lg border border-zinc-800 bg-zinc-900/40 p-3 hover:border-zinc-600 sm:flex-row">
      {/* eslint-disable-next-line @next/next/no-img-element -- publisher thumbnails, already resized */}
      {n.thumb && <img src={n.thumb} alt="" loading="lazy" className="h-36 w-full shrink-0 rounded object-cover sm:h-28 sm:w-44" />}
      <div className="min-w-0 space-y-1">
        <Meta n={n} />
        <div className="text-base font-semibold leading-snug text-zinc-50 group-hover:text-sky-300">{n.title}</div>
        {n.summary && <div className="line-clamp-3 text-xs leading-relaxed text-zinc-400">{n.summary}</div>}
      </div>
    </a>
  );
}

function Row({ n }: { n: Item }) {
  return (
    <a href={n.url} target="_blank" rel="noreferrer" className="group flex gap-3 rounded px-1 py-2.5 hover:bg-zinc-900/60">
      <div className="min-w-0 flex-1 space-y-0.5">
        <Meta n={n} />
        <div className="line-clamp-2 text-sm leading-snug text-zinc-100 group-hover:text-sky-300">{n.title}</div>
        {n.summary && <div className="line-clamp-1 text-xs text-zinc-500">{n.summary}</div>}
      </div>
      {/* eslint-disable-next-line @next/next/no-img-element -- publisher thumbnails, already resized */}
      {n.thumb && <img src={n.thumb} alt="" loading="lazy" className="h-14 w-20 shrink-0 rounded object-cover" />}
    </a>
  );
}

/** Paged headline list: a featured first story on page 1, `size` stories per page. */
export function NewsList({ items, size = 10, featured = true }: { items: Item[]; size?: number; featured?: boolean }) {
  const [page, setPage] = useState(0);
  useEffect(() => setPage(0), [items]);
  if (!items.length) return <div className="py-8 text-center text-xs text-zinc-500">뉴스가 없습니다.</div>;
  const pages = Math.ceil(items.length / size), shown = items.slice(page * size, page * size + size);
  const [top, ...rest] = featured && page === 0 ? shown : [null, ...shown];
  return (
    <div>
      {top && <Featured n={top} />}
      <div className="divide-y divide-zinc-900">{rest.map((n, i) => n && <Row key={n.url + i} n={n} />)}</div>
      <Pager page={page} pages={pages} onChange={setPage} />
    </div>
  );
}

/** News of one stock (Naver for Korea, Google News for the rest). */
export function StockNews({ ticker, market }: { ticker: string; market: string }) {
  const { data } = useApi<Item[]>(`/api/news/stock?ticker=${encodeURIComponent(ticker)}&market=${market}`);
  return data ? <NewsList items={data} size={8} /> : <div className="text-xs text-zinc-500">불러오는 중…</div>;
}
