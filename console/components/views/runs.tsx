"use client";

import { useMemo } from "react";
import { runTree } from "@/lib/derive";
import { duration, shortDate } from "@/lib/format";
import type { Run } from "@/lib/types";
import { Empty, Pill } from "../primitives";

const MODE_LABELS: Record<string, string> = {
  single: "单个主 Agent",
  search_ensemble: "并行检索",
  search_child: "检索子任务",
  primary_evaluation: "主评估",
};

function modeLabel(mode: string): string {
  return MODE_LABELS[mode] ?? mode;
}

export function RunsView({ runs }: { runs: Run[] }) {
  const tree = useMemo(() => runTree(runs), [runs]);
  if (!tree.length) return <Empty>还没有运行记录。可以到 Agents 页创建第一次运行。</Empty>;

  return (
    <div className="runs">
      {tree.map(({ run, children }) => (
        <article className="run" key={run.run_id}>
          <div className="run__head">
            <div className="row__main">
              <p className="run__title">
                {modeLabel(run.mode)}
                <em>{run.run_id.replace(/^run-/, "").slice(0, 12)}</em>
              </p>
              {run.prompt ? <p className="run__prompt">{run.prompt}</p> : null}
            </div>
            <div className="row__right">
              <Pill status={run.status} />
            </div>
          </div>

          <p className="run__meta">
            <span>{run.backend ?? "local"}</span>
            {run.effort ? <span>{run.effort}</span> : null}
            {run.role ? <span>{run.role}</span> : null}
            {children.length ? <span>{children.length} 个子 run</span> : null}
            <span>{shortDate(run.created_at)}</span>
            <span>耗时 {duration(run.created_at, run.updated_at)}</span>
          </p>

          {run.error ? <p className="run__out run__out--err">{run.error}</p> : null}
          {!run.error && run.final_text ? <p className="run__out">{run.final_text}</p> : null}

          {children.length ? (
            <div className="run__kids">
              {children.map((child) => (
                <div className="run__kid" key={child.run_id}>
                  <span className="row__main truncate">
                    <b>{modeLabel(child.mode)}</b> <span>{child.role ?? ""}</span>
                  </span>
                  <span className="row__right">
                    <span>{duration(child.created_at, child.updated_at)}</span>
                    <Pill status={child.status} />
                  </span>
                </div>
              ))}
            </div>
          ) : null}
        </article>
      ))}
    </div>
  );
}
