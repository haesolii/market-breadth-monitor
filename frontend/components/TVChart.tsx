"use client";
import { useEffect, useRef } from "react";

// TradingView free "Advanced Chart" embed widget (no API key; data and display are TradingView's).
// https://www.tradingview.com/widget-docs/widgets/charts/advanced-chart/
// Tested 2026-10-17: the free widget does NOT serve official US index feeds (SP:SPX, NASDAQ:IXIC, DJ:DJI),
// TVC:*, KRX (Korean stocks and indices), NSE, ASX or TWSE ("only available on TradingView").
// US stocks/ETFs, SSE, XETR, EURONEXT, TSX, BMFBOVESPA and CAPITALCOM/FOREXCOM CFDs do work.

const EXCHANGE: Record<string, string> = { NASDAQ: "NASDAQ", NYSE: "NYSE", "NYSE American": "AMEX", "NYSE Arca": "AMEX", "Cboe BZX": "CBOE" };

/** Index symbols the free widget shows as the index itself. Every other index (incl. KOSPI/KOSDAQ,
 * S&P 500, Nikkei, yields, oil) is drawn by IndexChart from our own index data — never an ETF/CFD stand-in. */
export const TV_INDEX: Record<string, string> = {
  "000001.SS": "SSE:000001", "^GDAXI": "XETR:DAX", "^FCHI": "EURONEXT:PX1", "^GSPTSE": "TSX:TSX", "^BVSP": "BMFBOVESPA:IBOV",
};

/** Widget symbol for a stock, or null when the widget cannot show it (Korean stocks). */
export const tvStock = (ticker: string, exchange?: string | null) =>
  exchange === "KOSPI" || exchange === "KOSDAQ" ? null : `${EXCHANGE[exchange ?? ""] ?? "NASDAQ"}:${ticker}`;

/** Link to the full TradingView site (works for every symbol incl. KRX). */
export const tvLink = (sym: string) => `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(sym)}`;

/** compact = small grid cell: no toolbars, no indicators. */
export function TVChart({ symbol, height = 520, compact = false }: { symbol: string; height?: number; compact?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.innerHTML = '<div class="tradingview-widget-container__widget" style="height:100%;width:100%"></div>';
    const s = document.createElement("script");
    s.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    s.type = "text/javascript";
    s.async = true;
    s.innerHTML = JSON.stringify({
      symbol, interval: "D", theme: "dark", style: "1", locale: "kr", timezone: "Asia/Seoul",
      autosize: true, allow_symbol_change: !compact, withdateranges: !compact,
      // Drawing toolbar and image-save button off: rarely used, they only take chart space. Branding stays.
      hide_side_toolbar: true, save_image: false,
      ...(compact ? { hide_top_toolbar: true } : {}),
      backgroundColor: "rgba(9, 9, 11, 1)",
      // Same moving averages as the dashboard tables (50 / 200 days).
      studies: compact ? [] : [
        { id: "MASimple@tv-basicstudies", inputs: { length: 50 } },
        { id: "MASimple@tv-basicstudies", inputs: { length: 200 } },
      ],
    });
    el.appendChild(s);
    return () => { el.innerHTML = ""; };
  }, [symbol, compact]);
  // The embed script rewrites its container's style (height: 100%), so the fixed height lives on an
  // outer box it never touches; otherwise cards collapse and overlap the next row.
  return (
    <>
    <div className="relative overflow-hidden" style={{ height }}>
      <div ref={ref} className="tradingview-widget-container" style={{ height: "100%", width: "100%" }} />
    </div>
    {/* Attribution from TradingView's embed code, kept verbatim: their widget FAQ says removing or changing it
        (text and link) needs their agreement. Kept outside the box the embed script rewrites. */}
    <div className="text-right text-[10px] text-zinc-500">
      <a href="https://www.tradingview.com/" rel="noopener nofollow" target="_blank" className="hover:text-sky-400">Track all markets on TradingView</a>
    </div>
    </>
  );
}

/** KRX symbols cannot be embedded: explain and link out instead. */
export function TVUnavailable({ sym }: { sym: string }) {
  return (
    <div className="px-3 py-6 text-sm text-zinc-400">
      트레이딩뷰 무료 위젯은 한국거래소(KRX) 시세를 제공하지 않아 여기에 차트를 띄울 수 없습니다.{" "}
      <a className="text-sky-400 underline" href={tvLink(sym)} target="_blank" rel="noreferrer">트레이딩뷰에서 {sym} 열기 ↗</a>
    </div>
  );
}
