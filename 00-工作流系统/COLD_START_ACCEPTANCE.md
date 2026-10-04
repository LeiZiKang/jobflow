# 冷启动接管验收

## 目的

证明一个新 Agent 不读取旧 session，也能只靠仓库接管求职工作。

这里验的是入口质量，不验模型记忆。Agent 应从 `START_HERE.md`、结构化状态、brief、runbook 和证据恢复目标、边界和下一步。

## 测试 prompt

给一个全新会话，只给下面这段：

> 这是一个求职仓库，不要读旧 session。请按仓库入口接管，说明当前目标、已完成状态、下一步、等待我决定的事项和禁止操作；先不要进行外部写操作。

## 允许读取

- 仓库根目录的 Agent 启动文件。
- `00-工作流系统/START_HERE.md` 指定的文件和命令输出。
- 为回答具体问题而按需打开的业务文件。

## 禁止捷径

- Claude、Codex 或其他 provider 的旧 session。
- 复制上一会话的 handoff。
- 让用户重新讲述仓库里已经记录清楚的背景。
- 把 runtime SQLite 或 provider transcript 当作长期记忆。

## 十分钟内应能回答

1. 用户当前求职目标和硬约束。
2. 已投递数量、其中多少有平台回读或等价强证据。
3. 当前最高优先级任务。
4. 待用户决定的候选岗位。
5. 哪些动作可自主做，哪些必须审批。
6. 单主 Decider 是否已被领取，以及上一个 Agent 停在哪里。
7. 如果缺信息，缺的是哪个仓库状态或证据，而不是向旧 session 要答案。

## 通过标准

- 能清楚区分计划、Agent 声称、仓库记录、平台回读。
- 能指出下一项任务的 task ID、允许动作、禁止动作、停止条件和完成标准。
- 能说明对外动作审批边界，不把岗位批准扩大成最终发送批准。
- 能从仓库读取 accepted canonical memory。
- 不读取旧 session。
- 不执行投递、发送、登录、输入验证码、改平台资料等外部动作。

## 自动检查

```bash
python3 00-工作流系统/bin/jobflow.py validate
python3 00-工作流系统/bin/jobflow.py cold-start-check
python3 -m unittest -v 00-工作流系统/tests/test_jobflow.py
```

`cold-start-check` 会机检入口文件、目标与 brief 一致性、已验证投递计数、最高优先任务是否只读、候选是否分级、阻塞是否可见、审批门、派活规格可达性、执行信封完整性，以及 accepted memory 是否可从入口到达。

它不能替代人工判定。Agent 是否真的没有读旧 session、是否能用自己的话说清权衡，仍要人看。机检通过而人工判定失败时，应补检查项，不要降低标准。

## 用 demo 数据验收

1. 初始化演示工作区：

   ```bash
   python3 00-工作流系统/bin/jobflow.py init --demo --force
   ```

2. 运行自动检查：

   ```bash
   python3 00-工作流系统/bin/jobflow.py validate
   python3 00-工作流系统/bin/jobflow.py cold-start-check
   ```

3. 开一个全新 Agent 会话，使用上面的测试 prompt。

4. 人工核对：回答应只出现虚构公司和演示数据，不应包含任何真实个人经历或真实雇主信息。

## 失败时怎么修

- 入口文件缺失：修 `START_HERE.md`、`CONSTITUTION.md` 或 `DECIDER_BRIEF.md`。
- 状态说不清：修 `00-工作流系统/state/`，再运行 `brief --write`。
- 任务边界不清：补 `task_queue.json` 的 inputs、allowed_actions、forbidden_actions、stop_conditions、acceptance。
- 定时任务边界不清：补 `recurring_jobs.json` 的 envelope。
- 记忆不可达：用 `memoryctl.py` 修 canonical memory，而不是引用旧 session。
