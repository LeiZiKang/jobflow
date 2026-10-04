"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { EMPTY_DATA, loadConsole } from "@/lib/client";
import { activeRunCount, isOnTrace, overdueFollowUps } from "@/lib/derive";
import { shortDate } from "@/lib/format";
import type { ConsoleData, ResourceErrors } from "@/lib/types";
import { AgentsView } from "./views/agents";
import { ApplicationsView } from "./views/applications";
import { MemoryView } from "./views/memory";
import { MyMaterialsView, PhonePrepView } from "./views/my-materials";
import { OverviewView } from "./views/overview";
import { OpportunitiesView } from "./views/opportunities";
import { ReportsView } from "./views/reports";
import { RunsView } from "./views/runs";
import { UpdateBanner } from "./update-banner";
import { ThemeToggle } from "./theme-toggle";
import { TodayView } from "./views/today";

const REFRESH_MS = 20_000;

type PageId = "today" | "opportunities" | "overview" | "applications" | "materials" | "phone-prep" | "reports" | "agents" | "memory" | "runs";

const NAV: Array<{ id: PageId; label: string }> = [
  { id: "today", label: "Today · 今天" },
  { id: "opportunities", label: "检索岗位" },
  { id: "overview", label: "总览" },
  { id: "applications", label: "跟踪中" },
  { id: "phone-prep", label: "电话准备" },
  { id: "materials", label: "我的简历" },
  { id: "reports", label: "报告" },
  { id: "agents", label: "执行器" },
  { id: "memory", label: "记忆" },
  { id: "runs", label: "运行记录" },
];

function isPageId(value: string): value is PageId {
  return NAV.some((item) => item.id === value);
}

export function Console() {
  const [page, setPage] = useState<PageId>("today");
  const [data, setData] = useState<ConsoleData>(EMPTY_DATA);
  const [errors, setErrors] = useState<ResourceErrors>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [stamp, setStamp] = useState<Date | null>(null);

  const refresh = useCallback(async (quiet = false) => {
    if (quiet) setRefreshing(true);
    const result = await loadConsole();
    setData(result.data);
    setErrors(result.errors);
    setStamp(new Date());
    setLoading(false);
    setRefreshing(false);
  }, []);

  useEffect(() => {
    const hash = window.location.hash.slice(1);
    if (isPageId(hash)) setPage(hash);
    void refresh();
    const timer = window.setInterval(() => void refresh(true), REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const go = useCallback((next: PageId) => {
    setPage(next);
    window.history.replaceState(null, "", `#${next}`);
    window.scrollTo({ top: 0 });
  }, []);

  const overdue = useMemo(() => overdueFollowUps(data.applications), [data.applications]);
  const running = useMemo(() => activeRunCount(data.runs), [data.runs]);
  const proposed = data.memory.counts?.proposed ?? 0;
  const online = !errors.overview;

  const badges: Partial<Record<PageId, { value: number; tone?: "warn" }>> = {
    applications: { value: data.applications.filter(isOnTrace).length },
    memory: proposed ? { value: proposed, tone: "warn" } : { value: 0 },
    runs: running ? { value: running } : { value: 0 },
  };

  const failed = Object.entries(errors);

  return (
    <div className="shell">
      <nav className="rail" aria-label="主导航">
        <button className="rail__brand" type="button" onClick={() => go("today")}>
          <span className="rail__mark">J</span>
          <b>Jobflow</b>
        </button>

        <div className="rail__nav">
          {NAV.filter((item) => !["agents", "memory", "runs"].includes(item.id)).map((item) => {
            const badge = badges[item.id];
            return (
              <button
                type="button"
                key={item.id}
                className="rail__item"
                aria-current={page === item.id ? "page" : undefined}
                onClick={() => go(item.id)}
              >
                <span>{item.label}</span>
                {badge && badge.value > 0 ? (
                  <span className={badge.tone === "warn" ? "rail__badge rail__badge--warn" : "rail__badge"}>
                    {badge.value}
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>

        <details className="rail__tools"><summary>更多</summary><div>{NAV.filter((item) => ["agents", "memory", "runs"].includes(item.id)).map((item) => <button className="rail__item" key={item.id} type="button" onClick={(event) => { go(item.id); event.currentTarget.closest("details")?.removeAttribute("open"); }}>{item.label}</button>)}</div></details>
        <div className="rail__foot">
          <p className="rail__gate">对外发消息、账号操作和最终投递，都要本人先确认。</p>
          <p className="rail__conn">
            <span className={online ? "dot dot--on" : "dot"} />
            {online ? "本地服务已连接" : "本地服务没连上"}
          </p>
        </div>
      </nav>

      <main className="main">
        <UpdateBanner refreshAt={stamp} />
        <header className="topbar">
          <span className="topbar__title">{NAV.find((item) => item.id === page)?.label}</span>
          <span className="topbar__phase">本地求职工作台 · 对外动作需本人确认</span>
          <div className="topbar__right">
            <span className="topbar__stamp">{stamp ? shortDate(stamp.toISOString()) : "连接中"}</span>
            <ThemeToggle />
            <button
              type="button"
              className="icon-btn"
              onClick={() => void refresh(true)}
              disabled={refreshing}
              aria-label="刷新"
            >
              <span className={refreshing ? "spin" : undefined}>↻</span>
            </button>
          </div>
        </header>

        <div className="page">
          {failed.length ? (
            <p className="banner banner--warn" role="status">
              <b>{failed.length} 项没读到</b>
              <span>{failed.map(([key, value]) => `${key}：${value}`).join("　")}</span>
            </p>
          ) : null}

          {loading ? (
            <Loading />
          ) : page === "today" ? (
            <TodayView today={data.today} />
          ) : page === "opportunities" ? (
            <OpportunitiesView opportunities={data.opportunities} />
          ) : page === "overview" ? (
            <OverviewView data={data} onNavigate={go} />
          ) : page === "applications" ? (
            <ApplicationsView applications={data.applications} schedules={data.schedules} />
          ) : page === "materials" ? (
            <MyMaterialsView materials={data.materials} />
          ) : page === "phone-prep" ? (
            <PhonePrepView applications={data.applications} />
          ) : page === "reports" ? (
            <ReportsView reports={data.reports} opportunities={data.opportunities} />
          ) : page === "agents" ? (
            <AgentsView agents={data.agents} decider={data.overview.active_decider} onCreated={() => void refresh(true)} />
          ) : page === "memory" ? (
            <MemoryView memory={data.memory} />
          ) : (
            <RunsView runs={data.runs} />
          )}
        </div>
      </main>
    </div>
  );
}

function Loading() {
  return (
    <div className="loading" aria-label="正在读取本地数据">
      <span className="skeleton loading__strip" />
      <div className="loading__cols">
        <span className="skeleton" />
        <span className="skeleton" />
      </div>
    </div>
  );
}
