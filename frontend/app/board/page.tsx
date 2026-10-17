"use client";
import { useState } from "react";
import { Panel, PeriodButtons, Select } from "@/components/bits";
import { IndexChart } from "@/components/IndexChart";
import { TVChart, TV_INDEX } from "@/components/TVChart";
import { useApi } from "@/lib/api";
import { useSetting } from "@/lib/settings";

type Item = { symbol: string; name: string; region: string };
const REGION_ORDER = ["미국", "아시아", "유럽", "미주", "원자재", "채권"];

/** Chart grid for every symbol in the world-index list. Cells are drawn from our own index data so the
 * 6개월 / 1년 / 3년 period applies exactly (TradingView's widget cannot show 6M or 3Y of daily bars). */
export default function Board() {
  const cfg = useApi<{ items: Item[] }>("/api/world/config");
  const [region, setRegion] = useSetting("board.region", "");
  const [cols, setCols] = useSetting("board.cols", "4");
  const [period, setPeriod] = useSetting("board.period", 252);
  const [big, setBig] = useState<Item | null>(null);
  const items = cfg.data?.items ?? [];
  const regions = [...new Set(items.map((i) => i.region))].sort((a, b) => REGION_ORDER.indexOf(a) - REGION_ORDER.indexOf(b));
  const shown = items.filter((i) => !region || i.region === region);
  const grid = { "2": "md:grid-cols-2", "3": "md:grid-cols-2 xl:grid-cols-3", "4": "md:grid-cols-2 xl:grid-cols-4" }[cols];

  return (
    <div className="space-y-3">
      {big && (
        <Panel title={<>{big.name} <span className="font-mono text-xs text-zinc-500">{TV_INDEX[big.symbol] ?? big.symbol}</span></>}
          right={<>
            {!TV_INDEX[big.symbol] && <PeriodButtons value={period} onChange={setPeriod} />}
            <button className="text-xs text-zinc-400 hover:text-white" onClick={() => setBig(null)}>닫기 ✕</button>
          </>}>
          {TV_INDEX[big.symbol] ? (
            <>
              <div className="mb-1 text-[11px] text-zinc-500">TradingView 차트 — 기간은 차트 하단의 기간 버튼으로 선택</div>
              <TVChart symbol={TV_INDEX[big.symbol]} height={560} />
            </>
          ) : <IndexChart symbol={big.symbol} height={560} sessions={period} />}
        </Panel>
      )}
      <Panel
        title="차트 보드"
        right={
          <>
            <PeriodButtons value={period} onChange={setPeriod} />
            <Select value={region} onChange={setRegion} options={[["", "전체"], ...regions.map((r) => [r, r] as [string, string])]} />
            <Select value={cols} onChange={setCols} options={[["4", "가로 4열"], ["3", "가로 3열"], ["2", "가로 2열"]]} />
          </>
        }
      >
        {regions.filter((r) => !region || r === region).map((r) => (
          <section key={r} className="mb-5">
            <h3 className="mb-1 text-xs font-semibold text-zinc-400">{r}</h3>
            <div className={`grid grid-cols-1 gap-2 ${grid}`}>
              {shown.filter((i) => i.region === r).map((it) => (
                <div key={it.symbol} className="rounded border border-zinc-800 bg-zinc-950">
                  <div className="flex items-center gap-1 border-b border-zinc-800 px-2 py-1 text-xs">
                    <button className="truncate font-semibold hover:text-sky-300" title="크게 보기" onClick={() => setBig(it)}>{it.name}</button>
                    <span className="truncate font-mono text-[10px] text-zinc-500">{it.symbol}</span>
                    {TV_INDEX[it.symbol] && <span className="ml-auto shrink-0 rounded bg-sky-900/60 px-1 text-[10px] text-sky-200" title="크게 보기에서 TradingView 차트">TV</span>}
                  </div>
                  <IndexChart symbol={it.symbol} height={240} compact sessions={period} />
                </div>
              ))}
            </div>
          </section>
        ))}
        <div className="text-[11px] text-zinc-500">
          50일선(파랑)·200일선(주황) · 차트 안에서 드래그·휠로 이동/확대 · 이름을 클릭하면 크게 보기 (“TV” = TradingView 차트) · 목록은 “세계 지수” 메뉴 설정을 따릅니다.
        </div>
      </Panel>
    </div>
  );
}
