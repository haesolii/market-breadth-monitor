import { Panel } from "@/components/bits";

export const metadata = { title: "개인정보처리방침" };

const H = ({ children }: { children: React.ReactNode }) => <h2 className="pt-4 text-sm font-semibold text-zinc-100">{children}</h2>;

export default function Privacy() {
  return (
    <div className="mx-auto max-w-3xl">
      <Panel title="개인정보처리방침">
        <div className="space-y-2 text-sm leading-relaxed text-zinc-300">
          <p>이 사이트(시장 폭 모니터)는 개인 연구용 대시보드와 게시판을 운영하며, 서비스 제공에 필요한 최소한의 정보만 처리합니다.</p>
          <H>1. 처리하는 정보와 목적</H>
          <ul className="list-disc space-y-1 pl-5">
            <li><b>게시판 회원</b>: 아이디, 닉네임, 비밀번호(복원할 수 없는 해시로만 저장) — 회원 식별과 로그인</li>
            <li><b>게시판 글·댓글</b>: 작성 내용, 작성 시각, 작성자 IP 주소 — 게시물 관리, 도배·광고 차단, 분쟁 대응과 법령에 따른 요청 대응. 화면에는 IP 앞 두 자리만 표시합니다.</li>
            <li><b>방문 통계</b>: IP와 브라우저 정보를 섞어 만든 익명 식별값(원래 IP는 저장하지 않음), 방문 날짜, 본 화면 경로 — 이용 현황 파악</li>
            <li>이메일, 전화번호, 실명 등 그 밖의 개인정보는 받지 않습니다.</li>
          </ul>
          <H>2. 보관 기간</H>
          <ul className="list-disc space-y-1 pl-5">
            <li>회원 정보: 탈퇴 요청 시까지 (게시판 운영자에게 요청하면 삭제)</li>
            <li>게시물의 작성 IP: 작성일로부터 최대 1년, 이후 삭제</li>
            <li>방문 통계: 최대 1년</li>
          </ul>
          <H>3. 제3자 제공과 처리 위탁</H>
          <p>개인정보를 제3자에게 제공하지 않습니다. 저장과 호스팅을 위해 다음 서비스를 이용합니다: Supabase(데이터베이스), Vercel(웹 호스팅).</p>
          <H>4. 이용자의 권리</H>
          <p>본인의 회원 정보와 게시물의 열람, 수정, 삭제를 요청할 수 있습니다. 게시물은 직접 수정·삭제할 수 있고, 회원 탈퇴는 운영자에게 요청하면 처리합니다.</p>
          <H>5. 문의</H>
          <p>게시판에 &lsquo;운영자&rsquo; 앞으로 글을 남겨 주세요.</p>
          <p className="pt-4 text-xs text-zinc-500">시행일: 2026-10-24</p>
        </div>
      </Panel>
    </div>
  );
}
