# 用 Codex 跑定时任务

通用规则先读 `SCHEDULED_COMMON.md`。这里只写 Codex 特有的配置。

## 配置步骤

1. 在 Codex 应用里打开本仓库，创建一个每天触发的 automation / heartbeat，
   时间设为第一段的名义时间（例如 09:00）。
2. 任务 prompt：

```text
你是本仓库的定时任务执行者。按 AGENTS.md 和 00-工作流系统/START_HERE.md 冷启动，
再读 00-工作流系统/adapters/SCHEDULED_COMMON.md。
按顺序串行执行三段：job-inbound-sweep（09:00）、job-daily-position-search（09:30）、
job-daily-ontrace-check（10:30），时区 +08:00，名义时间用当天日期，只处理当天，不逐日补跑历史。
领租约用 claim-decider --agent codex --backend codex；拿到租约后再查一次 scheduled-bootstrap，
防止等待期间同一 slot 已被别的 session 完成。
```

3. 把 automation 的 ID 写进 `state/recurring_jobs.json` 对应 job 的 `trigger.external_id`。

## 注意

- 只在本仓库工作，以仓库为业务上下文，不读旧 session。
- Git 只提交本段独有改动；遇到无法安全分离的既有改动时保留文件并说明，不整份夹带。
- 不要同时在 Claude Code 里开同一组任务。
- 用命令行代替应用也可以：`codex exec -C <仓库路径> "<上面的 prompt>"`，配合 cron / launchd。
