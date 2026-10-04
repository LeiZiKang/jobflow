"use client";

import { useEffect, useMemo, useState } from "react";
import type { Opportunity } from "@/lib/types";
import { Empty } from "../primitives";

const OPENED_KEY = "jobflow.opened-job-reports.v1";

export function OpportunitiesView({ opportunities, compact = false, initialRange = "latest" }: {
  opportunities: Opportunity[]; compact?: boolean; initialRange?: "latest" | "all";
}) {
  const [query, setQuery] = useState("");
  const [range, setRange] = useState<string>(opportunities.some(job => job.screening) ? "all" : initialRange);
  const [goalOrder, setGoalOrder] = useState(true);
  const [unopenedOnly, setUnopenedOnly] = useState(false);
  const [foreignOnly, setForeignOnly] = useState(false);
  const [opened, setOpened] = useState<Set<string>>(new Set());
  const keyFor = (job: Opportunity) => `${job.job_id}:${job.revision}`;

  useEffect(() => {
    try {
      const value: unknown = JSON.parse(localStorage.getItem(OPENED_KEY) || "[]");
      if (Array.isArray(value)) setOpened(new Set(value.filter((item): item is string => typeof item === "string")));
    } catch { /* Browser storage is optional; the job list still works. */ }
  }, []);

  const dates = useMemo(() => [...new Set(opportunities.map((job) => job.found_at).filter((d): d is string => Boolean(d)))].sort().reverse(), [opportunities]);
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return opportunities.filter((job) => {
      const date = range === "latest" ? dates[0] : range;
      return (range === "all" || job.found_at === date)
        && (!unopenedOnly || !opened.has(keyFor(job)))
        && (!foreignOnly || job.tags?.includes("真外企"))
        && (!needle || `${job.company} ${job.role} ${job.salary} ${job.channel}`.toLowerCase().includes(needle));
    }).sort((a, b) => {
      if (goalOrder) {
        if (a.screening && !b.screening) return -1;
        if (!a.screening && b.screening) return 1;
        if (a.screening && b.screening) {
          const ak = a.screening.sort_key, bk = b.screening.sort_key;
          for (let i = 0; i < Math.min(ak.length, bk.length); i++) {
            const av = ak[i], bv = bk[i];
            const cmp = typeof av === "number" && typeof bv === "number" ? av - bv : String(av).localeCompare(String(bv));
            if (cmp) return cmp;
          }
        }
      }
      return (b.found_at || "").localeCompare(a.found_at || "") || a.company.localeCompare(b.company);
    });
  }, [opportunities, query, range, dates, opened, unopenedOnly, foreignOnly, goalOrder]);

  function markOpened(job: Opportunity) {
    setOpened((previous) => {
      const next = new Set(previous).add(keyFor(job));
      try { localStorage.setItem(OPENED_KEY, JSON.stringify([...next].slice(-1000))); } catch { /* optional */ }
      return next;
    });
  }

  return <section className="opportunities" aria-label="检索到的岗位">
    <header className="opportunities__head">
      <div><p className="opportunities__eyebrow">{compact ? "最近检索" : "你的岗位收件箱"}</p><h1>{compact ? "最近检索到的岗位" : "检索到了哪些岗位"}</h1>
        <p className="muted">{dates[0] ? `最近一次有岗位记录：${dates[0]}。` : "尚无检索日期记录。"}逐个打开报告阅读，当前列表会保留。</p></div>
      <span className="opportunities__count">{visible.length}<small> / {opportunities.length} 个岗位</small></span>
    </header>
    {!compact && <div className="toolbar opportunities__filters">
      <input className="search" type="search" aria-label="搜索岗位" placeholder="搜索公司、岗位或技术方向" value={query} onChange={(event) => setQuery(event.target.value)} />
      <select aria-label="检索日期" value={range} onChange={(event) => setRange(event.target.value)}>
        <option value="latest">最近一次检索</option><option value="all">全部检索记录</option>
        {dates.map((date) => <option key={date} value={date}>{date}</option>)}
      </select>
      <button className="toggle" type="button" aria-pressed={goalOrder} onClick={() => { setGoalOrder(!goalOrder); if (!goalOrder) setRange("all"); }}>目标优先排序</button>
      <button className="toggle" type="button" aria-pressed={foreignOnly} onClick={() => setForeignOnly(!foreignOnly)}>只看真外企</button>
      <button className="toggle" type="button" aria-pressed={unopenedOnly} onClick={() => setUnopenedOnly(!unopenedOnly)}>只看未打开</button>
    </div>}
    {!opportunities.length ? <Empty>还没有岗位检索记录。已有记录会在这里按岗位展示。</Empty> : !visible.length ? <Empty>没有符合条件的岗位。可以切换日期或清空搜索。</Empty> :
      <ol className="opportunity-list">
        {(compact ? visible.slice(0, 4) : visible).map((job, index) => {
          const wasOpened = opened.has(keyFor(job));
          return <li className="opportunity" key={job.job_id}>
            <span className="opportunity__number">{String(index + 1).padStart(2, "0")}</span>
            <div className="opportunity__body">
              <div className="opportunity__tags"><span>{job.stage_label}</span><span>{job.report_kind}</span>{job.tags?.map(tag => <span key={tag}>{tag}</span>)}{wasOpened && <span className="muted">已打开</span>}</div>
              <h2>{job.company}</h2><p className="opportunity__role">{job.role}</p>
              <p className="opportunity__meta"><b>{job.salary}</b><span>{job.location}</span><span>{job.channel}</span><time>{job.found_at || "日期未记录"}</time></p>
              <p className="opportunity__summary">{job.summary}</p>
              {job.screening && <p className="opportunity__caveat">{job.screening.decision} · 匹配 {job.screening.score_lower}–{job.screening.score_upper} / 100 · 证据覆盖 {job.screening.evidence_coverage_percent}% · 硬线{job.screening.gate === "pass" ? "通过" : job.screening.gate === "fail" ? "不通过" : "待核实"}</p>}
              {job.report_kind === "检索详情" && <p className="opportunity__caveat">检索记录，尚待独立审核。</p>}
              {job.report_url ? <a className="opportunity__open" href={job.report_url} target="_blank" rel="noopener noreferrer" onClick={() => markOpened(job)}>
                {job.report_kind === "岗位档案" || job.report_kind === "岗位报告" ? "阅读岗位报告" : "阅读检索详情"} <span aria-hidden="true">↗</span><span className="sr-only">（新标签页）</span>
              </a> : <span className="muted">报告待补齐</span>}
            </div>
          </li>;
        })}
      </ol>}
  </section>;
}
