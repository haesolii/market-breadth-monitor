import { NextResponse, type NextRequest } from "next/server";
import { authToken } from "@/lib/auth";

// Single-user password gate, enabled only when DASHBOARD_PASSWORD is set (the deployed site).

export async function middleware(req: NextRequest) {
  const pw = process.env.DASHBOARD_PASSWORD;
  if (!pw) return NextResponse.next();
  if (req.cookies.get("mb_auth")?.value === (await authToken(pw))) return NextResponse.next();
  const url = req.nextUrl.clone();
  url.pathname = "/login";
  url.search = `?next=${encodeURIComponent(req.nextUrl.pathname)}`;
  return NextResponse.redirect(url);
}

export const config = { runtime: "nodejs", matcher: ["/((?!login|auth/|_next/|favicon.ico).*)"] };
