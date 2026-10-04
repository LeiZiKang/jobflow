import { NextRequest, NextResponse } from "next/server";
import { controlRaw } from "@/lib/server/jobflowd";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const id = request.nextUrl.searchParams.get("application_id") ?? "";
  if (!/^[A-Za-z0-9_-]+$/.test(id)) return NextResponse.json({ error: "申请标识无效" }, { status: 400 });
  try {
    const response = await controlRaw(`/submission-evidence?application_id=${encodeURIComponent(id)}`);
    return new NextResponse(await response.arrayBuffer(), { status: response.status, headers: {
      "Content-Type": response.headers.get("Content-Type") ?? "text/plain; charset=utf-8",
      "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
      "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    } });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "读取失败" }, { status: 503 });
  }
}
