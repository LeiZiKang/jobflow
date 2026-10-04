# Agent runtime adapters

本目录定义 Claude、Codex、Slack bot 等运行时如何接入同一个 repo-first 工作流。

## 边界

- 本仓库保存业务目标、任务、决定、证据和接管协议。
- Agent runtime 只负责启动模型、提供工具和返回结果。
- Slack SQLite 只保存 Slack conversation 到 backend/session 的临时映射，不保存求职业务真相。
- 切换 backend 时可以丢弃旧 session 映射，但不能丢弃 repo 中的 task/approval/state。

## 新后端启动

不要向新后端注入旧对话全文。生成一个有界 bootstrap prompt：

```bash
python3 00-工作流系统/bin/jobflow.py bootstrap-prompt --role decider
```

执行特定任务：

```bash
python3 00-工作流系统/bin/jobflow.py bootstrap-prompt \
  --role executor \
  --task-id task-audit-overdue-followups
```

把输出作为新 Claude/Codex 会话的首条任务即可。

## Slack 集成要求

1. `切换claude` / `切换codex` 只切运行时，不改变业务 task 状态。
2. 新 backend 的第一轮必须使用上面的 bootstrap prompt。
3. Slack 消息与 repo task ID 绑定；没有 task ID 的副作用请求只允许起草，不执行。
4. Slack 一次性审批码应同时绑定 repo `approval_id`，并在执行后调用 `consume-approval`。
5. backend 失效时在 repo 记录 blocker/event，再切换后端；不要通过读取旧 session 恢复业务状态。

Slack 桥接不在本仓库内；接入任何 bot 前，先确认它满足上面五条。

定时任务的配置见 `SCHEDULED_COMMON.md`、`CLAUDE_CODE_SCHEDULED.md`、`CODEX_SCHEDULED.md`。

## 首次使用与个人配置

Run `python3 00-工作流系统/bin/jobflow.py doctor` first. If required checks fail, follow
[onboarding](../runbooks/onboarding.en.md) ([Chinese edition](../runbooks/首次使用.md)).
所有后端与定时触发器须继承同一 `JOBFLOW_PROFILE_DIR` 和 `JOBFLOW_RUNTIME_DIR`。
渠道设置先从 `00-工作流系统/config/search_channels.json`、`00-工作流系统/config/inbound_sources.json` 复制到个人目录后编辑，
不要修改仓库模板。统一用 `jobflow.py config search_channels.json` /
`jobflow.py config inbound_sources.json` 读取；个人覆盖优先，损坏时停止并修复，不回退。
