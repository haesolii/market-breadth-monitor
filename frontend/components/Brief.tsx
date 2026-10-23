"use client";
import { Fragment, useState } from "react";
import { Panel } from "@/components/bits";
import { useApi } from "@/lib/api";

type B = { date: string; slot: "us" | "kr"; created_at: string; model: string; text: string };
type Rel = { series: string; name: string; unit: string; good: string; obs_date: string; value: number; prev: number; chg: number;
  date: string; react_date?: string; spx?: number; us10y?: number };

/** **bold** inside a line (the brief is plain markdown: headings, bullets, bold). */
const inline = (t: string) => t.split(/\*\*(.+?)\*\*/g).map((p, i) => (i % 2 ? <b key={i} className="text-zinc-100">{p}</b> : <Fragment key={i}>{p}</Fragment>));

function Markdown({ text }: { text: string }) {
  return (
    <div className="space-y-1 text-sm leading-relaxed text-zinc-300">
      {text.split("\n").map((l, i) => {
        const t = l.trim();
        if (!t) return null;
        if (t.startsWith("#")) return <div key={i} className="pt-2 text-sm font-semibold text-sky-300">{t.replace(/^#+\s*/, "")}</div>;
        if (/^[-*]\s/.test(t)) return <div key={i} className="pl-4 -indent-3">• {inline(t.slice(2))}</div>;
        return <div key={i}>{inline(t)}</div>;
      })}
    </div>
  );
}

/** Latest AI brief (Claude, from the dashboard's own numbers) with earlier ones one click away. */
export function Brief({ compact = false }: { compact?: boolean }) {
  const { data } = useApi<B[]>("/api/brief");
  const [i, setI] = useState(0);
  const [open, setOpen] = useState(!compact);
  if (!data?.length) {
    return compact ? null : (
      <Panel title="AI 시장 브리핑"><div className="text-xs text-zinc-500">아직 브리핑이 없습니다 — GitHub Secret에 ANTHROPIC_API_KEY를 넣으면 미국·한국 장 마감 후 자동 작성됩니다.</div></Panel>
    );
  }
  const b = data[Math.min(i, data.length - 1)];
  return (
    <Panel title={<>AI 시장 브리핑 <span className="text-xs font-normal text-zinc-500">{b.date} · {b.slot === "us" ? "미국 마감 후" : "한국 마감 후"} · Claude가 대시보드 수치로 작성 · 투자 권유 아님</span></>}
      right={<>
        <select value={i} onChange={(e) => setI(Number(e.target.value))} className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200">
          {data.map((x, k) => <option key={k} value={k}>{x.date} {x.slot === "us" ? "미국" : "한국"}</option>)}
        </select>
        {compact && <button className="text-xs text-sky-400" onClick={() => setOpen(!open)}>{open ? "접기" : "펼치기"}</button>}
      </>}>
      {open ? <Markdown text={b.text} /> : <Markdown text={b.text.split(/\n(?=##)/).slice(0, 2).join("\n")} />}
    </Panel>
  );
}

const sgn = (v: number | undefined, d = 2, u = "%") => (v === undefined ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(d)}${u}`);
const col = (v: number | undefined, invert = false) => (v === undefined || v === 0 ? "text-zinc-400" : (v > 0) !== invert ? "text-emerald-400" : "text-red-400");

/** Macro releases seen by the refresh job, with the S&P 500 / 10-year move on the release day. */
export function Releases() {
  const { data } = useApi<Rel[]>("/api/macro/releases?days=90");
  return (
    <Panel title="최근 발표와 시장 반응 (Releases)">
      {!data?.length ? (
        <div className="text-xs text-zinc-500">아직 감지된 발표가 없습니다 — 갱신 작업이 새 발표를 처음 본 날부터 기록됩니다 (FRED 무료 데이터는 과거 발표 시각을 주지 않음).</div>
      ) : (
        <table className="w-full font-mono text-xs">
          <thead className="text-zinc-400"><tr><th className="text-left">발표일</th><th className="text-left">지표</th><th>기준 기간</th><th>발표값</th><th>직전</th><th>변화</th><th title="발표일(또는 다음 거래일) 종가 기준">S&P 500</th><th>미국 10년물</th></tr></thead>
          <tbody>
            {data.map((r) => (
              <tr key={r.series + r.obs_date} className="border-t border-zinc-900 text-center">
                <td className="text-left">{r.date}</td><td className="text-left font-sans">{r.name}</td><td>{r.obs_date.slice(0, 7)}</td>
                <td>{r.value.toFixed(2)}</td><td className="text-zinc-500">{r.prev.toFixed(2)}</td>
                <td className={r.good === "neutral" ? "text-zinc-300" : col(r.chg, r.good === "down")}>{sgn(r.chg, 2, "")}</td>
                <td className={col(r.spx)}>{sgn(r.spx)}</td><td className={col(r.us10y, true)}>{sgn(r.us10y, 0, "bp")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}
