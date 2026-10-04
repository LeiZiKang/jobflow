"use client";
import { useMemo, useState } from "react";
import { basename, shortDate } from "@/lib/format";
import type { Opportunity, Report } from "@/lib/types";
import { Empty } from "../primitives";
import { OpportunitiesView } from "./opportunities";

export function ReportsView({ reports, opportunities }: { reports: Report[]; opportunities: Opportunity[] }) {
  const [mode, setMode] = useState("jobs");
  const [query, setQuery] = useState("");
  const groups = useMemo(() => {
    const linked = new Set(opportunities.map((job) => job.report_path));
    const selected = reports.filter((report) => mode !== "inbound" || report.path.includes("/主动联系日报/"))
      .filter((report) => !linked.has(report.path) && !report.path.includes("/岗位速览/") && !basename(report.path).startsWith("_") && !report.path.endsWith("/岗位目录.html"))
      .filter((report) => !query.trim() || report.title.toLowerCase().includes(query.trim().toLowerCase()));
    const result: Record<string, Report[]> = {};
    selected.forEach((report) => {
      const kind = report.path.includes("/主动联系日报/") ? "主动联系日报" : /汇总|批次|对比/.test(report.title) ? "批次汇总" : /inbound|巡检/.test(report.path) ? "巡检记录" : report.path.includes("/岗位档案/") ? "历史岗位档案" : "其他研究报告";
      (result[kind] ??= []).push(report);
    });
    return result;
  }, [reports, opportunities, query, mode]);
  return <>
    <div className="toolbar"><button className="toggle" type="button" aria-pressed={mode === "jobs"} onClick={() => setMode("jobs")}>按岗位阅读</button>
      <button className="toggle" type="button" aria-pressed={mode === "inbound"} onClick={() => setMode("inbound")}>主动联系日报</button>
      <button className="toggle" type="button" aria-pressed={mode === "other"} onClick={() => setMode("other")}>批次与其他记录</button></div>
    {mode === "jobs" ? <OpportunitiesView opportunities={opportunities} initialRange="all" /> : <>
      <p className="muted">{mode === "inbound" ? "每天按日期查看谁主动联系了你、来源覆盖、消息要点和待办。未查成的渠道会明确标注。" : "岗位报告按岗位单独展示；这里保留跨岗位的汇总与研究记录。所有报告均在新标签页打开。"}</p>
      <input className="search" type="search" aria-label="搜索其他报告" placeholder="搜索报告标题" value={query} onChange={(event) => setQuery(event.target.value)} />
      {Object.keys(groups).length ? Object.entries(groups).map(([kind, items]) => <section className="report-group" key={kind}><h2>{kind}<small> {items.length} 份</small></h2>
        <div className="report-rows">{items.map((report) => <a key={report.report_id} className="report-row" href={report.view_url || undefined} target="_blank" rel="noopener noreferrer">
          <span><b>{report.path.includes("/主动联系日报/") ? (report.path.endsWith("/index.html") ? "主动联系 · 日期索引" : `主动联系日报 · ${report.title}`) : report.title}</b><small>更新于 {shortDate(report.modified_at)}</small></span><span aria-hidden="true">↗</span></a>)}</div>
      </section>) : <Empty>没有匹配的其他报告。</Empty>}
    </>}
  </>;
}
