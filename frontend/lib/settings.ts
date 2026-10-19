"use client";
import { useEffect, useRef, useState } from "react";

/** Per-browser preference persisted in localStorage (safe if storage is unavailable).
 * A key change (e.g. per-market setting) loads that key's value, or `initial` when none is stored. */
export function useSetting<T>(key: string, initial: T): [T, (v: T) => void] {
  const [v, setV] = useState<T>(initial);
  const init = useRef(initial);
  init.current = initial;
  useEffect(() => {
    let nv = init.current;
    try {
      const s = localStorage.getItem(key);
      if (s !== null) nv = JSON.parse(s);
    } catch {}
    setV(nv);
  }, [key]);
  const set = (nv: T) => {
    setV(nv);
    try { localStorage.setItem(key, JSON.stringify(nv)); } catch {}
    window.dispatchEvent(new CustomEvent("setting", { detail: { key, value: nv } }));
  };
  useEffect(() => {
    const h = (e: Event) => {
      const d = (e as CustomEvent).detail;
      if (d.key === key) setV(d.value);
    };
    window.addEventListener("setting", h);
    return () => window.removeEventListener("setting", h);
  }, [key]);
  return [v, set];
}
