"use client";

import { FormEvent, useState } from "react";
import { createRun } from "@/lib/client";
import type { Agent, Backend, Decider, RunMode } from "@/lib/types";
import { Count, Empty, Panel, Pill } from "../primitives";

const DEFAULT_ENSEMBLE = "按 goals.json 检索最近的目标岗位，核对 JD 原文并输出候选草稿。";

type Notice = { tone: "ok" | "danger"; text: string };

export function AgentsView({
  agents,
  decider,
  onCreated,
}: {
  agents: Agent[];
  decider?: Decider;
  onCreated: () => void;
}) {
  const [backend, setBackend] = useState<Backend>("codex");
  const [effort, setEffort] = useState("max");
  const [single, setSingle] = useState("");
  const [ensemble, setEnsemble] = useState(DEFAULT_ENSEMBLE);
  const [busy, setBusy] = useState<RunMode | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);

  async function submit(event: FormEvent, mode: "single" | "search_ensemble") {
    event.preventDefault();
    const prompt = (mode === "single" ? single : ensemble).trim();
    if (!prompt) {
      setNotice({ tone: "danger", text: "先写清楚这次要 Agent 做什么。" });
      return;
    }
    setBusy(mode);
    setNotice(null);
    try {
      await createRun({ mode, prompt, ...(mode === "single" ? { backend, effort } : {}) });
      setNotice({
        tone: "ok",
        text: mode === "single" ? "主 Agent 运行已创建，去 Runs 页看进度。" : "并行检索已创建，结果先进 staging，不会自动投递。",
      });
      if (mode === "single") setSingle("");
      onCreated();
    } catch (error) {
      setNotice({ tone: "danger", text: `创建失败：${error instanceof Error ? error.message : "未知错误"}` });
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      {notice ? (
        <p className={`banner banner--${notice.tone}`} role="status">
          {notice.text}
        </p>
      ) : null}

      <div className="forms">
        <form className="panel form" onSubmit={(event) => void submit(event, "single")}>
          <div>
            <h2 style={{ fontSize: "var(--fs4)", fontWeight: 600 }}>跑一个主 Agent</h2>
            <p className="form__hint">评估、规划、审核这类需要通盘理解上下文的活。</p>
          </div>
          <label className="field">
            <span>要它做什么</span>
            <textarea
              value={single}
              rows={5}
              placeholder="例如：按我的 WLB 和团队成熟度硬线，把今天的候选岗位排个序。"
              onChange={(event) => setSingle(event.target.value)}
            />
          </label>
          <div className="field-row">
            <label className="field">
              <span>Backend</span>
              <select
                value={backend}
                onChange={(event) => {
                  const next = event.target.value as Backend;
                  setBackend(next);
                  if (next === "claude" && effort === "ultra") setEffort("max");
                }}
              >
                <option value="codex">Codex</option>
                <option value="claude">Claude Code</option>
              </select>
            </label>
            <label className="field">
              <span>Effort</span>
              <select value={effort} onChange={(event) => setEffort(event.target.value)}>
                <option value="high">High</option>
                <option value="xhigh">XHigh</option>
                <option value="max">Max</option>
                {backend === "codex" ? <option value="ultra">Ultra</option> : null}
              </select>
            </label>
          </div>
          <button className="btn btn--primary" type="submit" disabled={busy !== null}>
            {busy === "single" ? "创建中…" : "启动"}
          </button>
        </form>

        <form className="panel form" onSubmit={(event) => void submit(event, "search_ensemble")}>
          <div>
            <h2 style={{ fontSize: "var(--fs4)", fontWeight: 600 }}>并行检索队</h2>
            <p className="form__hint">两路只读检索 + 一个主评估汇总。结果先进 staging。</p>
          </div>
          <label className="field">
            <span>检索目标</span>
            <textarea value={ensemble} rows={5} onChange={(event) => setEnsemble(event.target.value)} />
          </label>
          <div className="chips">
            <span className="chip chip--allow">只读</span>
            <span className="chip">broad discovery</span>
            <span className="chip">source audit</span>
            <span className="chip">evaluator</span>
          </div>
          <button className="btn" type="submit" disabled={busy !== null}>
            {busy === "search_ensemble" ? "组队中…" : "开始检索"}
          </button>
        </form>
      </div>

      <Panel title="可用 backend" meta={<Count value={agents.length} />} flush>
        {agents.length ? (
          <div className="agents">
            {agents.map((agent) => (
              <div className="agent" key={agent.agent_id}>
                <div className="row__main">
                  <p className="agent__name">{agent.name ?? agent.agent_id}</p>
                  <p className="agent__meta">
                    {[agent.backend, agent.version, agent.model, agent.effort].filter(Boolean).join(" · ")}
                  </p>
                  {agent.role ? <p className="agent__meta">{agent.role}</p> : null}
                  {agent.error ? <p className="agent__err">{agent.error}</p> : null}
                </div>
                <Pill status={agent.status} />
              </div>
            ))}
          </div>
        ) : (
          <Empty>本机没有检测到可用的 Agent backend。</Empty>
        )}
      </Panel>

      <Panel title="当前 Decider">
        <div className="row">
          <div className="row__main">
            <p className="row__title">{decider?.name ?? "未领取"}</p>
            <p className="row__sub">
              {decider?.agent_id ?? "—"}
              {decider?.lease_expires_at ? ` · 租约至 ${decider.lease_expires_at}` : " · 新 Agent 可以从仓库 Context Bundle 接管"}
            </p>
          </div>
          <div className="row__right">
            <Pill status={decider?.status ?? "unclaimed"} />
          </div>
        </div>
      </Panel>
    </>
  );
}
