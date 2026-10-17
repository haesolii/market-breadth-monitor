export default async function Login({ searchParams }: { searchParams: Promise<{ next?: string; error?: string }> }) {
  const { next = "/", error } = await searchParams;
  return (
    <div className="flex min-h-screen items-center justify-center">
      <form method="post" action="/api/login" className="w-80 space-y-3 rounded border border-zinc-800 bg-zinc-950 p-6">
        <div className="font-mono text-sm font-bold text-emerald-400">MARKET BREADTH</div>
        <input type="hidden" name="next" value={next} />
        <input type="password" name="password" autoFocus placeholder="비밀번호" required
          className="w-full rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100" />
        {error && <div className="text-xs text-red-400">비밀번호가 맞지 않습니다.</div>}
        <button className="w-full rounded bg-sky-700 py-2 text-sm text-white hover:bg-sky-600">로그인</button>
      </form>
    </div>
  );
}
