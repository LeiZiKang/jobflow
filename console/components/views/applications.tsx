"use client";

import { useState } from "react";
import { PhonePrepAction } from "./my-materials";
import { daysSince, fullDate, relativeDays, shortDate, statusLabel } from "@/lib/format";
import { isOnTrace } from "@/lib/derive";
import type { Application, ApplicationCase, CaseRound, JobSchedule } from "@/lib/types";
import { Bullets, Empty, Panel, Pill, Refs, Subhead } from "../primitives";

export function ApplicationsView({ applications, schedules = [], compact = false }: { applications: Application[]; schedules?: JobSchedule[]; compact?: boolean }) {
  const [open, setOpen] = useState<string | null>(null);
  const [filter, setFilter] = useState("active");
  const active = applications.filter(isOnTrace).sort((a, b) => (a.attention_priority?.rank ?? 25) - (b.attention_priority?.rank ?? 25) || (a.attention_priority?.waiting_days ?? 0) - (b.attention_priority?.waiting_days ?? 0));
  const ended = applications.filter((a) => ["closed", "rejected", "withdrawn"].includes(a.status));
  const prepared = applications.filter((a) => !isOnTrace(a) && !ended.includes(a));
  const visible = compact || filter === "active" ? active : filter === "ended" ? ended : prepared;
  const schedule = schedules.find((j) => j.job_id === "job-daily-ontrace-check");
  const confirmed = schedule?.enabled && schedule.runtime_status === "enabled_confirmed";
  if (!applications.length) return <Empty>还没有投递记录。</Empty>;
  return <section className="trace-section" aria-label="On trace 岗位跟踪">
    <header className="trace-heading"><div><h1>{compact ? "跟踪中" : filter === "ended" ? "已结束的岗位" : filter === "prepared" ? "待投递的岗位" : "On trace · 跟踪中"}</h1>
      {!compact && <p className="muted">已投递的岗位持续核实，已结束的单独收起。</p>}</div><span className="count">{visible.length} 个</span></header>
    {!compact && <div className="toolbar">{[["active", "跟踪中", active.length], ["ended", "已结束", ended.length], ["prepared", "待投递", prepared.length]].filter(([key,, count]) => key !== "prepared" || Number(count) > 0).map(([key,label,count]) => <button className="toggle" type="button" key={key} aria-pressed={filter === key} onClick={() => setFilter(String(key))}>{label} {count}</button>)}</div>}
    {!compact && filter === "active" && <p className="trace-schedule">{confirmed ? `每天 ${schedule.local_time} 核实平台进度 · 下次 ${shortDate(schedule.next_due)}` : "例行核实尚未启用"}。仅有新进展或需要处理的问题时提醒。</p>}
    {visible.length ? <div className="trace-list">{visible.map((application) => {
      const expanded = open === application.application_id;
      const attempt = application.follow_up_observations?.at(-1);
      const blocked = attempt?.outcome === "blocked";
      const summary = blocked ? attempt.note : ["closed", "rejected", "withdrawn"].includes(application.status) ? application.last_note || application.platform_readback || "已结束。" : application.platform_readback || "等待到投递平台核实当前进度。";
      return <article className="trace-row" key={application.application_id}>
        <div className="trace-row__top"><div><h2>{application.company}</h2><p className="muted">{application.role}</p></div><div className="trace-statuses">{isOnTrace(application) && application.attention_priority && <span className="priority-badge" data-level={application.attention_priority.level}>{application.attention_priority.level ? `P${application.attention_priority.level} · ` : ""}{application.attention_priority.label}</span>}<Pill status={application.status} /></div></div>
        <p className={blocked ? "trace-record trace-record--blocked" : "trace-record"}><span>{blocked ? "核实受阻" : "最近记录"}</span>{summary}</p>
        {isOnTrace(application) && application.attention_priority && <p className="trace-priority-reason">{application.attention_priority.reason} · 截至 {shortDate(application.attention_priority.as_of)}{application.attention_priority.verification === "blocked" ? " · 最新核实受阻，保留原等级" : ""}</p>}
        <div className="toolbar" style={{ margin: "12px 0" }}><PhonePrepAction application={application} /></div>
        <div className="trace-row__foot"><span>最后核实：{application.last_platform_check_at ? shortDate(application.last_platform_check_at) : application.platform_readback ? "见上方记录" : "尚未核实"}</span>
          {!compact && <span>投递于 {shortDate(application.submitted_at)}</span>}
          <button className="link" type="button" aria-expanded={expanded} onClick={() => setOpen(expanded ? null : application.application_id)}>{expanded ? "收起详情" : "沟通与证据"}</button></div>
        {expanded && <Detail application={application} />}
      </article>;
    })}</div> : <Empty>{filter === "ended" ? "没有已结束的岗位。" : filter === "prepared" ? "没有待投递记录。" : "当前没有在跟踪的岗位。"}</Empty>}
  </section>;
}

function Detail({ application }: { application: Application }) {
  return (
    <div className="app__detail">
      <div>
        <dl className="kv">
          <div>
            <dt>投递 ID</dt>
            <dd className="mono">{application.application_id}</dd>
          </div>
          <div>
            <dt>跟进</dt>
            <dd>
              {application.follow_up_due ? fullDate(application.follow_up_due) : "无"}
              {application.follow_up_state ? ` · ${statusLabel(application.follow_up_state)}` : ""}
            </dd>
          </div>
          <div>
            <dt>证据强度</dt>
            <dd>
              {application.evidence_strength ?? "未记录"}
              {application.legacy_evidence ? " · 历史证据" : ""}
            </dd>
          </div>
          {application.updated_at ? (
            <div>
              <dt>最后更新</dt>
              <dd>
                {fullDate(application.updated_at)}
                {application.last_actor ? ` · ${application.last_actor}` : ""}
              </dd>
            </div>
          ) : null}
        </dl>
      </div>

      {application.platform_readback ? (
        <div>
          <Subhead title="平台回读" />
          <p className="note">{application.platform_readback}</p>
        </div>
      ) : null}

      {application.last_note ? (
        <div>
          <Subhead title="最新说明" />
          <p className="note">{application.last_note}</p>
        </div>
      ) : null}

      {application.evidence_refs?.length ? (
        <div>
          <Subhead title="证据" />
          <Refs items={application.evidence_refs} />
        </div>
      ) : null}

      {application.case ? <CaseBlock detail={application.case} viewUrl={application.view_url} /> : (
        <p className="faint" style={{ fontSize: "var(--fs2)" }}>还没进面试，所以没有公司 Case。</p>
      )}
    </div>
  );
}

function CaseBlock({ detail, viewUrl }: { detail: ApplicationCase; viewUrl?: string | null }) {
  const openItems = (detail.open_items ?? []).filter((item) => !item.status || item.status === "open");
  return (
    <>
      <div>
        <Subhead
          title="公司 Case"
          meta={
            viewUrl ? (
              <a className="link" href={viewUrl} target="_blank" rel="noreferrer">
                打开完整 Case ↗
              </a>
            ) : null
          }
        />
        <dl className="kv">
          <div>
            <dt>当前阶段</dt>
            <dd>{detail.current_stage?.label ?? "未记录"}</dd>
          </div>
          <div>
            <dt>等谁</dt>
            <dd>{detail.waiting_on?.summary ?? "未记录"}</dd>
          </div>
          <div>
            <dt>开启于</dt>
            <dd>{detail.opened_at ? fullDate(detail.opened_at) : "—"}</dd>
          </div>
          {detail.closed_at ? (
            <div>
              <dt>关闭于</dt>
              <dd>{fullDate(detail.closed_at)}</dd>
            </div>
          ) : null}
        </dl>
      </div>

      {openItems.length ? (
        <div>
          <Subhead title={`未解决 ${openItems.length} 项`} />
          <div className="rows">
            {openItems.map((item) => (
              <div className="row" key={item.item_id}>
                <div className="row__main">
                  <p className="row__title">{item.summary}</p>
                  <p className="row__sub">
                    {item.category === "decision" ? "需要决定" : "事实缺口"} · 归属 {item.owner ?? "未指定"}
                  </p>
                </div>
                <div className="row__right">
                  <Pill status="open" />
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {detail.materials?.length ? (
        <div>
          <Subhead title="用到的材料" />
          <div className="materials">
            {detail.materials.map((material) => (
              <p className="material" key={material.path ?? material.label}>
                <span className="truncate">{material.label ?? material.path}</span>
                {material.used_for_submission ? <span className="material__flag">实际投出</span> : null}
              </p>
            ))}
          </div>
        </div>
      ) : null}

      {detail.rounds?.length ? (
        <div style={{ display: "grid", gap: "var(--s3)" }}>
          <Subhead title={`面试轮次 ${detail.rounds.length}`} />
          {detail.rounds.map((round) => (
            <Round key={round.round_id} round={round} />
          ))}
        </div>
      ) : null}
    </>
  );
}

function Round({ round }: { round: CaseRound }) {
  const missing = (round.questions ?? []).filter((q) => q.answer_state !== "recorded").length;
  return (
    <article className="round">
      <div className="round__head">
        <b>
          第 {round.sequence ?? 1} 轮 · {round.type ?? "未分类"}
        </b>
        <span className="chip">{round.medium ?? "—"}</span>
        <span className="chip">{shortDate(round.occurred_at)}</span>
        <Pill status={round.status} />
        {missing ? <span className="overdue">{missing} 题没记下来</span> : null}
      </div>

      {round.questions?.length ? (
        <div className="qa">
          {round.questions.map((question) => (
            <div className="qa__item" key={question.question_id}>
              <span className="qa__q">{question.prompt ?? question.topic}</span>
              <span className={question.actual_answer ? "qa__a" : "qa__a qa__a--missing"}>
                {question.actual_answer ?? "没记录当时怎么答的"}
              </span>
            </div>
          ))}
        </div>
      ) : null}

      {round.outcome?.summary ? <p className="note" style={{ marginTop: "var(--s3)" }}>{round.outcome.summary}</p> : null}

      {round.self_review ? (
        <div style={{ marginTop: "var(--s3)" }}>
          <Subhead title="自己的复盘" />
          {round.self_review.summary ? <p className="muted" style={{ fontSize: "var(--fs2)" }}>{round.self_review.summary}</p> : null}
          <Bullets items={round.self_review.issues} />
          {round.self_review.next_time?.length ? (
            <>
              <p className="label" style={{ marginTop: "var(--s2)" }}>下次</p>
              <Bullets items={round.self_review.next_time} />
            </>
          ) : null}
        </div>
      ) : null}

      {round.agent_analysis?.length ? (
        <div style={{ marginTop: "var(--s3)" }}>
          <Subhead title="Agent 复盘" />
          {round.agent_analysis.map((analysis) => (
            <div key={analysis.analysis_id} style={{ marginTop: "var(--s2)" }}>
              <p className="muted" style={{ fontSize: "var(--fs2)" }}>{analysis.summary}</p>
              <Bullets items={analysis.findings} />
            </div>
          ))}
        </div>
      ) : null}

      <p className="task__foot" style={{ marginTop: "var(--s3)" }}>
        <span>证据 {round.evidence_strength ?? "未标注"}</span>
        {round.occurred_at ? <span>{relativeDays(round.occurred_at)}</span> : null}
      </p>
    </article>
  );
}
