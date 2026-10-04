# START HERE — 新 Agent 接管入口

这份文件是 Claude、Codex 或其他 Agent 的统一入口。目标不是恢复上一段对话，
而是从仓库恢复求职工作的目标、规则、状态和下一步。

## 0. 最高目标

帮助用户找到符合现实能力、薪资、地点、WLB 和成长要求的工作。
系统建设、报告和自动化都只是服务这个目标的手段。

## 1. 固定启动顺序

**先判断是否准备完成**：运行 `python3 00-工作流系统/bin/jobflow.py doctor`。
如果 `00-工作流系统/state/current.json` 不存在，或 doctor 必需项不全（退出码 1），
先读 `00-工作流系统/runbooks/首次使用.md`，按阶段访谈并补齐。已有 state 时不要重复 init。
纯引擎开发使用临时 profile/runtime 做验收，无需开发者填写真实资料。
英文用户改读 [English onboarding](runbooks/onboarding.en.md)。

0. 想先看全貌：用浏览器打开 `00-工作流系统/系统架构.html`——分层、角色、派活方式、
   状态机、证据等级、审批门和当前实现进度都在里面。看完再按下面顺序走。
1. 完整读取 `00-工作流系统/CONSTITUTION.md`。
2. 完整读取 `00-工作流系统/DECIDER_BRIEF.md`。
   求职检索/推荐还须读取仓库外 `JOBFLOW_PROFILE_DIR/goals.json`（默认 `~/.config/jobflow/profile/goals.json`），先用 `bin/jobflow_screening.py --validate-profile` 校验。身份文件不用于检索；边界见 `PRIVATE_PROFILE.md`。缺配置报告阻塞，不拿虚构示例替用户目标。
3. 运行：

   ```bash
   python3 00-工作流系统/bin/jobflow.py validate
   python3 00-工作流系统/bin/memoryctl.py validate
   python3 00-工作流系统/bin/jobflow.py status
   python3 00-工作流系统/bin/jobflow.py next
   ```

   继续工程建设或提交前，运行完整检查：

   ```bash
   ./00-工作流系统/scripts/check-all.sh
   ```

4. 如果担任主 Decider，读 `00-工作流系统/DECIDER_PROTOCOL.md` **和**
   `00-工作流系统/SUBAGENT_PROTOCOL.md`——派活的信封由 Decider 写，所以 Decider 必须懂信封规格。
   派单不要手写：定时任务用 `jobflow.py job-envelope --job <id>`，一次性任务用
   `jobflow.py bootstrap-prompt --role executor --task-id <id>`。
   如果只是执行子任务，读 `00-工作流系统/SUBAGENT_PROTOCOL.md` 和任务指定的 runbook。
5. 只按任务需要读取岗位档案、简历或历史决策。不要从根目录开始无差别通读。
6. 开工前向用户简短复述：当前目标、当前状态、下一步和需要审批的事项。

已领取 Decider 租约后，设置 `JOBFLOW_SESSION_REF` 为自己的 session-ref，执行
`jobflow.py sync-progress --actor <自己>`，再看 `jobflow.py next` 与
`00-工作流系统/推进求职.html`。日常执行方式见 `runbooks/推进求职.md`。
已批准岗位独立准备；不要再等整批候选全部决定，不要把岗位批准当成最终文字/附件批准。

## 1.5 仓库布局

整个系统就是这一个仓库，clone 到哪里都能跑，不依赖固定路径。几样东西在工作树之外：

| 东西 | 默认位置 | 覆盖用的环境变量 |
|---|---|---|
| 个人目标、渠道配置、访谈与可选身份 | `~/.config/jobflow/profile/` | `JOBFLOW_PROFILE_DIR` |
| jobflowd 运行产物（SQLite / token / pid） | `~/.local/state/jobflow` | `JOBFLOW_RUNTIME_DIR` |

仓库内：

| 目录 | 是什么 |
|---|---|
| `00-工作流系统/` | 引擎：协议、CLI、runbook、本地服务、测试 |
| `console/` | Next.js 控制台（`JOBFLOW_CONSOLE_DIR` 可覆盖） |
| `00-工作流系统/state/` `events/` `evidence/` `approvals/` | 用户的结构化状态与证据，由 `jobflow.py init` 生成 |
| `01-现在在做/` … `05-检索报告/` | 用户的业务文档，由 `init` 生成 |

用户数据目录默认被 `.gitignore` 忽略，避免误推到公开仓库。用户如果把自己的副本放在
**私有**仓库里并希望版本化这些数据，可以删掉 `.gitignore` 里对应的块。

需要时再读，不用一上来就读：

- `runbooks/首次使用.md` —— state 不存在或 doctor 必需项未齐时，按它带用户完成准备
- `adapters/CODEX_SETUP.md` —— 用 Codex 接管前看这份

## 2. 权威顺序

出现冲突时按以下顺序处理：

1. 用户在当前对话中的明确指令。
2. `00-工作流系统/state/` 中通过校验的结构化状态。
3. `00-工作流系统/evidence/` 与平台现场的当前回读证据。
4. `02-策略/决策日志.md` 中仍然有效的决定。
5. `01-现在在做/`、`05-检索报告/` 等业务文档。
6. 历史 session；只能作为历史参考。

如果第 2、3 项互相矛盾，停止外部操作，先报告矛盾并修复状态。

## 3. 正常启动禁止事项

- 不读取 `~/.claude/projects/`、Codex rollout 或其他旧 session 来恢复上下文。
- 不因为历史 prompt 写过“投递”就声称已经投递。
- 不把旧 HANDOVER 的浏览器 task-space、session ID 当作仍然有效。
- 不重做已经有充分证据且没有时效变化的调查。
- 不擅自扩大用户批准的公司、岗位、平台或文字范围。
- 不读取、输出或写入密码、Cookie、token；状态中只能保存 `secret://` 引用。

只有在仓库证据缺失、发生矛盾且用户同意取证时，旧 session 才可作为异常取证材料。

## 4. 完成一次工作的最低要求

每次任务结束必须同时完成：

- 更新结构化状态或明确说明为什么不需要更新。
- 保存结果文件与证据引用。
- 发现值得跨 Agent 保留的新事实、偏好、决定或教训时，只能提出 proposed memory；未经评审
  不得自动写成 accepted memory。
- 区分“计划、已执行、已验证”。
- 写清尚未完成的部分、阻塞和下一步。
- 运行 `jobflow.py validate`。
- Git 只提交本任务相关文件，不夹带用户现有改动。

## 5. 冷启动成功标准

一个没有历史 session 的新 Agent，应当在十分钟内只靠本仓库准确回答：

- 用户要找什么工作，约束是什么？
- 已投多少，哪些真正验证成功？
- 当前最优先的下一项任务是什么？
- 哪些候选等待用户决定？
- 哪些操作可自主执行，哪些必须审批？
- 上一个 Agent 在哪里停下，如何避免重复操作？

回答不了时，不要回头读整段 session；先把缺失信息作为系统缺陷记录下来。

外部 Slack/CLI 启动器应使用 `jobflow.py bootstrap-prompt` 生成首条指令，详见
`00-工作流系统/adapters/README.md`。

动态本地控制台可双击根目录 `打开本地求职控制台.command`（或运行
`00-工作流系统/local-control/start.sh`）：它在本机启动 Next.js UI 与 `jobflowd`，
投递、Case、报告和只读 Agent runs 都可在网页中查看。`打开看板.command`
是零 Node 依赖的只读备用入口。定时任务定义在 `state/recurring_jobs.json`，
外部触发器（Claude Code 桌面定时任务、Codex automation、cron）只负责调用
`scheduled-bootstrap`，配置方法见 `adapters/`。
