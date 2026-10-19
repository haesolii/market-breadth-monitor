"use client";
import { useCallback, useEffect, useState } from "react";

export type Row = Record<string, number | string | boolean | null>;

// Components mounted together (status bar, source selectors, day detail) share one request per URL.
const recent = new Map<string, { t: number; p: Promise<unknown> }>();
const SHARE_MS = 3000;

export function getJSON<T = unknown>(url: string, fresh = false): Promise<T> {
  const hit = recent.get(url);
  if (!fresh && hit && Date.now() - hit.t < SHARE_MS) return hit.p as Promise<T>;
  const p = (async () => {
    const r = await fetch(url, { cache: "no-store" });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error((body as { detail?: string }).detail ?? `${r.status} ${r.statusText}`);
    return body as T;
  })();
  recent.set(url, { t: Date.now(), p });
  return p;
}

export async function send<T = unknown>(url: string, method: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const res = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(JSON.stringify((res as { detail?: unknown }).detail ?? r.statusText));
  return res as T;
}

/** Fetch `url` (skip when null); returns {data, error, loading, reload}. */
export function useApi<T = unknown>(url: string | null, refreshMs?: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const load = useCallback((fresh = false) => {
    if (!url) return;
    setLoading(true);
    getJSON<T>(url, fresh)
      .then((d) => { setData(d); setError(null); })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [url]);
  useEffect(() => {
    load();
    if (!refreshMs) return;
    const t = setInterval(() => load(), refreshMs);
    return () => clearInterval(t);
  }, [load, refreshMs]);
  return { data, error, loading, reload: () => load(true) };  // reload after a change: skip the shared request
}

export type SourceInfo = { label: string; short?: string; real: boolean; tickers: boolean; market?: boolean; cal?: string; benchmark?: string; etf?: string;
  params?: { price_floor: number; min_volume: number; min_dollar_vol: number; currency: string } };
export type Status = {
  expected_session: string;
  busy: boolean;
  enabled: string[];
  massive_key: boolean;
  expected_sessions?: Record<string, string>;
  final_hours?: Record<string, number>;
  refresh_min?: number;
  sources: Record<string, { latest_date: string | null; expected?: string; derived_from?: string | null; last_success?: string; last_attempt?: string; last_error?: string | null; last_error_at?: string; running?: boolean; provisional?: boolean; progress?: string | null; result?: Record<string, unknown>; enabled: boolean }>;
  log: { t: string; level: string; source: string; msg: string }[];
  scheduler?: { last_check: string; target_session: string };
  breadth20_sources: string[];
  monitor_sources: string[];
  default_breadth20: string;
  default_monitor: string;
  source_info: Record<string, SourceInfo>;
};
export type Series = { source: string; rows: Row[] };

export const BENCH_NAMES: Record<string, string> = {
  "^GSPC": "S&P 500", "^IXIC": "나스닥 종합", "^KS11": "코스피 지수", "^KQ11": "코스닥 지수",
  SPY: "SPY", QQQ: "QQQ", "069500.KS": "KODEX 200", "229200.KS": "KODEX 코스닥150",
};

/** Close-by-date map for a benchmark index stored in the world-index table. */
export function useBench(symbol: string | undefined) {
  const sym = symbol || "^GSPC";
  const { data } = useApi<Record<string, [string, number][]>>(`/api/world/history?symbols=${encodeURIComponent(sym)}`);
  const [map, setMap] = useState<Map<string, number> | null>(null);
  useEffect(() => {
    if (data?.[sym]) setMap(new Map(data[sym]));
  }, [sym, data]);
  return { map, name: BENCH_NAMES[sym] ?? sym };
}
