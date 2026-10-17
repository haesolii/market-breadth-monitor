import type { Metadata } from "next";
import "./globals.css";
import { Shell } from "@/components/Shell";
import { TooltipProvider } from "@/components/ui/tooltip";

export const metadata: Metadata = {
  title: "시장 폭 모니터",
  description: "20% Bull/Bear Study & Market Monitor — 개인 투자 연구용",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko" className="dark">
      <body className="bg-black text-zinc-200 antialiased" style={{ fontFamily: "'Malgun Gothic', 'Apple SD Gothic Neo', system-ui, sans-serif" }}>
        <TooltipProvider>
          <Shell>{children}</Shell>
        </TooltipProvider>
      </body>
    </html>
  );
}
