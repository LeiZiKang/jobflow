/**
 * jobflowd 返回的数据形状。
 *
 * 这份文件是控制台与 `00-工作流系统/local-control/jobflowd.py` 之间唯一的契约。
 * 字段名按 jobflowd 的实际输出写死，不做 `a ?? b` 的猜测式兜底——
 * 猜不出来说明契约变了，应该改这里，不是在渲染层加分支。
 */

export type ResourceKey =
  | "opportunities"
  | "overview"
  | "applications"
  | "materials"
  | "today"
  | "reports"
  | "agents"
  | "memory"
  | "runs";

export type Actor = { type?: string; id?: string };

// ── overview ────────────────────────────────────────────────────────────────

export type Task = {
  task_id: string;
  title: string;
  status: string;
  priority?: number;
  role?: string;
  objective?: string;
  inputs?: string[];
  depends_on?: string[];
  allowed_actions?: string[];
  forbidden_actions?: string[];
  output_path?: string;
  stop_conditions?: string[];
  approval_required?: boolean;
  source?: string;
  acceptance?: string[];
  blocked_reason?: string;
  not_before?: string;
};

export type Decider = {
  agent_id?: string;
  name?: string;
  backend?: string | null;
  status?: string;
  lease_expires_at?: string | null;
};

export type Overview = {
  objective?: string;
  phase?: string;
  updated_at?: string;
  metrics?: {
    submitted_verified?: number;
    diagnostic_sample_target?: number | null;
    gap_to_target?: number | null;
    candidate_dossiers_in_latest_comparison?: number;
    interviewing?: number;
    awaiting_user?: number;
  };
  next_actions?: Task[];
  active_decider?: Decider;
};

// ── applications & case ─────────────────────────────────────────────────────

export type CaseQuestion = {
  question_id: string;
  topic?: string;
  prompt?: string;
  answer_state?: "recorded" | "not_recorded" | string;
  actual_answer?: string;
  source?: string;
};

export type CaseStatement = {
  feedback_id?: string;
  observation_id?: string;
  kind?: string;
  statement?: string;
  statement_form?: string;
  attributed_to?: string;
  author?: Actor;
  source?: string;
  evidence_strength?: string;
};

export type CaseAnalysis = {
  analysis_id: string;
  author?: Actor;
  summary?: string;
  findings?: string[];
  basis_refs?: string[];
};

export type CaseRound = {
  round_id: string;
  sequence?: number;
  type?: string;
  status?: string;
  medium?: string;
  occurred_at?: string;
  duration_minutes?: number | null;
  interviewers?: string[];
  questions?: CaseQuestion[];
  employer_feedback?: CaseStatement[];
  observations?: CaseStatement[];
  self_review?: {
    author?: Actor;
    summary?: string;
    issues?: string[];
    next_time?: string[];
  } | null;
  agent_analysis?: CaseAnalysis[];
  outcome?: { code?: string; summary?: string } | null;
  source_refs?: string[];
  evidence_strength?: string;
};

export type CaseOpenItem = {
  item_id: string;
  category?: string;
  summary?: string;
  status?: string;
  owner?: string;
};

export type CaseMaterial = {
  kind?: string;
  label?: string;
  path?: string;
  used_for_submission?: boolean;
};

export type ApplicationCase = {
  opened_at?: string;
  directory?: string;
  view_path?: string;
  dossier_ref?: string;
  current_stage?: { code?: string; label?: string; updated_at?: string };
  waiting_on?: { party?: string; summary?: string; since?: string };
  next_action?: { task_id?: string | null; kind?: string; owner?: string };
  deadline?: string | null;
  materials?: CaseMaterial[];
  open_items?: CaseOpenItem[];
  rounds?: CaseRound[];
  closed_at?: string | null;
  closure_source_ref?: string;
};

export type Application = {
  application_id: string;
  company: string;
  role: string;
  channel?: string;
  resume_version?: string;
  status: string;
  submitted_at?: string;
  follow_up_due?: string | null;
  follow_up_state?: string;
  evidence_refs?: string[];
  evidence_strength?: string;
  legacy_evidence?: boolean;
  platform_readback?: string;
  last_platform_check_at?: string;
  attention_priority?: { level: number | null; rank: number; label: string; reason: string; as_of: string; waiting_days: number | null; verification: string };
  follow_up_observations?: Array<{ outcome: string; observed_at: string; note: string; source_ref: string }>;
  last_note?: string;
  last_actor?: string;
  updated_at?: string;
  view_url?: string | null;
  case?: ApplicationCase;
  phone_prep?: { path?: string; status?: string; prepared_at?: string; job_ref?: string };
  phone_prep_available?: boolean;
  phone_prep_url?: string | null;
};

// ── reports ─────────────────────────────────────────────────────────────────

export type Report = {
  report_id: string;
  title: string;
  kind?: string;
  path: string;
  modified_at?: string;
  view_url?: string | null;
};

// ── agents ──────────────────────────────────────────────────────────────────

export type Agent = {
  agent_id: string;
  name?: string;
  role?: string;
  backend?: string;
  model?: string;
  effort?: string;
  status?: string;
  version?: string;
  error?: string | null;
  current_task?: string;
};

// ── memory ──────────────────────────────────────────────────────────────────

export type MemoryItem = {
  memory_id: string;
  type: string;
  scope: string;
  subject: string;
  statement: string;
  status: string;
  source_refs?: string[];
  author?: Actor;
  evidence_strength?: string;
  sensitivity?: string;
  tags?: string[];
  valid_until?: string | null;
  created_at?: string;
  updated_at?: string;
  supersedes?: string[];
  superseded_by?: string | null;
};

export type MemoryDocument = {
  schema_version?: number;
  revision?: number;
  updated_at?: string;
  items?: MemoryItem[];
  counts?: Partial<Record<"accepted" | "proposed" | "rejected" | "superseded", number>>;
  context_preview?: string;
};

// ── runs ────────────────────────────────────────────────────────────────────

export type RunMode = "single" | "search_ensemble" | "search_child" | "primary_evaluation";
export type Backend = "codex" | "claude";

export type Run = {
  run_id: string;
  parent_run_id?: string | null;
  mode: RunMode | string;
  role?: string;
  backend?: string;
  status: string;
  prompt?: string;
  final_text?: string;
  error?: string | null;
  task_id?: string | null;
  session_id?: string | null;
  model?: string | null;
  effort?: string;
  created_at?: string;
  updated_at?: string;
  metadata?: Record<string, unknown>;
};

// ── 控制台自己派生的东西 ───────────────────────────────────────────────────

export type Opportunity = {
  job_id: string; company: string; role: string; salary: string; location: string;
  channel: string; found_at?: string | null; stage: string; stage_label: string;
  summary: string; report_path?: string | null; report_url?: string | null;
  report_kind: string; revision: string;
  tags?: string[];
  screening?: { decision: string; gate: string; score_lower: number; score_upper: number; evidence_coverage_percent: number; tags: string[]; sort_key: (string | number)[] };
};

export type JobSchedule = {
  job_id: string; title: string; enabled: boolean; local_time?: string;
  next_due?: string; start_date?: string; runtime_status?: string;
  last_run_status?: string; last_run_at?: string; blocker?: string | null;
};

export type TodayRow = Pick<Application, "application_id" | "company" | "role" | "channel" | "status" | "submitted_at" | "phone_prep_available" | "phone_prep_url"> & { evidence_url: string; message_at?: string };
export type TodayData = {
  date: string; timezone: string; verified_count: number; company_count: number;
  groups: Record<"verified" | "unverified" | "prepared" | "message_only" | "undated", TodayRow[]>;
  conflicting_application_ids: string[];
};

export type ResumeMaterial = {
  id: string; label: string; language: string; available: boolean;
  view_url: string | null; source_url?: string | null; reason?: string | null;
};

export type ConsoleData = {
  schedules: JobSchedule[];
  opportunities: Opportunity[];
  overview: Overview;
  applications: Application[];
  materials: ResumeMaterial[];
  today: TodayData | null;
  reports: Report[];
  agents: Agent[];
  memory: MemoryDocument;
  runs: Run[];
};

export type ResourceErrors = Partial<Record<ResourceKey, string>>;

export interface UpdateStatus {
  status: "ok" | "failed" | "disabled" | "unchecked";
  current_version: string;
  latest_version: string | null;
  update_available: boolean;
  release_url: string | null;
  notes: string[];
  checked_at: number | null;
  stale: boolean;
}
