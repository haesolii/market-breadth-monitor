"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useApi } from "@/lib/api";
import { MK, stockHref } from "@/lib/stock";

export type Hit = { ticker: string; name: string; market: string; exchange: string; sector: string; size: number };

/** Name / ticker search over the sector map. Default: open the stock page; onPick: hand the stock back. */
export function StockSearch({ onPick, placeholder = "종목명 또는 티커 (예: 삼성전자, 005930, NVDA)" }: { onPick?: (h: Hit) => void; placeholder?: string }) {
  const [q, setQ] = useState("");
  const [deb, setDeb] = useState("");
  useEffect(() => { const t = setTimeout(() => setDeb(q.trim()), 250); return () => clearTimeout(t); }, [q]);
  const { data } = useApi<Hit[]>(deb ? `/api/stock/search?q=${encodeURIComponent(deb)}` : null);
  const router = useRouter();
  const pick = (h: Hit) => { setQ(""); if (onPick) onPick(h); else router.push(stockHref(h.ticker, h.market)); };
  return (
    <div className="relative w-full min-w-0 max-w-md sm:w-80">
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder}
        onKeyDown={(e) => { if (e.key === "Enter" && data?.[0]) pick(data[0]); }}
        className="w-full rounded border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-100 placeholder:text-zinc-500" />
      {deb && q.trim() === deb && data && data.length > 0 && (
        <div className="absolute z-20 mt-1 max-h-80 w-full overflow-auto rounded border border-zinc-700 bg-zinc-950 text-sm shadow-lg">
          {data.map((h) => (
            <button key={h.market + h.ticker} onClick={() => pick(h)} className="flex w-full gap-2 px-3 py-1.5 text-left hover:bg-zinc-800">
              <span className="text-zinc-100">{h.name}</span><span className="font-mono text-zinc-500">{h.ticker}</span>
              <span className="ml-auto text-xs text-zinc-500">{MK[h.market] ?? h.market} · {h.sector}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
