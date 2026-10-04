# 定时任务：通用执行规则

`state/recurring_jobs.json` 定义了三个每日任务。仓库本身不会自己跑，需要一个外部触发器
（Claude Code 桌面定时任务、Codex automation、cron + CLI 都行）每天叫醒一个 Agent。
触发器只负责"叫醒"，做什么、怎么做全在仓库里：

| 顺序 | job | 建议名义时间 | runbook |
|---|---|---|---|
| 1 | `job-inbound-sweep` | 09:00 | `runbooks/inbound巡检.md` |
| 2 | `job-daily-position-search` | 09:30 | `runbooks/每日岗位检索.md` |
| 3 | `job-daily-ontrace-check` | 10:30 | `runbooks/每日Ontrace核实.md` |

时间和时区按自己的作息改；`recurring_jobs.json` 里的时间要和触发器保持一致。

## 为什么建议一个触发器串行跑三段

三个任务都要领 Decider 租约。如果分成三个独立触发器，电脑晚开机时它们会同时补跑、互相抢租约，
后面的直接 blocked。一个触发器按顺序跑三段可以根治这个问题。

## 每一段的固定流程

1. `jobflow.py scheduled-bootstrap --job <job> --scheduled-for <当天名义时间的带时区 ISO>`。
   返回 NO-OP 或非 0：记一行原因，跳过这段。
   `--scheduled-for` 写**名义时间**（slot 标识），不是实际开始时间；实际观察时间另记真实时间。
2. `jobflow.py claim-decider --agent <你> --backend <runtime> --session-ref <本次唯一引用>`，
   并把同值写进 `JOBFLOW_SESSION_REF`。别人的租约有效时不抢占：每 30 秒查一次，最多等 30 分钟，
   仍拿不到就记 blocked，继续下一段。
3. `jobflow.py job-envelope --job <job>` 生成信封，派 collector subagent 按 runbook 只读执行。
4. 主 session 合并结果：写 state / 报告、`record-run`（或 `ontrace_check.py record`）、
   `render-views --write`、`scripts/check-all.sh`，只提交本段文件。
5. `release-decider`，确认释放后再进入下一段。某段失败不影响后面几段，也不伪造结果。

## 边界（所有触发器都一样）

- 只读：不发消息、不回复、不投递、不收藏、不改平台资料、不接受条款。
- 不登录、不读写凭据；遇到登录页 / 验证码 / 浏览器控制权被拿走，记 blocked 交还用户。
- 浏览器优先用能复用用户登录态的工具（推荐 ego-browser，见根目录 README）。没有这类工具时
  **要在结果里明说**，不能静默换成未登录的浏览器然后把"没查到"当成"没有"。
- "定时任务已开启"不等于"检索已成功"。每个渠道的覆盖、新候选、进度变化都要有证据。
- 每段在证据目录写 `execution-note.md`，记录开始、上下文就绪、派活、回收、记账、结束的真实时间。
- 没有实质变化就安静地写一行；有新候选、新回复、状态变化或需要用户处理的新阻塞时再通知。
