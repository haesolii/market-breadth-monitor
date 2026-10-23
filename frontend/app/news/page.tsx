"use client";
import { Panel } from "@/components/bits";
import { NewsList, type Item } from "@/components/News";
import { useApi } from "@/lib/api";

export default function News() {
  const market = useApi<{ kr: Item[]; us: Item[] }>("/api/news/market");
  const watch = useApi<Item[]>("/api/news/watch");
  return (
    <div className="space-y-3">
      <div className="text-[11px] text-zinc-500">
        제목을 누르면 언론사 원문이 열립니다. 한국: 네이버 증권 주요 뉴스·종목 뉴스, 미국: Google 뉴스 검색. 5분마다 새로 받습니다. 개인용 화면입니다 (언론사 약관상 공개·광고 페이지에는 쓰지 않음).
      </div>
      <div className="grid gap-3 xl:grid-cols-3">
        <Panel title="관심종목 뉴스">
          {watch.data && !watch.data.length ? <div className="text-xs text-zinc-500">관심종목이 없거나 뉴스가 없습니다. 15번 메뉴에서 종목을 추가하세요.</div>
            : <NewsList items={watch.data ?? []} max={60} />}
        </Panel>
        <Panel title="한국 시장 주요 뉴스"><NewsList items={market.data?.kr ?? []} /></Panel>
        <Panel title="미국 시장 뉴스"><NewsList items={market.data?.us ?? []} /></Panel>
      </div>
    </div>
  );
}
