/**
 * 状态文案。投递态和跟进态与 `00-工作流系统/bin/jobflow.py` 的
 * APPLICATION_STATUS_LABELS / FOLLOW_UP_STATE_LABELS 保持一致——
 * 网页和命令行说的必须是同一句话。
 */
const STATUS_LABELS: Record<string, string> = {
  // 投递（对齐 jobflow.py APPLICATION_STATUS_LABELS）
  discovered: "已发现",
  jd_verified: "JD 已核实",
  screened: "已初筛",
  researched: "已背调",
  awaiting_user_decision: "待决定",
  approved: "已批准",
  application_prepared: "材料已准备",
  awaiting_final_submit: "待最终提交",
  submitted_unverified: "已提交·未验证",
  submitted_verified: "已投",
  follow_up_due: "待跟进",
  interviewing: "面试中",
  offer: "Offer",
  rejected: "已挂",
  withdrawn: "已撤回",
  closed: "已关闭",
  // 跟进（对齐 jobflow.py FOLLOW_UP_STATE_LABELS）
  overdue_unknown: "已到期，当前状态待核实",
  scheduled: "已安排",
  due: "待跟进",
  completed: "已完成",
  cancelled: "已取消",
  // 任务
  pending: "待执行",
  in_progress: "进行中",
  waiting_user: "等你决定",
  blocked: "已阻塞",
  done: "已完成",
  // run / backend
  running: "运行中",
  queued: "排队中",
  failed: "失败",
  interrupted: "已中断",
  unavailable: "不可用",
  claimed: "已接管",
  unclaimed: "未领取",
  idle: "空闲",
  active: "在线",
  ready: "已验证可用",
  installed_unverified: "装了但没验证",
  auth_required: "要重新登录",
  degraded: "有异常",
  // memory
  accepted: "已接受",
  proposed: "待评审",
  superseded: "已替代",
  // case
  open: "未解决",
  resolved: "已解决",
  recorded: "有记录",
  not_recorded: "没记下来",
};

export type Tone = "ok" | "info" | "warn" | "danger" | "muted";

const TONES: Record<Tone, readonly string[]> = {
  ok: ["completed", "done", "submitted_verified", "offer", "approved", "jd_verified", "active", "ready", "accepted", "resolved", "recorded", "scheduled"],
  info: ["running", "queued", "in_progress", "interviewing", "claimed", "screened", "researched", "application_prepared"],
  warn: [
    "waiting_user",
    "pending",
    "proposed",
    "follow_up_due",
    "due",
    "overdue_unknown",
    "awaiting_user_decision",
    "awaiting_final_submit",
    "submitted_unverified",
    "open",
    "not_recorded",
    "installed_unverified",
  ],
  danger: ["failed", "rejected", "blocked", "interrupted", "unavailable", "auth_required", "degraded"],
  muted: ["closed", "withdrawn", "cancelled", "idle", "unclaimed", "superseded", "discovered"],
};

export function statusLabel(status?: string): string {
  if (!status) return "未知";
  return STATUS_LABELS[status] ?? status.replaceAll("_", " ");
}

export function statusTone(status?: string): Tone {
  if (!status) return "muted";
  for (const tone of Object.keys(TONES) as Tone[]) {
    if (TONES[tone].includes(status)) return tone;
  }
  return "muted";
}

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;

/** `2026-08-30` → `08-30`；`…T05:11:13Z` → `09-11 05:11`。 */
export function shortDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  const withTime = !DATE_ONLY.test(value);
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    ...(withTime ? { hour: "2-digit", minute: "2-digit", hour12: false } : {}),
  }).format(parsed);
}

export function fullDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    ...(DATE_ONLY.test(value) ? {} : { hour: "2-digit", minute: "2-digit", hour12: false }),
  }).format(parsed);
}

/** 正数表示已经过去几天。今天返回 0，未来返回负数。 */
export function daysSince(value?: string | null, now = new Date()): number | null {
  if (!value) return null;
  const parsed = new Date(DATE_ONLY.test(value) ? `${value}T00:00:00` : value);
  if (Number.isNaN(parsed.getTime())) return null;
  const day = 24 * 60 * 60 * 1000;
  const a = Date.UTC(parsed.getFullYear(), parsed.getMonth(), parsed.getDate());
  const b = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((b - a) / day);
}

export function relativeDays(value?: string | null, now = new Date()): string {
  const diff = daysSince(value, now);
  if (diff === null) return "—";
  if (diff === 0) return "今天";
  if (diff === 1) return "昨天";
  if (diff > 0) return `${diff} 天前`;
  if (diff === -1) return "明天";
  return `${-diff} 天后`;
}

export function duration(from?: string, to?: string): string {
  if (!from || !to) return "—";
  const start = new Date(from).getTime();
  const end = new Date(to).getTime();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return "—";
  const seconds = Math.round((end - start) / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m${String(seconds % 60).padStart(2, "0")}s`;
}

/** `05-检索报告/岗位档案/2026-08-25-示例科技.html` → `2026-08-25-示例科技.html` */
export function basename(path?: string): string {
  if (!path) return "";
  return path.split("/").filter(Boolean).at(-1) ?? path;
}
