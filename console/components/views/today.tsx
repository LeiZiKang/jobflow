"use client";

import type { TodayData, TodayRow } from "@/lib/types";
import { Empty, Panel, Pill } from "../primitives";
import { PhonePrepAction } from "./my-materials";

function shanghaiTime(value?: string) {
  if (!value) return "未记录提交时间";
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return `${value} · 仅记录日期`;
  const time = new Date(value);
  return Number.isNaN(time.getTime()) ? "时间待核实" : new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", dateStyle: "short", timeStyle: "medium", hour12: false }).format(time);
}

function Rows({ rows, empty }: { rows: TodayRow[]; empty: string }) {
  if (!rows.length) return <p className="muted" style={{ padding: "12px 0", margin: 0 }}>{empty}</p>;
  return <div className="trace-list">{rows.map((row) => <article className="trace-row" key={row.application_id}>
    <div className="trace-row__top"><div><h2>{row.company}</h2><p className="muted">{row.role}</p></div><Pill status={row.status} /></div>
    <p className="muted">{row.channel || "渠道未记录"} · {row.message_at ? `消息时间：${shanghaiTime(row.message_at)}` : `提交时间：${shanghaiTime(row.submitted_at)}`}</p>
    <div className="toolbar"><a className="btn" style={{ minHeight: 44 }} href={row.evidence_url} target="_blank" rel="noreferrer">查看登记证据 ↗</a><PhonePrepAction application={row} /></div>
  </article>)}</div>;
}

export function TodayView({ today }: { today: TodayData | null }) {
  if (!today) return <Empty>今天的数据尚未读取成功，不能按零次投递理解。</Empty>;
  return <section aria-label="Today 今日投递">
    <header className="trace-heading"><div><h1>Today · 今天</h1><p className="muted">{today.date} · 北京时间（UTC+8）</p></div></header>
    <div className="simple-stats" style={{ marginBottom: 24 }}>
      <div style={{ padding: 20 }}><strong style={{ fontSize: 38 }}>{today.verified_count}</strong><p>今天已核实投递岗位</p></div>
      <div style={{ padding: 20 }}><strong style={{ fontSize: 38 }}>{today.company_count}</strong><p>涉及公司（按登记名称）</p></div>
    </div>
    <p className="muted" style={{ marginBottom: 20 }}>按提交日期和岗位记录去重统计。准备材料、发送消息和未验证提交单独列出；今天投出后关闭的岗位仍保留。</p>
    {today.conflicting_application_ids.length > 0 && <p className="banner banner--warn" role="status">有 {today.conflicting_application_ids.length} 个岗位记录冲突，已暂时排除计数，需核对。</p>}
    <div style={{ display: "grid", gap: 24 }}>
      <Panel title="今天已核实投递" meta={`${today.verified_count} 个岗位`}><Rows rows={today.groups.verified} empty="今天还没有满足证据条件的已核实投递。" /></Panel>
      <Panel title="今天已提交 · 尚未验证" meta={`${today.groups.unverified.length} 个岗位`}><Rows rows={today.groups.unverified} empty="没有登记在今天的待验证提交。" /></Panel>
      <Panel title="今天仅发送消息 · 不计投递" meta={`${today.groups.message_only.length} 个岗位`}><Rows rows={today.groups.message_only} empty="没有登记今天已核实发送、但未核实投递的消息记录。" /></Panel>
      <Panel title="当前准备中 · 不计今天投递" meta={`${today.groups.prepared.length} 个岗位`}><Rows rows={today.groups.prepared} empty="当前没有待投递的准备记录。" /></Panel>
      {today.groups.undated.length > 0 && <Panel title="提交日期待核实 · 未归入今天"><Rows rows={today.groups.undated} empty="" /></Panel>}
    </div>
  </section>;
}
