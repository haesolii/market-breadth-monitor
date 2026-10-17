import { NextResponse, type NextRequest } from "next/server";

export async function GET(req: NextRequest) {
  const res = NextResponse.redirect(new URL("/login", req.url), 303);
  res.cookies.delete("mb_auth");
  return res;
}
