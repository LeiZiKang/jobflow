"use client";
import { ApplicationsView } from "./applications";
import { isOnTrace } from "@/lib/derive";
import { shortDate } from "@/lib/format";
import type { ConsoleData } from "@/lib/types";

export function OverviewView({ data, onNavigate }: { data: ConsoleData; onNavigate: (page: "opportunities" | "applications" | "reports" | "agents" | "runs") => void }) {
  const pending = data.opportunities.filter((j) => j.stage === "awaiting_user");
  const active = data.applications.filter(isOnTrace);
  const latest = data.opportunities.reduce((date, j) => j.found_at && j.found_at > date ? j.found_at : date, "");
  const newest = data.opportunities.filter((j) => j.found_at === latest);
  return <>
    <header className="simple-heading"><h1>求职概览</h1><p className="muted">先看新岗位和已有回复，需要决定的放在这里。</p></header>
    <div className="simple-stats"><button type="button" onClick={() => onNavigate("opportunities")}><strong>{newest.length}</strong><span>最近检索 · {shortDate(latest)}</span></button>
      <button type="button" onClick={() => onNavigate("applications")}><strong>{active.length}</strong><span>跟踪中</span></button>
      <button type="button" onClick={() => document.getElementById("decisions")?.scrollIntoView({ behavior: "smooth" })}><strong>{pending.length}</strong><span>待你决定</span></button></div>
    <section className="routine-list" aria-label="每日安排">{data.schedules.map((job) => {
      const enabled = job.enabled && job.runtime_status === "enabled_confirmed";
      const status = job.last_run_status === "completed" ? "最近一次已完成" : job.last_run_status === "partial" ? "最近一次部分完成" : job.last_run_status === "blocked" ? "最近一次受阻" : enabled ? "已安排" : "尚未开启";
      return <div className="routine" key={job.job_id}><b>{job.local_time}</b><div><strong>{job.job_id === "job-daily-position-search" ? "每日检索新岗位" : "每日核实 On trace"}</strong><p>{status} · 下次 {shortDate(job.next_due)}{job.blocker ? ` · ${job.blocker.replace("login_required", "需要登录")}` : ""}</p></div></div>;
    })}</section>
    <ApplicationsView applications={data.applications} schedules={data.schedules} compact />
    <section className="decision-list" id="decisions"><h2>待你决定</h2>{pending.length ? pending.map((job) => <a key={job.job_id} href={job.report_url || undefined} target="_blank" rel="noopener noreferrer"><span><b>{job.company}</b><small>{job.role}</small></span><span>查看报告 ↗</span></a>) : <p className="muted">暂时没有需要你决定的岗位。</p>}</section>
  </>;
}
