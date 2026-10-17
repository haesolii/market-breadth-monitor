"use client";
import { useEffect, useState } from "react";

/** Per-browser preference persisted in localStorage (safe if storage is unavailable). */
export function useSetting<T>(key: string, initial: T): [T, (v: T) => void] {
  const [v, setV] = useState<T>(initial);
  useEffect(() => {
    try {
      const s = localStorage.getItem(key);
      if (s !== null) setV(JSON.parse(s));
    } catch {}
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
