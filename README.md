# jobflow

用 AI Agent 帮你找工作的 repo-first 工作流系统。

求职过程容易散在几十个平台、聊天记录、浏览器标签和本地文件里。Agent 也容易谎报进度，或者把“准备投递”说成“已经投递”。jobflow 把仓库作为唯一记忆：所有进度、证据、审批、任务都落在仓库里；所有对外动作都必须先由你批准；每条结论都要区分证据等级。

目标很简单：clone 后用 Claude Code 或 Codex 打开仓库，说一句“帮我初始化”，就能开始。

## 核心设计

- **仓库即记忆**：状态、任务、证据、审批、报告都在仓库里。旧 session 不是权威。
- **宪章与审批门**：投递、发消息、改平台资料、接受条款等外部动作，一律先问你。
- **证据等级**：计划、Agent 声称、仓库记录、平台回读分开写。已验证必须有强证据。
- **Decider + subagent 信封**：一个主 Decider 负责判断和派活；执行层只按任务信封做事。
- **定时任务**：外部调度器只触发任务，任务范围由仓库信封限制。
- **本地控制台**：在浏览器里看总览、候选、投递、报告和 Agent runs。

## 前置条件

- macOS 或 Linux。
- Python 3.9+。引擎只用标准库。
- Node 20.9+。控制台需要。
- Claude Code 或 Codex。
- 可选：`ego-browser` / ego lite 这类能复用你自己浏览器登录态的浏览器 skill。没有它，Agent 只能用未登录浏览器，大部分招聘平台看不到内容。
- 可选：macOS 菜单栏 App 需要 Xcode Command Line Tools。

## 快速开始

```bash
git clone <repo-url>
cd jobflow
```

然后用 Claude Code 或 Codex 打开这个仓库，对 Agent 说：

```text
帮我初始化
```

Agent 会按 `00-工作流系统/runbooks/首次使用.md` 带你走。

也可以手动执行：

```bash
python3 00-工作流系统/bin/jobflow.py init
```

想先看效果：

```bash
python3 00-工作流系统/bin/jobflow.py init --demo
```

看完演示数据后，想重置为空工作区：

```bash
python3 00-工作流系统/bin/jobflow.py init --force
```

## 打开控制台

第一次用控制台先装依赖：

```bash
cd console
npm install
cd ..
```

启动方式任选一个（`.command` 是 macOS 双击启动器，Linux 用第二种）：

```bash
./打开本地求职控制台.command
```

或：

```bash
./00-工作流系统/local-control/start.sh
```

浏览器打开：

```text
http://127.0.0.1:8788
```

零 Node 的只读看板：

```bash
./打开看板.command
```

菜单栏 App：

```bash
./00-工作流系统/menubar-app/build.sh
```

## 日常怎么用

| 步骤 | 你做什么 | Agent 能做什么 | 参考 runbook |
|---|---|---|---|
| 检索岗位 | 授权只读检索范围 | 查 BOSS直聘、猎聘、LinkedIn、公司官网等，只保存来源 | `00-工作流系统/runbooks/每日岗位检索.md` |
| 读岗位报告 | 看报告和风险 | 整理 JD、公司信息、匹配度、未知项 | `00-工作流系统/runbooks/岗位报告撰写.md` |
| 决定投不投 | 明确批准或拒绝具体岗位 | 记录候选决定，不自动投递 | `00-工作流系统/runbooks/目标评分与推荐.md` |
| 准备材料 | 核对事实 | 准备简历版本、消息草稿、附件清单 | `00-工作流系统/runbooks/投递.md` |
| 批准文字 | 批准具体文字和附件 | 生成审批记录，绑定内容哈希 | `00-工作流系统/runbooks/投递.md` |
| 投递 | 最终确认后才执行 | 只在批准范围内操作，遇登录/验证码停下 | `00-工作流系统/runbooks/投递.md` |
| 每日核实进度 | 处理需要你登录或判断的地方 | 只读回读平台状态，更新证据 | `00-工作流系统/runbooks/跟进.md` |
| 面试准备 | 给出面试时间、岗位和材料 | 整理口径、问题、风险点和复盘 | `00-工作流系统/runbooks/面试准备.md` |
| 复盘 | 确认事实和结论 | 写报告，区分事实、推断、未知 | `00-工作流系统/runbooks/推进求职.md` |

默认情况下，Agent 可以自己做只读检索、整理、校验、生成本地报告。凡是会对外产生影响的动作，都必须你先批准。

## 定时任务

定时任务不是“让 Agent 自由发挥”。外部调度器只负责按时启动，具体任务范围仍由仓库信封决定。

- 通用规则：`00-工作流系统/adapters/SCHEDULED_COMMON.md`
- Claude Code：`00-工作流系统/adapters/CLAUDE_CODE_SCHEDULED.md`
- Codex：`00-工作流系统/adapters/CODEX_SCHEDULED.md`

## 你的数据在哪

个人目标默认在仓库外：

```text
~/.config/jobflow/profile/
```

仓库内的 `state/`、报告、简历、证据等，默认被 `.gitignore` 忽略，`git status` 里看不到它们。

强烈提醒：如果想用 git 版本化自己的求职数据，请在**私有**仓库里做，删掉 `.gitignore` 的“个人数据”块。不要 fork 到公开仓库后提交个人数据。

## 目录结构

| 路径 | 用途 |
|---|---|
| `00-工作流系统/` | 引擎、协议、runbook、测试、本地服务 |
| `00-工作流系统/bin/` | CLI 工具 |
| `00-工作流系统/runbooks/` | Agent 执行流程 |
| `00-工作流系统/state/` | 结构化状态，初始化后生成 |
| `00-工作流系统/evidence/` | 证据 manifest 和材料 |
| `00-工作流系统/approvals/` | 审批记录 |
| `console/` | Next.js 本地控制台 |
| `01-现在在做/` | 当前投递、候选、状态视图 |
| `02-策略/` | 用户自己的策略和复盘 |
| `03-简历/` | 简历材料 |
| `04-面试/` | 面试准备和 Case |
| `05-检索报告/` | 岗位报告、岗位目录、检索结果 |

## 安全边界

- Agent 不碰凭据、验证码、Cookie、token。
- 遇到登录页、验证码、凭据输入，Agent 停下交还给你。
- 对外动作一律先批准。已批准范围不得扩大。
- 平台自动化只做只读浏览。请遵守各平台用户协议，风险自负。
- 状态里只允许保存 `secret://` 形式的凭据引用，不保存真实秘密。

## 常见问题

**Agent 说缺少 ego-browser 怎么办？**  
这表示当前 session 没有可复用你登录态的浏览器 skill。你可以安装或启用它，也可以让 Agent 只做未登录公开页面的只读检索。不要让 Agent 静默改用未登录浏览器后声称看过登录内容。

**`check-all.sh` 报错怎么办？**  
新 clone 先跑初始化：

```bash
python3 00-工作流系统/bin/jobflow.py init
```

然后再跑：

```bash
./00-工作流系统/scripts/check-all.sh
```

**控制台显示“没读到”怎么办？**  
通常是 `jobflowd` 没启动，或控制台没有拿到启动脚本注入的 token。用 `./打开本地求职控制台.command` 或 `./00-工作流系统/local-control/start.sh` 启动，不要直接 `npm run dev`。

## 参与开发

改引擎代码前先装 git hook，它会在每次提交前跑发布检查和完整测试：

```bash
./00-工作流系统/scripts/install-hooks.sh
```

- `00-工作流系统/scripts/check-all.sh`：校验、生成视图、全部单元测试。需要先 `init`（建议 `init --demo`）。
- `00-工作流系统/scripts/check-publishable.sh`：扫描将要提交的文件里有没有手机号、邮箱、个人路径、密钥、二进制和用户数据目录。
  自己的名字、投过的公司这类私人关键词写在仓库外的 `~/.config/jobflow/publish-denylist.txt`（每行一个正则），它也会一起检查。

## 许可证

MIT，见 `LICENSE`。
