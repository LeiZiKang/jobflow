"use client";

import { useEffect, useState } from "react";
import type { UpdateStatus } from "@/lib/types";

const DISMISSED_KEY = "jobflow-dismissed-release";

export function UpdateBanner({ refreshAt }: { refreshAt: Date | null }) {
  const [update, setUpdate] = useState<UpdateStatus | null>(null);
  const [dismissed, setDismissed] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    try { setDismissed(localStorage.getItem(DISMISSED_KEY)); } catch { /* Storage can be unavailable. */ }
    void fetch("/api/update", { cache: "no-store" })
      .then(async (response) => response.ok ? await response.json() as UpdateStatus : null)
      .then((value) => { if (active) setUpdate(value); })
      .catch(() => { if (active) setUpdate(null); });
    return () => { active = false; };
  }, [refreshAt]);
  if (!update || update.status !== "ok" || !update.update_available || update.stale ||
      !update.latest_version || !update.release_url || dismissed === update.latest_version ||
      !update.release_url.startsWith("https://github.com/")) return null;
  return <div className="banner banner--warn" role="status">
    <a href={update.release_url} target="_blank" rel="noreferrer">有新版本 v{update.latest_version} · 查看更新说明</a>
    <button type="button" className="icon-btn" aria-label="关闭更新提示" onClick={() => {
      setDismissed(update.latest_version);
      try { localStorage.setItem(DISMISSED_KEY, update.latest_version!); } catch { /* Keep this session dismissed. */ }
    }}>×</button>
  </div>;
}
