"use client";
import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import { Err, Kpi, Panel, PeriodButtons, RangePicker, Select } from "@/components/bits";
import { localTime } from "@/components/Shell";
import { TimeChart } from "@/components/TimeChart";
import { IndexChart } from "@/components/IndexChart";
import { TVChart, TV_INDEX } from "@/components/TVChart";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { send, useApi, type Series } from "@/lib/api";
import { downloadCSV } from "@/lib/csv";
import { fmt } from "@/lib/defs";
import { useSetting } from "@/lib/settings";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

type Flag = { code: string; label: string; level: "up" | "down" | "warn" | "stale"; strong: boolean };
type Idx = {
  symbol: string; name: string; region: string; inverse: boolean; live?: boolean; tz?: string; price?: number;
  date?: string; close?: number; chg1d?: number; chg1w?: number; chg1m?: number; chg3m?: number; ytd?: number;
  dd52?: number; above50?: boolean; above200?: boolean; vol20?: number; z1d?: number; stale_days?: number; flags: Flag[];
  unit?: "%" | "bp"; spread_10y3m?: number;
};
type World = { rows: Idx[]; correlation: { symbols: string[]; days: number; matrix: (number | null)[][] }; last_success?: string; last_error?: string };

const PALETTE = ["#38bdf8", "#f472b6", "#a3e635", "#fbbf24", "#c084fc", "#2dd4bf", "#fb923c", "#e879f9", "#4ade80", "#f87171", "#60a5fa", "#facc15"];

// Flag colors: up = green, down = red, warn = amber, stale = gray; "strong" = filled badge + row tint.
const BADGE: Record<string, [string, string]> = {
  up: ["border border-emerald-500 text-emerald-300", "bg-emerald-600 text-white"],
  down: ["border border-red-500 text-red-300", "bg-red-600 text-white"],
  warn: ["border border-amber-500 text-amber-300", "bg-amber-500 text-black"],
  stale: ["border border-zinc-500 text-zinc-400", "bg-zinc-600 text-white"],
};
const ORDER = ["down", "up", "warn", "stale"];
function rowTone(flags: Flag[]): string {
  const strong = flags.filter((f) => f.strong);
  const pick = (strong.length ? strong : flags).sort((a, b) => ORDER.indexOf(a.level) - ORDER.indexOf(b.level))[0];
  if (!pick) return "";
  const s = pick.strong;
  return {
    down: s ? "bg-red-950/70 border-l-4 border-l-red-500" : "border-l-4 border-l-red-700",
    up: s ? "bg-emerald-950/70 border-l-4 border-l-emerald-500" : "border-l-4 border-l-emerald-700",
    warn: "bg-amber-950/40 border-l-4 border-l-amber-500",
    stale: "opacity-60 border-l-4 border-l-zinc-500",
  }[pick.level];
}

const pc = (v: number | undefined | null, inv = false, d = 2, unit: string = "%") => {
  if (v === undefined || v === null) return <span className="text-zinc-600">—</span>;
  const good = inv ? v < 0 : v > 0;
  return <span className={v === 0 ? "" : good ? "text-emerald-400" : "text-red-400"}>{v > 0 ? "+" : ""}{v.toFixed(unit === "bp" ? 1 : d)}{unit}</span>;
};
// Equity-index KPIs exclude commodities and bonds.
const NON_EQUITY = new Set(["원자재", "채권"]);
const yn = (v?: boolean) => (v === undefined || v === null ? "—" : v ? <span className="text-emerald-400">위</span> : <span className="text-red-400">아래</span>);

export default function WorldPage() {
  const [z, setZ] = useSetting("world.z", "2");
  const [dd, setDd] = useSetting("world.dd", "10");
  const w = useApi<World>(`/api/world?z=${z}&dd=${dd}`, 5 * 60 * 1000);
  const [region, setRegion] = useState("");
  const [onlyFlagged, setOnlyFlagged] = useState(false);
  const [picked, setPicked] = useSetting<string[]>("world.picked", ["^GSPC", "^KS11", "^N225", "^GDAXI"]);
  const [range, setRange] = useState(252);
  const [lower, setLower] = useState("bear");
  const [tv, setTv] = useState<{ symbol: string; name: string } | null>(null);
  const [period, setPeriod] = useSetting("board.period", 252);
  const hist = useApi<Record<string, [string, number][]>>(picked.length ? `/api/world/history?symbols=${encodeURIComponent(picked.join(","))}` : null);
  const b20 = useApi<Series>(lower === "bear" ? "/api/breadth20" : null);

  const rows = useMemo(() => w.data?.rows ?? [], [w.data]);
  const regions = [...new Set(rows.map((r) => r.region))];
  const shown = rows.filter((r) => (!region || r.region === region) && (!onlyFlagged || r.flags.length));
  const nameOf = (s: string) => rows.find((r) => r.symbol === s)?.name ?? s;

  const priced = rows.filter((r) => !r.inverse && !NON_EQUITY.has(r.region) && r.chg1d !== undefined && r.chg1d !== null);
  const ups = priced.filter((r) => (r.chg1d ?? 0) > 0).length;
  const a200 = priced.filter((r) => r.above200 !== undefined && r.above200 !== null);
  const flagged = rows.filter((r) => r.flags.some((f) => f.level !== "stale")).length;

  // Comparison chart: union of dates, each index rebased to 100 at its first value in the window, forward-filled.
  const chart = useMemo(() => {
    const h = hist.data ?? {};
    const all = [...new Set(Object.values(h).flatMap((v) => v.map((x) => x[0])))].sort();
    const dates = range ? all.slice(-range) : all;
    const series = picked.filter((s) => h[s]).map((s, i) => {
      const m = new Map(h[s]);
      let base: number | null = null, last: number | null = null;
      const data = dates.map((d) => {
        const v = m.get(d);
        if (v !== undefined) last = v;
        if (last !== null && base === null) base = last;
        return last !== null && base ? +((last / base) * 100).toFixed(2) : null;
      });
      return { name: nameOf(s), data, color: PALETTE[i % PALETTE.length], type: "line" as const };
    });
    let lowerData: (number | null)[] | undefined;
    if (lower === "bear" && b20.data) {
      const m = new Map(b20.data.rows.map((r) => [String(r.date), r.bear as number]));
      lowerData = dates.map((d) => m.get(d) ?? null);
    }
    return { dates, series, lowerData };
  }, [hist.data, picked, range, lower, b20.data, rows]); // eslint-disable-line react-hooks/exhaustive-deps

  const corr = w.data?.correlation;
  const corrOpt = useMemo(() => corr && corr.symbols.length ? {
    backgroundColor: "transparent", animation: false,
    tooltip: { formatter: (p: { value: [number, number, number] }) => `${nameOf(corr.symbols[p.value[0]])} × ${nameOf(corr.symbols[p.value[1]])}: ${p.value[2]}` },
    grid: { left: 110, right: 10, top: 10, bottom: 130 },
    xAxis: { type: "category", data: corr.symbols.map(nameOf), axisLabel: { color: "#a1a1aa", rotate: 90, fontSize: 9, interval: 0 } },
    yAxis: { type: "category", data: corr.symbols.map(nameOf), axisLabel: { color: "#a1a1aa", fontSize: 9, interval: 0 } },
    visualMap: { min: -1, max: 1, calculable: false, orient: "horizontal", left: "center", bottom: 0, itemHeight: 120, textStyle: { color: "#a1a1aa" }, inRange: { color: ["#dc2626", "#18181b", "#10b981"] } },
    series: [{ type: "heatmap", data: corr.matrix.flatMap((row, i) => row.map((v, j) => [i, j, v ?? "-"])), label: { show: corr.symbols.length <= 14, fontSize: 9, color: "#e4e4e7" } }],
  } : null, [corr, rows]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = (s: string) => setPicked(picked.includes(s) ? picked.filter((x) => x !== s) : [...picked, s]);

  return (
    <div className="space-y-3">
      <Err error={w.error ?? w.data?.last_error ?? null} />
      <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
        <Kpi label="상승 마감 주가지수 (1일)" value={`${ups} / ${priced.length}`} tone={ups >= priced.length / 2 ? "up" : "down"} sub="VIX·원자재·채권 제외" />
        <Kpi label="200일선 위 지수 비율" value={a200.length ? `${Math.round((100 * a200.filter((r) => r.above200).length) / a200.length)}%` : "—"} sub={`${a200.filter((r) => r.above200).length}/${a200.length}개`} />
        <Kpi label="특이사항 발생 지수" value={flagged} tone={flagged ? "down" : "flat"} sub="아래 표에서 색상 강조" />
        <Kpi label="VIX" value={fmt(rows.find((r) => r.symbol === "^VIX")?.close, 2)} sub={<>1일 {pc(rows.find((r) => r.symbol === "^VIX")?.chg1d, true, 1)}</>} />
        <Kpi label="마지막 갱신" value={<span className="text-base">{localTime(w.data?.last_success)}</span>} sub={process.env.NEXT_PUBLIC_AUTH === "1" ? "장중 약 5분마다 자동" : "서버 실행 중 1시간마다 자동"} />
      </div>

      <Panel
        title="세계 주요 지수 (World Indices)"
        right={
          <>
            <Select value={region} onChange={setRegion} options={[["", "전체 지역"], ...regions.map((r) => [r, r] as [string, string])]} />
            <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={onlyFlagged} onChange={(e) => setOnlyFlagged(e.target.checked)} />특이사항만</label>
            <span className="text-xs text-zinc-400">급등락 기준</span>
            <Select value={z} onChange={setZ} options={[["1.5", "민감"], ["2", "보통"], ["2.5", "둔감"], ["3", "매우 둔감"]]} />
            <span className="text-xs text-zinc-400">조정 기준</span>
            <Select value={dd} onChange={setDd} options={[["5", "-5% (약세 -10%)"], ["10", "-10% (약세 -20%)"], ["15", "-15% (약세 -30%)"]]} />
            <button className="text-xs text-sky-400" onClick={() => downloadCSV("world_indices.csv", rows.map((r) => ({ ...r, flags: r.flags.map((f) => f.label).join(" / ") })),
              ["symbol", "name", "region", "date", "close", "chg1d", "chg1w", "chg1m", "chg3m", "ytd", "dd52", "above50", "above200", "vol20", "z1d", "flags"])}>CSV 다운로드</button>
          </>
        }
      >
        <div className="mb-2 flex flex-wrap gap-2 text-[11px]">
          <span className="text-zinc-400">특이사항 색상:</span>
          <span className={`rounded px-1.5 ${BADGE.up[1]}`}>강한 상승 신호 (급등·52주 신고가)</span>
          <span className={`rounded px-1.5 ${BADGE.up[0]}`}>상승 (200일선 돌파)</span>
          <span className={`rounded px-1.5 ${BADGE.down[1]}`}>강한 하락 신호 (급락·신저가·약세장·VIX 공포)</span>
          <span className={`rounded px-1.5 ${BADGE.down[0]}`}>하락 (200일선 이탈)</span>
          <span className={`rounded px-1.5 ${BADGE.warn[1]}`}>경계 (조정 국면·VIX ≥ 20)</span>
          <span className={`rounded px-1.5 ${BADGE.stale[1]}`}>데이터 지연</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full font-mono text-xs">
            <thead className="bg-zinc-900 text-zinc-300">
              <tr className="text-right">
                <th className="px-2 py-1 text-left">비교</th><th className="px-2 text-left">지수</th><th className="px-2 text-left">지역</th>
                <th className="px-2">종가</th><th className="px-2">1일</th><th className="px-2">1주</th><th className="px-2">1개월</th><th className="px-2">3개월</th><th className="px-2">연초 대비</th>
                <th className="px-2" title="52주 최고 종가 대비">고점 대비</th><th className="px-2">50일선</th><th className="px-2">200일선</th>
                <th className="px-2" title="최근 20일 변동성 (연율)">변동성 20일</th><th className="px-2">마지막 거래일</th><th className="px-2 text-left">특이사항</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.symbol} className={`border-b border-zinc-900 text-right ${rowTone(r.flags)}`}>
                  <td className="px-2 text-left"><input type="checkbox" checked={picked.includes(r.symbol)} onChange={() => toggle(r.symbol)} /></td>
                  <td className="px-2 py-1 text-left font-sans">
                    <button className="text-left underline decoration-dotted underline-offset-2 hover:text-sky-300" title="차트 열기"
                      onClick={() => setTv({ symbol: r.symbol, name: r.name })}>{r.name}</button>{" "}
                    <span className="font-mono text-[10px] text-zinc-500">{r.symbol}</span>
                  </td>
                  <td className="px-2 text-left font-sans text-zinc-400">{r.region}</td>
                  <td className="px-2">{fmt(r.close, 2)}{r.unit === "bp" && "%"}</td>
                  <td className="px-2">{pc(r.chg1d, r.inverse, 2, r.unit)}</td><td className="px-2">{pc(r.chg1w, r.inverse, 2, r.unit)}</td>
                  <td className="px-2">{pc(r.chg1m, r.inverse, 2, r.unit)}</td><td className="px-2">{pc(r.chg3m, r.inverse, 2, r.unit)}</td><td className="px-2">{pc(r.ytd, r.inverse, 1, r.unit)}</td>
                  <td className="px-2">{r.inverse ? "—" : pc(r.dd52, false, 1)}</td>
                  <td className="px-2">{r.symbol === "^VIX" ? "—" : yn(r.above50)}</td><td className="px-2">{r.symbol === "^VIX" ? "—" : yn(r.above200)}</td>
                  <td className="px-2">{r.vol20 !== undefined && r.vol20 !== null ? (r.unit === "bp" ? `${r.vol20.toFixed(0)}bp` : `${r.vol20.toFixed(1)}%`) : "—"}</td>
                  <td className="px-2 text-zinc-400">{r.date ?? "—"}{r.live && <span className="ml-1 rounded bg-sky-900 px-1 text-sky-200" title={`현재가 ${fmt(r.price, 2)} (장중 잠정값 — 마감 확정 후 다시 저장)`}>장중</span>}</td>
                  <td className="px-2 text-left">
                    {r.flags.map((f) => <span key={f.code} className={`mr-1 inline-block whitespace-nowrap rounded px-1.5 font-sans ${BADGE[f.level][f.strong ? 1 : 0]}`}>{f.label}</span>)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-2 text-[11px] text-zinc-500">
          지수 이름을 클릭하면 차트가 열립니다 · VIX·금리는 상승을 빨간색으로 표시 · 금리 변화는 bp(0.01%p) · “장중” 표시 지수는 진행 중인 당일 값(잠정) · 참고용이며 매매 신호가 아닙니다.
        </div>
      </Panel>

      {tv && (
        <Panel title={<>차트: <span className="text-sky-400">{tv.name}</span> <span className="font-mono text-xs text-zinc-500">{TV_INDEX[tv.symbol] ?? tv.symbol}</span></>}
          right={<>
            {!TV_INDEX[tv.symbol] && <PeriodButtons value={period} onChange={setPeriod} />}
            <button className="text-xs text-zinc-400 hover:text-white" onClick={() => setTv(null)}>닫기 ✕</button>
          </>}>
          {TV_INDEX[tv.symbol] ? <TVChart symbol={TV_INDEX[tv.symbol]} /> : <IndexChart symbol={tv.symbol} sessions={period} />}
        </Panel>
      )}

      <div className="grid gap-3 xl:grid-cols-3">
        <Panel className="xl:col-span-2" title="지수 비교 (기간 시작 = 100)"
          right={<><Select value={lower} onChange={setLower} options={[["bear", "아래: 미국 20% Bear 종목 수"], ["none", "아래 패널 없음"]]} /><RangePicker value={range} onChange={setRange} /></>}>
          {picked.length ? (
            <TimeChart dates={chart.dates} series={chart.series} spy={lower === "bear" ? chart.lowerData : undefined}
              lowerName="미국 Bear 수" lowerBar lowerColor="#ef4444" rebased height={460} yName="지수 (=100)" lines={[{ y: 100, label: "100", color: "#71717a" }]} />
          ) : <div className="text-xs text-zinc-500">표에서 비교할 지수를 체크하세요.</div>}
        </Panel>
        <Panel title={`일간 수익률 상관관계 (최근 ${corr?.days ?? 60}거래일)`}>
          {corrOpt ? <ReactECharts option={corrOpt} style={{ height: 520 }} theme="dark" /> : <div className="text-xs text-zinc-500">데이터 없음</div>}
          <div className="text-[10px] text-zinc-500">같은 날짜 기준이라 시차가 있는 아시아·미국 간 상관은 낮게 나올 수 있습니다.</div>
        </Panel>
      </div>

      <IndexSettings onSaved={w.reload} />
    </div>
  );
}

function IndexSettings({ onSaved }: { onSaved: () => void }) {
  const cfg = useApi<{ items: { symbol: string; name: string; region: string }[]; defaults: { symbol: string; name: string; region: string }[] }>("/api/world/config");
  const [form, setForm] = useState({ symbol: "", name: "", region: "기타" });
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const save = async (items: { symbol: string; name: string; region: string }[]) => {
    setBusy(true);
    try {
      await send("/api/world/config", "POST", items);
      setMsg("저장됨 — 데이터를 다시 받는 중입니다 (수 초)");
      cfg.reload();
      setTimeout(onSaved, 4000);
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  };
  const items = cfg.data?.items ?? [];
  return (
    <Panel title="지수 목록 설정 (추가 / 삭제)" right={<>{msg && <span className="text-xs text-sky-400">{msg}</span>}<Button size="sm" variant="ghost" disabled={busy} onClick={() => cfg.data && save(cfg.data.defaults)}>기본 목록 복원</Button></>}>
      <div className="flex flex-wrap gap-1 text-xs">
        {items.map((it) => (
          <span key={it.symbol} className="rounded border border-zinc-700 px-2 py-0.5">
            {it.name} <span className="text-zinc-500">{it.symbol} · {it.region}</span>
            <button className="ml-1 text-red-400" disabled={busy} onClick={() => save(items.filter((x) => x.symbol !== it.symbol))}>✕</button>
          </span>
        ))}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
        <Input className="h-7 w-32 text-xs" placeholder="Yahoo 심볼 (예: ^SSMI)" value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value.trim() })} />
        <Input className="h-7 w-40 text-xs" placeholder="표시 이름 (예: 스위스 SMI)" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <Input className="h-7 w-24 text-xs" placeholder="지역" value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })} />
        <Button size="sm" disabled={busy || !form.symbol || !form.name || items.some((x) => x.symbol === form.symbol)}
          onClick={() => save([...items, form]).then(() => setForm({ symbol: "", name: "", region: "기타" }))}>추가</Button>
        <span className="text-zinc-500">심볼은 finance.yahoo.com 검색에서 확인 (지수는 보통 ^로 시작). 추가 시 데이터를 받아 유효성을 확인합니다.</span>
      </div>
    </Panel>
  );
}
