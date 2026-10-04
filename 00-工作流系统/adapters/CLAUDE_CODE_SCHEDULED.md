# 用 Claude Code 桌面应用跑定时任务

通用规则先读 `SCHEDULED_COMMON.md`。这里只写 Claude Code 特有的配置。

## 配置步骤

1. 打开 Claude 桌面应用的 Code 标签页，新建一个 **Scheduled task**（定时任务），
   工作目录选本仓库根目录。
2. 触发时间：每天第一段的名义时间（例如 09:00）。应用会加几分钟随机延迟，这是正常的。
3. 权限模式：建议 Auto，并在 `.claude/settings.json` 里只放行本仓库需要的命令。
4. 任务 prompt 用下面这段（按需改时间和时区）：

```text
你是本仓库的定时任务执行者。先读 CLAUDE.md、00-工作流系统/START_HERE.md、
00-工作流系统/adapters/SCHEDULED_COMMON.md。
按顺序串行执行三段：job-inbound-sweep（09:00）、job-daily-position-search（09:30）、
job-daily-ontrace-check（10:30），时区 +08:00，名义时间用当天日期。
每段按 SCHEDULED_COMMON.md 的固定流程走；collector 用 Agent 工具派 subagent，
prompt 就是 job-envelope 的输出。最后回复三行：每段的结论、覆盖、新增或变化、阻塞。
```

5. 在 `00-工作流系统/state/recurring_jobs.json` 里把三个 job 的 `trigger` 写成这个任务
   （`jobflow.py set-job-runtime` 可以改），这样控制台才知道是谁在调度。

## 注意

- 只有应用开着才会触发；到点时应用没开，下次打开会补跑一次。`scheduled-bootstrap`
  会拦掉同一 slot 的重复执行。
- 主 session 是临时 Decider，负责写 state、记账、check-all、commit、释放租约；
  subagent 只读浏览，不写 canonical state、不 commit，结果以结构化文本返回。
- 不要同时在 Codex 里开同一组任务，两边会抢同一个租约。
