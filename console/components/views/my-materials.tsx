"use client";

import { useState } from "react";
import type { Application, ResumeMaterial } from "@/lib/types";
import { shortDate } from "@/lib/format";
import { Empty, Panel, Pill } from "../primitives";

export function PhonePrepAction({ application }: { application: Application }) {
  return application.phone_prep_available && application.phone_prep_url ? (
    <a className="btn btn--primary" style={{ minHeight: 44 }} href={application.phone_prep_url} target="_blank" rel="noreferrer">
      ☎ 打开电话准备
    </a>
  ) : <span className="muted">电话脚本待准备</span>;
}

export function MyMaterialsView({ materials }: { materials: ResumeMaterial[] }) {
  const [selected, setSelected] = useState<string | null>(null);
  const preview = materials.find((item) => item.id === selected && item.available && item.view_url);
  return <section aria-label="我的简历">
    <header className="trace-heading"><div><h1>我的简历</h1><p className="muted">查看当前登记的简历，电话沟通时快速核对经历。</p></div></header>
    {materials.length ? <div style={{ display: "grid", gap: 16 }}>{materials.map((item) => <Panel key={item.id} title={item.label} meta={<span className="chip">{item.language}</span>}>
      {item.available && item.view_url ? <div className="toolbar">
        <button className="btn" type="button" onClick={() => setSelected(selected === item.id ? null : item.id)} aria-pressed={selected === item.id}>{selected === item.id ? "收起预览" : "预览 PDF"}</button>
        <a className="btn btn--primary" style={{ minHeight: 44 }} href={item.view_url} target="_blank" rel="noreferrer">打开简历 PDF ↗</a>
        {item.source_url && <a className="link" href={item.source_url} target="_blank" rel="noreferrer">查看源稿</a>}
      </div> : <p className="muted">{item.reason || "简历文件暂不可用"}</p>}
    </Panel>)}</div> : <Empty>尚未登记简历。登记现有 PDF 后会出现在这里。</Empty>}
    {preview?.view_url && <Panel title={preview.label + " · PDF 预览"}>
      <p className="muted">若当前浏览器不能显示 PDF，请使用上方“打开简历 PDF”。</p>
      <iframe title={preview.label + " PDF"} src={preview.view_url} style={{ width: "100%", height: "70vh", minHeight: 360, border: "1px solid var(--line)", borderRadius: 8 }} />
    </Panel>}
  </section>;
}

export function PhonePrepView({ applications }: { applications: Application[] }) {
  const [query, setQuery] = useState("");
  const [showEnded, setShowEnded] = useState(false);
  const needle = query.trim().toLocaleLowerCase();
  const visible = applications.filter((app) => (showEnded || !["closed", "rejected", "withdrawn"].includes(app.status)) && `${app.company} ${app.role}`.toLocaleLowerCase().includes(needle));
  const ready = visible.filter((app) => app.phone_prep_available).length;
  return <section aria-label="电话准备">
    <header className="trace-heading"><div><h1>电话准备</h1><p className="muted">接到来电，搜公司名，直接打开对应岗位的沟通提纲。</p></div><span className="count">{ready} 份可打开</span></header>
    <div className="toolbar" style={{ marginBottom: 20 }}>
      <input className="search" style={{ height: 44 }} type="search" placeholder="搜索公司或岗位…" aria-label="搜索电话准备公司或岗位" value={query} onChange={(event) => setQuery(event.target.value)} />
      <button className="toggle" type="button" aria-pressed={showEnded} onClick={() => setShowEnded(!showEnded)}>含已结束岗位</button>
    </div>
    {visible.length ? <div className="trace-list">{visible.map((app) => <article className="trace-row" key={app.application_id}>
      <div className="trace-row__top"><div><h2>{app.company}</h2><p className="muted">{app.role}</p></div><Pill status={app.status} /></div>
      <div className="toolbar" style={{ marginTop: 16 }}><PhonePrepAction application={app} />
        {app.phone_prep_available && app.phone_prep?.prepared_at && <span className="muted">准备于 {shortDate(app.phone_prep.prepared_at)}</span>}
      </div>
    </article>)}</div> : <Empty>{query ? "没有找到匹配的公司或岗位。" : "还没有需要电话准备的岗位记录。"}</Empty>}
  </section>;
}
