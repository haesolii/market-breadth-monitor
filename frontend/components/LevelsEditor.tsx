"use client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ALL_DEFS, defaultLevels, type Levels } from "@/lib/defs";
import { useSetting } from "@/lib/settings";

/** Per-market highlight levels for the Market Monitor table (user setting, not a trading signal). */
export function LevelsEditor({ market, label, n }: { market: string; label: string; n?: number | null }) {
  const [stored, setLevels] = useSetting<Levels | null>(`mm.levels.${market}`, null);
  const levels = stored ?? defaultLevels(n, market);
  const set = (k: string, i: 0 | 1, v: string) => {
    const cur = [...(levels[k] ?? [null, null])] as [number | null, number | null];
    cur[i] = v === "" || Number.isNaN(Number(v)) ? null : Number(v);
    setLevels({ ...levels, [k]: cur });
  };
  return (
    <div className="rounded border border-zinc-800 p-2">
      <div className="mb-2 flex items-center text-xs text-zinc-400">
        <span>{label} · 색상 강조 기준 (사용자 설정, 매매 신호 아님) · 빈칸 = 강조 안 함 · 종목 수 기본값: 미국 시장은 미국 기준을 시장 규모({n ? n.toLocaleString("en-US") : "—"}종목)에 맞춰 환산, 한국·크립토는 같은 희소성으로 보정한 값</span>
        <Button size="sm" variant="ghost" className="ml-auto h-6" onClick={() => setLevels(null)}>기본값 복원</Button>
      </div>
      <div className="grid gap-x-6 gap-y-1 text-xs md:grid-cols-2">
        {ALL_DEFS.map((d) => {
          const [a, b] = levels[d.key] ?? d.levels;
          const two = d.kind === "up" || d.kind === "down";
          return (
            <div key={d.key} className="flex items-center gap-2">
              <span className="w-56 truncate">{d.ko} <span className="text-zinc-500">({d.en})</span></span>
              <span className="text-zinc-500">{two ? "강조 ≥" : "하단 ≤"}</span>
              <Input className="h-6 w-20 text-xs" value={a ?? ""} onChange={(e) => set(d.key, 0, e.target.value)} />
              <span className="text-zinc-500">{two ? "극단 ≥" : "상단 ≥"}</span>
              <Input className="h-6 w-20 text-xs" value={b ?? ""} onChange={(e) => set(d.key, 1, e.target.value)} />
            </div>
          );
        })}
      </div>
    </div>
  );
}
