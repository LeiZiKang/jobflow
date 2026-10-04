# 数据契约

`state/` 是当前运行状态的机器可读真相；业务 Markdown/HTML 是人类视图与证据。

## 2026-09-12：按岗位推进

- `state/progress.json` 保存草稿处理台账、源条目摘要、审核去向和同步日期。draft 可为 pending_review / linked_existing / promoted / rejected / stale；promoted 产生 awaiting_user candidate，不授予投递权限。
- `sync-progress` 根据 approved candidate、关联 application、跟进日期与检索记录幂等维护下一步。只有岗位自身未决定才等待用户；不再用整批审批阻塞已批准岗位。
- `prepare-candidate` 关联稳定 candidate ID、平台岗位 ID 与 application，保存精确文字文件及 JD 核实来源，建立单独 waiting_user 最终审批任务。
- `record-followup` 保存观察来源和时间。blocked 不覆盖平台状态；有效观察更新下一次检查日期，关闭的应用不生成跟进。
- `推进求职.html` 与根目录 `求职看板.html` 纳入 render-views 与 validate 漂移检查。投递龄与回复时间是不同指标。
- 核心 CLI mutation 使用仓库级进程锁，活跃租约核对 `JOBFLOW_SESSION_REF`；正常异常回滚状态、审批、事件和生成视图。直接编辑 JSON 和进程强杀不在自动事务恢复保证内。

## Evidence / approval v2

新外部证据必须绑定 v2 审批：application_id、公司/岗位、platform、operation_type、approved_payloads（每个实际文件的 kind/path/sha256/bytes）。流程为 pending → approved → executing（claim-approval）→ consumed（evidence-record 自动消费）。

领取前核对任务依赖、目标、全部内容和有效期；不得重复领取，领取后 30 分钟内记账。操作不确定或超时须保留未验证状态并人工复核，不能自动重发。截图类 proof 必须实际为图片文件。

submitted_verified 要求该 application 的 application_submit + verified_success + audit pass 成功证据；其他操作、失败证据或随便一个 manifest 不能满足。投递前关闭/撤回不计入已投样本。

`state/evidence_policy.json` 只冻结迁移时已存在的两份 manifest 及审批摘要，并限定原五家 legacy application ID。历史未消费/自审缺口仍保留，严格证据检查会继续报告；这些旧审批不能用于任何新操作。新增记录不得通过设置 legacy_evidence 绕过检查。

具体执行步骤见 `runbooks/推进求职.md`。下文旧版“一次性审批”描述以本节的新执行约束为准。

## 状态文件

- `current.json`：目标、指标、当前阶段、开放决定、阻塞和下一动作。
- `applications.json`：投递记录、证据引用，以及进入面试后的 company-centric Case。
- `candidates.json`：当前候选批次、稳定 ID、建议、用户决定状态和岗位档案。
- `task_queue.json`：跨 session 的待办、依赖和授权要求。
- `decision_index.json`：当前仍有效决定的索引；完整理由可链接到决策日志。
- `active_decider.json`：单主租约；运行时可更新。
- `events/events.jsonl`：关键操作与状态变化的追加式精简日志，不复制 session。
- `recurring_jobs.json`：定时任务定义、仓库期望开关、外部 trigger 的独立运行时状态、上一轮结果。
- `memory.json`：带来源和评审状态的 canonical 长期记忆；provider session 与 SQLite run 不属于这里。

`enabled` 是仓库期望状态，不等于外部 scheduler 已同步。`trigger.runtime_status` 使用
`pending_enable` / `pending_disable` / `enabled_confirmed` / `disabled_confirmed` / `unknown`。
任何视图必须同时考虑两者，不能把 pending 显示为已经开关成功。

## 生成视图

- `applications.json` → `01-现在在做/投递记录.md` marker 区块。
- `applications[].case` → `04-面试/公司/<application-id>/index.html`（给人阅读的主要入口）。
- `candidates.json` → `01-现在在做/候选决策.md` 全文件。
- current/applications/candidates/tasks → README 当前状态 marker。
- 全部 canonical state → `DECIDER_BRIEF.md`。
- `memory.json` 中的 accepted memory → `DECIDER_BRIEF.md` 与每次 Agent bounded context。

`jobflow.py render-views` 默认检查，`--write` 才原子写入。所有 mutation 命令必须调用
`write_generated()`，validate 会拒绝任何手工漂移。

## Application Case

应用进入 `interviewing` 或 `offer` 前必须有 `applications[].case`。Case 固定以 application ID
定位，不能使用公司名作目录，也不能自定义写入位置：

```text
04-面试/公司/<application-id>/
├── index.html           # 从 canonical state 生成，只读、主要阅读入口
├── rounds/              # 每轮原始 Markdown 记录
├── preparation/         # 需要时放该公司的准备材料
└── communications/      # 需要时放已批准的沟通稿或证据
```

最小 Case 结构：

```json
{
  "schema_version": 1,
  "directory": "04-面试/公司/<application-id>",
  "view_path": "04-面试/公司/<application-id>/index.html",
  "dossier_ref": "05-检索报告/岗位档案/...html",
  "current_stage": {"code": "...", "label": "...", "updated_at": "ISO", "source_round_id": "..."},
  "waiting_on": {"party": "employer", "summary": "...", "since": "ISO", "source_round_id": "..."},
  "related_task_ids": ["task-..."],
  "next_action": {"task_id": "task-...", "kind": "...", "owner": "agent"},
  "deadline": null,
  "materials": [],
  "open_items": [],
  "rounds": []
}
```

每个 completed round 至少记录 `round_id`、`sequence`、`type`、`status`、`occurred_at`、
`questions`、`outcome`、`source_refs` 和证据强度。信息必须分层：

- `employer_feedback`：公司明确说过的内容，注明原话/转述与来源强度。
- `observations`：用户对“没给出什么、流程如何”等现场观察，作者必须是 human。
- `self_review`：用户自己的复盘，作者必须是 human。
- `agent_analysis`：Agent 的判断，作者必须是 agent，并列 `basis_refs`。

实际回答只写当时说出口的内容；“与事实不一致”等判断只能进入 `self_review` / `agent_analysis`。
`not_recorded` 不得被 Agent 自动补全。`outcome` 引用 feedback/observation 的稳定 ID。
材料须区分 `used_for_submission=true` 的实际附件与参考/生成源。

Case HTML 由 `render-views --write` 生成，不能手改；Dashboard 入口是
`/application/<application-id>`。原始 Markdown 仍用于可编辑事实记录，但不再是主要阅读入口。

## 长期记忆

`state/memory.json` 是跨 Codex / Claude 的正式记忆。SQLite、provider transcript、完整聊天和
模型隐藏上下文都不是 canonical memory。

每条记忆至少包含：

```text
memory_id
type: fact | preference | decision | lesson | procedure | open_question
scope
subject / statement
status: proposed | accepted | rejected | superseded
source_refs
author.type / author.id
evidence_strength
valid_from / valid_until
supersedes / superseded_by
review
```

规则：

- Agent 只能 `propose`；只有 `accepted` 且未过期的记忆进入新 Agent context。
- Agent 不得接受自己提出的记忆。
- `preference` 与 `decision` 必须由 human reviewer 接受；Agent 只能评审事实/流程/教训类记忆。
- 新决定替代旧决定时使用 `supersedes`，旧项转为 `superseded`，不删除历史。
- 所有 accepted memory 必须有来源和 review；secret-like 内容直接拒绝。
- 写入使用文件锁、revision/CAS、fsync 和原子替换，避免并发 Agent 丢更新。
- context 有数量和字符上限，不注入完整旧 session。

命令：

```bash
python3 00-工作流系统/bin/memoryctl.py validate
python3 00-工作流系统/bin/memoryctl.py list --status accepted
python3 00-工作流系统/bin/memoryctl.py context --scope job_search
python3 00-工作流系统/bin/memoryctl.py propose ...
python3 00-工作流系统/bin/memoryctl.py decide --memory-id X --decision accepted ...
```

## Evidence manifest

新外部操作使用 `evidence/<application-id>/<evidence-id>/manifest.json`。manifest 绑定 application、
task、approval、artifact SHA-256/bytes、平台回读、executor 与 auditor。新申请进入 post-submission
状态必须有 manifest；现有 5 家通过显式 `legacy_evidence=true` 兼容，不伪造历史证据。

**截图是 `application_submit` 的必需证据。** 两道校验：`evidence-record` 在记录
`application_submit` + `verified_success` 时直接拒绝没有 `kind` 以 `screenshot` 开头的
proof artifact 的调用（如 `screenshot_success_page`、`screenshot_platform_status`、
`screenshot_confirmation_email`）；`validate` 再按**整条投递**查，要求其 `evidence_manifests`
里至少有一处截图。按投递查而不是按单份 manifest 查，是为了让补救走「追加新 manifest」，
而不是回去改写当时那份。理由：平台侧证据会消失——JD 下架、会话被清之后就取不回来，
文字回读只是 Agent 的转述，截图才是可复核的原件。存放约定
`assets/投递截图/<application-id>/`，操作步骤见 `runbooks/投递.md`。
带 `legacy_evidence=true` 的历史投递豁免；**新投递不得打此标记绕过检查**。

## Golden cases

`golden-cases/cases.json` 保存决策枚举、必需规则、禁止规则和来源。跨模型响应使用结构化
`answers.json`，由 `golden-check --answers` 评分，不比较自然语言措辞。

## Recurring run metrics

`record-run --metric key=value` 保存通用指标；`scheduled-bootstrap` 在 enabled/runtime/slot/重复运行
任一不满足时安全 NO-OP。每日岗位检索只生成候选草稿，不能直接修改 canonical candidates。

所有文件必须：

- 使用 UTF-8 JSON、稳定 ID 和 ISO 8601 时间。
- 不保存 secret 值。
- 对历史迁移数据标注 `migration` 或证据强度。
- 状态变化后同步生成 `DECIDER_BRIEF.md`。

## 应用状态

允许的投递状态：

```text
discovered
jd_verified
screened
researched
awaiting_user_decision
approved
application_prepared
awaiting_final_submit
submitted_unverified
submitted_verified
follow_up_due
interviewing
offer
rejected
withdrawn
closed
```

`submitted_verified` 必须有 `submitted_at` 和至少一个 `evidence_ref`。

候选决定使用 `jobflow.py decide-candidates` 写入稳定 candidate ID；应用状态使用
`jobflow.py set-application-status` 迁移。终态不允许静默回退，纠错应追加事件并由 Decider 审核。

已关闭、已撤回或已拒绝的 Case 可将 `next_action` 设为 `{"task_id": null, "kind": "none", "owner": "levi"}`，保留历史关联任务但不再要求待执行任务。

## 任务状态

允许：`pending`、`in_progress`、`waiting_user`、`blocked`、`done`、`cancelled`。

任务必须声明：优先级、允许动作、是否需要审批、依赖、来源和完成标准。

任务状态应通过 `jobflow.py set-task-status` 迁移。完成依赖任务后，校验器会把对应阻塞任务
转为可执行状态，并把变化记录到 append-only event log。
