import { NextResponse, type NextRequest } from "next/server";
import { authToken } from "@/lib/auth";

export async function POST(req: NextRequest) {
  const form = await req.formData();
  const next = String(form.get("next") || "/");
  const safeNext = next.startsWith("/") && !next.startsWith("//") ? next : "/";
  const pw = process.env.DASHBOARD_PASSWORD;
  const url = new URL(safeNext, req.url);
  if (!pw || form.get("password") !== pw) {
    const back = new URL("/login", req.url);
    back.searchParams.set("next", safeNext);
    back.searchParams.set("error", "1");
    return NextResponse.redirect(back, 303);
  }
  const res = NextResponse.redirect(url, 303);
  res.cookies.set("mb_auth", await authToken(pw), { httpOnly: true, secure: true, sameSite: "lax", path: "/", maxAge: 60 * 60 * 24 * 30 });
  return res;
}
