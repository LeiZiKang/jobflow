"use client";

import type { ConsoleData, ResourceErrors, ResourceKey } from "./types";

async function getJson(path: string): Promise<unknown> {
  const response = await fetch(path, { cache: "no-store" });
  const payload = (await response.json().catch(() => null)) as unknown;
  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "error" in payload
        ? String((payload as { error: unknown }).error)
        : `${response.status} ${response.statusText}`;
    throw new Error(detail);
  }
  return payload;
}

function list<T>(payload: unknown, key: string): T[] {
  if (payload && typeof payload === "object") {
    const value = (payload as Record<string, unknown>)[key];
    if (Array.isArray(value)) return value as T[];
  }
  return [];
}

export const EMPTY_DATA: ConsoleData = {
  opportunities: [],
  schedules: [],
  overview: {},
  applications: [],
  materials: [],
  today: null,
  reports: [],
  agents: [],
  memory: {},
  runs: [],
};

const KEYS: ResourceKey[] = ["opportunities", "overview", "applications", "materials", "today", "reports", "agents", "memory", "runs"];

/** 各端点并发读取；任何一个失败只标记它自己，其余照常显示。 */
export async function loadConsole(): Promise<{ data: ConsoleData; errors: ResourceErrors }> {
  const settled = await Promise.allSettled(KEYS.map((key) => getJson(`/api/${key}`)));
  const data: ConsoleData = { ...EMPTY_DATA };
  const errors: ResourceErrors = {};

  settled.forEach((result, index) => {
    const key = KEYS[index]!;
    if (result.status === "rejected") {
      errors[key] = result.reason instanceof Error ? result.reason.message : "读取失败";
      return;
    }
    const value = result.value;
    if (key === "overview") data.overview = (value ?? {}) as ConsoleData["overview"];
    else if (key === "memory") data.memory = (value ?? {}) as ConsoleData["memory"];
    else if (key === "opportunities") { data.opportunities = list(value, "opportunities"); data.schedules = list(value, "schedules"); }
    else if (key === "applications") data.applications = list(value, "applications");
    else if (key === "materials") data.materials = list(value, "resumes");
    else if (key === "today") data.today = (value ?? null) as ConsoleData["today"];
    else if (key === "reports") data.reports = list(value, "reports");
    else if (key === "agents") data.agents = list(value, "agents");
    else if (key === "runs") data.runs = list(value, "runs");
  });

  return { data, errors };
}

export async function createRun(body: {
  mode: "single" | "search_ensemble";
  prompt: string;
  backend?: string;
  effort?: string;
}): Promise<void> {
  const response = await fetch("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = (await response.json().catch(() => ({}))) as { error?: string };
  if (!response.ok) throw new Error(payload.error || `${response.status} ${response.statusText}`);
}
