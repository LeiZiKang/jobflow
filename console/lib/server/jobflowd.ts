import "server-only";
import http from "node:http";

/**
 * 只在服务端跑。bearer token 由 start.sh 生成后经环境变量注入，
 * 浏览器永远拿不到它——所有请求都从这里代理出去。
 */

export const CONTROL_URL = process.env.JOBFLOWD_URL ?? "http://127.0.0.1:8791";

/** 允许浏览器读的 jobflowd 端点。不在这张表里的一律 404。 */
export const READABLE = ["overview", "applications", "materials", "today", "reports", "agents", "memory", "runs"] as const;
export type Readable = (typeof READABLE)[number];

export function isReadable(value: string): value is Readable {
  return (READABLE as readonly string[]).includes(value);
}

function token(): string {
  const value = process.env.JOBFLOWD_TOKEN;
  if (!value) throw new Error("JOBFLOWD_TOKEN 未配置：请通过 start.sh 启动控制台");
  return value;
}

const directAgent = new http.Agent({ keepAlive: true });

/**
 * 用独立的 http.Agent 直连 jobflowd：设置了 NODE_USE_ENV_PROXY 的机器上，全局 fetch
 * 和 http.globalAgent 都会把发往 127.0.0.1 的请求送进 HTTP 代理，导致本地服务连不上。
 */
export async function controlRaw(relative: string, init?: RequestInit): Promise<Response> {
  const url = new URL(`${CONTROL_URL}${relative}`);
  const headers: Record<string, string> = { Authorization: `Bearer ${token()}` };
  new Headers(init?.headers).forEach((value, key) => {
    headers[key] = value;
  });
  const body = init?.body == null ? undefined : typeof init.body === "string" ? init.body : String(init.body);
  if (body !== undefined) headers["content-length"] = String(Buffer.byteLength(body));
  return new Promise<Response>((resolve, reject) => {
    const request = http.request(
      { hostname: url.hostname, port: url.port, path: `${url.pathname}${url.search}`, method: init?.method ?? "GET", headers, agent: directAgent },
      (incoming) => {
        const chunks: Buffer[] = [];
        incoming.on("data", (chunk: Buffer) => chunks.push(chunk));
        incoming.on("end", () => {
          const responseHeaders = new Headers();
          for (const [key, value] of Object.entries(incoming.headers)) {
            if (value !== undefined) responseHeaders.set(key, Array.isArray(value) ? value.join(", ") : value);
          }
          resolve(new Response(Buffer.concat(chunks), { status: incoming.statusCode ?? 502, headers: responseHeaders }));
        });
        incoming.on("error", reject);
      },
    );
    request.on("error", reject);
    if (body !== undefined) request.write(body);
    request.end();
  });
}

export async function controlJson(relative: string, init?: RequestInit): Promise<unknown> {
  const response = await controlRaw(relative, init);
  const payload = (await response.json()) as unknown;
  if (response.ok) return payload;
  const message =
    payload && typeof payload === "object" && "error" in payload
      ? String((payload as { error: unknown }).error)
      : `jobflowd 返回 ${response.status}`;
  throw new Error(message);
}

/**
 * 写操作要求同源。控制台只监听 127.0.0.1，所以这里把 origin 钉死在回环地址上。
 */
export function sameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  const host = request.headers.get("host");
  if (!origin || !host) return false;
  try {
    const parsed = new URL(origin);
    return parsed.host === host && parsed.protocol === "http:" && parsed.hostname === "127.0.0.1";
  } catch {
    return false;
  }
}
