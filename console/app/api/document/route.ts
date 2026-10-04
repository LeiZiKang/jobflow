import { NextRequest, NextResponse } from "next/server";
import { reportLinks } from "@/lib/server/report-links";
import { controlRaw } from "@/lib/server/jobflowd";

export const dynamic = "force-dynamic";

/**
 * 代理仓库里的 HTML / PDF / 截图。路径白名单由 jobflowd 一侧执行，
 * 这里只负责把响应头原样带过来，并强制 nosniff。
 */
/**
 * 报告页的 CSP 禁止脚本，所以主题由服务端按 cookie 写进 <html data-theme>，
 * 与控制台顶栏 ☀/☾ 按钮一致。只接受 light / dark 两个值。
 */
function withTheme(html: string, theme: string | undefined): string {
  if (theme !== "light" && theme !== "dark") return html;
  return html.replace(/<html(\s|>)/i, `<html data-theme="${theme}"$1`);
}

/** 报告页不走 Next layout，补上控制台的 favicon（CSP 的 img-src 'self' 允许）。报告自带图标时不覆盖。 */
function withFavicon(html: string): string {
  if (/<link\b[^>]*\brel\s*=\s*["']?[^"'>]*\bicon\b/i.test(html)) return html;
  const link = '<link rel="icon" href="/icon.svg" type="image/svg+xml">';
  return /<head(\s[^>]*)?>/i.test(html)
    ? html.replace(/<head(\s[^>]*)?>/i, (tag) => tag + link)
    : link + html;
}

export async function GET(request: NextRequest) {
  const relative = request.nextUrl.searchParams.get("path") ?? "";
  if (!relative) {
    return NextResponse.json({ error: "缺少 path 参数" }, { status: 400 });
  }
  try {
    const response = await controlRaw(`/document?path=${encodeURIComponent(relative)}`);
    if (!response.ok) {
      return NextResponse.json({ error: await response.text() }, { status: response.status });
    }
    const csp = response.headers.get("Content-Security-Policy");
    const contentType = response.headers.get("Content-Type") ?? "application/octet-stream";
    const body = contentType.startsWith("text/html")
      ? withTheme(withFavicon(reportLinks(await response.text(), relative)), request.cookies.get("jobflow-theme")?.value)
      : await response.arrayBuffer();
    return new NextResponse(body, {
      headers: {
        "Content-Type": response.headers.get("Content-Type") ?? "application/octet-stream",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        ...(csp ? { "Content-Security-Policy": csp } : {}),
      },
    });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : String(error) }, { status: 403 });
  }
}
