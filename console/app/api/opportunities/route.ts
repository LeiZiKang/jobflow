import { readFile } from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

/** Read the checked, generated catalog; no credentials or provider runtime needed. */
export async function GET() {
  const repo = process.env.JOBFLOW_REPO || path.resolve(process.cwd(), "..");
  try {
    const data = JSON.parse(await readFile(path.join(repo, "05-检索报告", "岗位目录.json"), "utf8"));
    if (data.schema_version !== 1 || !Array.isArray(data.opportunities)) throw new Error("岗位目录格式不正确");
    return NextResponse.json(data, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "岗位目录读取失败" }, { status: 503 });
  }
}
