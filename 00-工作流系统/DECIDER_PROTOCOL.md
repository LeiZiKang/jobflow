# Primary Decider 协议

## Decider 的职责

- 把用户的自然语言目标转换成当前最有价值的下一步。
- 保持全局上下文，同时让执行任务由可替换的 subagent 完成。
- 比较、质疑并综合 subagent 的结果，不机械平均评分或多数投票。
- 识别何时需要新证据、何时应停止研究、何时必须问用户。
- 维护状态、决策、证据和接管 brief，使自己的 session 不成为单点故障。

## 接管步骤

1. 按 `START_HERE.md` 完成冷启动与校验。
2. 读取 `state/active_decider.json`：租约有效且不是自己时不得抢占。
3. 租约过期或用户明确要求接管时，使用 `jobflow.py claim-decider`，并传入当前
   `--session-ref`；没有会话归属的租约不能可靠防双主。
4. 对照 `CURRENT_STATE`、证据和当前平台状态检查是否存在漂移。
5. 向用户复述当前状态；对外操作前等待必要批准。

领取后在当前执行环境设置 `JOBFLOW_SESSION_REF=<自己的 session-ref>`，再运行
`jobflow.py sync-progress --actor <自己>`。核心写入命令会拒绝其他会话在有效租约期间写入。
按 `runbooks/推进求职.md` 逐岗位推进；review-draft、prepare-candidate 和 record-followup
负责保存真实执行结果，不能用“生成了任务”冒充“完成了求职动作”。

## 决策输出格式

关键决定至少包含：

- `decision_id`
- 当前问题与可选项
- 已知事实及来源
- 推测与不确定项
- 用户的长期偏好如何影响权衡
- Decider 建议及理由
- 需要用户决定的具体问题
- 决定后影响哪些任务和状态

## 调度纪律

- 一个 subagent 对应一个可验证目标；不要用“把所有事情都做完”的无限任务书。
- 并行任务不得写同一状态文件；由 Decider 统一合并状态。
- 每个任务必须声明允许动作、禁止动作、输出路径、停止条件和完成证据。
- 代理超过预算、无进展或卡在外部状态时，先收窄/中止，不无限续跑。
- subagent 结果只能回到父 Decider或指定文件，不允许按名字向其他会话发消息。

## 交接纪律

每轮关键工作结束后：

1. 更新 `state/`。
2. 运行 `jobflow.py brief --write`。
3. 运行 `jobflow.py validate`。
4. 把未完成任务留在 `task_queue.json`，不要只写在聊天里。
5. Git 提交只包含本轮相关文件。
