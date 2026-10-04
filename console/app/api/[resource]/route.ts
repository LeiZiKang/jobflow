import { NextResponse } from "next/server";
import { controlJson, isReadable, sameOrigin } from "@/lib/server/jobflowd";

export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" } as const;

type Context = { params: Promise<{ resource: string }> };

export async function GET(_request: Request, context: Context) {
  const { resource } = await context.params;
  if (!isReadable(resource)) {
    return NextResponse.json({ error: `未知资源 ${resource}` }, { status: 404 });
  }
  try {
    return NextResponse.json(await controlJson(`/${resource}`), { headers: NO_STORE });
  } catch (error) {
    return NextResponse.json({ error: message(error) }, { status: 503 });
  }
}

/** 目前只有 /api/runs 接受写入：创建一次只读 Agent run。 */
export async function POST(request: Request, context: Context) {
  const { resource } = await context.params;
  if (resource !== "runs") {
    return NextResponse.json({ error: `${resource} 不接受写入` }, { status: 405 });
  }
  if (!sameOrigin(request)) {
    return NextResponse.json({ error: "跨源请求已拒绝" }, { status: 403 });
  }
  try {
    const body = (await request.json()) as Record<string, unknown>;
    const mode = body.mode;
    if (mode !== "single" && mode !== "search_ensemble") {
      return NextResponse.json({ error: "mode 只能是 single 或 search_ensemble" }, { status: 400 });
    }
    const prompt = String(body.prompt ?? "").trim();
    if (!prompt) {
      return NextResponse.json({ error: "prompt 不能为空" }, { status: 400 });
    }
    const result = await controlJson(mode === "search_ensemble" ? "/ensembles" : "/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt,
        backend: body.backend === "claude" ? "claude" : "codex",
        effort: String(body.effort ?? "max"),
      }),
    });
    return NextResponse.json(result, { status: 202 });
  } catch (error) {
    return NextResponse.json({ error: message(error) }, { status: 400 });
  }
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
