"use client";
import { Panel, TabBar } from "@/components/bits";
import { NewsList, type Item } from "@/components/News";
import { useApi } from "@/lib/api";
import { useSetting } from "@/lib/settings";

type Tab = "watch" | "kr" | "us";

export default function News() {
  const [tab, setTab] = useSetting<Tab>("news.tab", "kr");
  const market = useApi<{ kr: Item[]; us: Item[] }>("/api/news/market");
  const watch = useApi<Item[]>("/api/news/watch");
  const items = tab === "watch" ? watch.data : market.data?.[tab];
  return (
    <div className="mx-auto max-w-4xl space-y-3">
      <Panel title="뉴스" right={<span className="text-[11px] text-zinc-500">5분마다 갱신 · 제목을 누르면 언론사 원문</span>}>
        <TabBar value={tab} onChange={setTab} tabs={[["kr", "한국 시장", market.data?.kr.length], ["us", "미국 시장", market.data?.us.length], ["watch", "관심종목", watch.data?.length]]} />
        <div className="pt-3">
          {!items ? <div className="py-8 text-center text-xs text-zinc-500">불러오는 중…</div>
            : tab === "watch" && !items.length ? <div className="py-8 text-center text-xs text-zinc-500">관심종목이 없거나 뉴스가 없습니다. &lsquo;관심종목&rsquo; 메뉴에서 종목을 추가하세요.</div>
              : <NewsList items={items} />}
        </div>
      </Panel>
      <div className="text-center text-[11px] text-zinc-600">한국: 네이버 증권 · 미국: Google 뉴스 · 개인용 화면 (언론사 약관상 공개·광고 페이지에는 쓰지 않음)</div>
    </div>
  );
}
