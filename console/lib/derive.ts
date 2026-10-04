import { daysSince } from "./format";
import type { Application, Run, Task } from "./types";

/** 跟进已经到期或逾期、且这条投递还活着的。按逾期最久排前面。 */
export type FollowUp = { application: Application; overdueDays: number };

const DEAD_STATES = new Set(["closed", "rejected", "withdrawn", "offer"]);

export function overdueFollowUps(applications: Application[], now = new Date()): FollowUp[] {
  return applications
    .filter((item) => !DEAD_STATES.has(item.status) && item.follow_up_state !== "cancelled")
    .map((application) => ({ application, overdueDays: daysSince(application.follow_up_due, now) ?? -Infinity }))
    .filter((entry) => entry.overdueDays >= 0)
    .sort((a, b) => b.overdueDays - a.overdueDays);
}

/** 只挑还需要动作的任务，等你决定的排最前，然后按 priority。 */
const TASK_RANK: Record<string, number> = { waiting_user: 0, in_progress: 1, pending: 2, blocked: 3 };

export function actionableTasks(tasks: Task[]): Task[] {
  return [...tasks]
    .filter((task) => task.status !== "done")
    .sort((a, b) => {
      const rank = (TASK_RANK[a.status] ?? 9) - (TASK_RANK[b.status] ?? 9);
      if (rank !== 0) return rank;
      return (a.priority ?? 99) - (b.priority ?? 99);
    });
}

/** Case 里还没解决的开放事项，跨所有投递汇总。 */
export type OpenItem = { application: Application; itemId: string; summary: string; category?: string; owner?: string };

export function openCaseItems(applications: Application[]): OpenItem[] {
  const out: OpenItem[] = [];
  for (const application of applications) {
    for (const item of application.case?.open_items ?? []) {
      if (item.status && item.status !== "open") continue;
      out.push({
        application,
        itemId: item.item_id,
        summary: item.summary ?? item.item_id,
        category: item.category,
        owner: item.owner,
      });
    }
  }
  return out;
}

/** ensemble 是一棵树：orchestrator 下面挂 search_child 和 primary_evaluation。 */
export type RunNode = { run: Run; children: Run[] };

export function runTree(runs: Run[]): RunNode[] {
  const children = new Map<string, Run[]>();
  for (const run of runs) {
    if (!run.parent_run_id) continue;
    children.set(run.parent_run_id, [...(children.get(run.parent_run_id) ?? []), run]);
  }
  return runs
    .filter((run) => !run.parent_run_id)
    .map((run) => ({
      run,
      children: (children.get(run.run_id) ?? []).sort(
        (a, b) => (a.created_at ?? "").localeCompare(b.created_at ?? "")
      ),
    }));
}

export function activeRunCount(runs: Run[]): number {
  return runs.filter((run) => run.status === "running" || run.status === "queued").length;
}

/** Active submissions remain tracked until explicitly ended; unverified stays labeled. */
export function isOnTrace(application: Application): boolean {
  return ["submitted_unverified", "submitted_verified", "follow_up_due", "interviewing", "offer"].includes(application.status)
    && (Boolean(application.submitted_at) || application.status === "submitted_unverified");
}
