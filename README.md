**中文** | [English](README.en.md)

# jobflow

用 AI Agent 帮你找工作的 repo-first 工作流。

求职目标、进度、证据和审批都有明确的存放位置。换 Agent 或开新会话时，从文件接着做。
计划、Agent 声称、仓库记录、平台回读分开记录。投递、发消息、改平台资料等对外动作先由你批准。

## 核心设计

- 仓库保存状态、任务、证据和报告；个人目标与渠道配置放在仓库外。
- 一个主 Decider 负责判断和派活，执行 Agent 按任务信封工作。
- 硬线、评分权重、证据覆盖率共同决定推荐；分数不是录用概率。
- 外部调度器只触发任务，任务范围由仓库定义。
- 本地控制台展示候选、投递、报告和 Agent runs；CLI 可独立使用。

## 开始前准备

先读 [新手指南](docs/新手指南.md)，提前想好目标、权重、硬线和渠道。

- macOS 或 Linux，Git，Python 3.9+。引擎只用标准库。
- 能打开本地仓库的 Claude Code、Codex 或其他 Agent。
- 至少一份简历，放进 `03-简历/`；PDF、Markdown、JSON、DOCX、TXT 均可。
- 推荐 [ego lite](https://lite.ego.app/) 和 Agent 侧的 `ego-browser` skill，以复用你自己的浏览器登录态。目前官方安装脚本只支持 macOS；不装时只能读未登录公开页面。
- 选好 BOSS直聘、猎聘、LinkedIn、Indeed、前程无忧、公司官网/ATS 等渠道，由你自己登录。Agent 不碰账号密码或验证码。
- 可选：Node 20.9+ 用于控制台；Xcode Command Line Tools 用于 macOS 菜单栏 App；作品集、已有机会、identity.json。

## 快速开始

```bash
git clone <repo-url>
cd jobflow
```

用 Agent 打开仓库，说“帮我初始化”。它会按 [首次使用访谈](00-工作流系统/runbooks/首次使用.md)
每次问 2–4 个问题，复述并得到确认后才写文件。

也可以手动开始：

```bash
python3 00-工作流系统/bin/jobflow.py init
python3 00-工作流系统/bin/jobflow.py doctor
```

首次 doctor 返回 1 是正常的：还要定制个人 goals、放入简历、确认渠道。
`config/search_channels.json` 和 `config/inbound_sources.json` 是默认模板；确认范围后复制到
`JOBFLOW_PROFILE_DIR`（默认 `~/.config/jobflow/profile/`）再编辑，别把个人偏好写进跟踪文件。
步骤见新手指南。读取时个人配置优先，无覆盖时才用模板：

```bash
python3 00-工作流系统/bin/jobflow.py config search_channels.json
python3 00-工作流系统/bin/jobflow.py config inbound_sources.json
python3 00-工作流系统/bin/jobflow.py doctor --json
./00-工作流系统/scripts/check-all.sh
```

**准备好了**：doctor 必需项全部 ok，且 check-all 通过。doctor 不输出 goals / identity 正文。
Node、控制台依赖、ego-browser、identity.json 缺失只会 warn，不影响 doctor 退出码。
平台登录与实际可访问性仍需核实。第一步建议手动跑一次只读岗位检索。

想先看虚构演示：

```bash
python3 00-工作流系统/bin/jobflow.py init --demo
# 看完并确认重置后
python3 00-工作流系统/bin/jobflow.py init --force
```

重置前会备份旧核心状态到 `00-工作流系统/.init-backup-*`。演示清单内的业务文件会被移除，
不要直接在演示文件里填真实数据。个人目录的配置保留。

## 打开控制台

```bash
cd console && npm install
cd ..
./00-工作流系统/local-control/start.sh
```

打开 `http://127.0.0.1:8788`。macOS 也可双击 `打开本地求职控制台.command`。
请用启动脚本，不要直接 `npm run dev`；脚本负责连接本地服务。

零 Node 的只读看板：`./打开看板.command`。
macOS 菜单栏 App：`./00-工作流系统/menubar-app/build.sh`。

## 日常怎么用

| 步骤 | 你与 Agent 怎么配合 | Runbook |
|---|---|---|
| 检索 | 确认只读范围，按所选渠道查 JD 并保存来源 | [每日岗位检索](00-工作流系统/runbooks/每日岗位检索.md) |
| 看报告 | 读匹配度、风险、未知项，决定具体岗位是否投递 | [岗位报告](00-工作流系统/runbooks/岗位报告撰写.md)、[目标评分](00-工作流系统/runbooks/目标评分与推荐.md) |
| 准备与投递 | 核对事实，批准具体文字和附件，最终确认后才执行 | [投递](00-工作流系统/runbooks/投递.md) |
| 跟进 | 只读回读平台状态，更新证据；发送另批 | [跟进](00-工作流系统/runbooks/跟进.md) |
| 面试与复盘 | 提供材料，核实事实，整理问题与复盘 | [面试准备](00-工作流系统/runbooks/面试准备.md)、[推进求职](00-工作流系统/runbooks/推进求职.md) |

Agent 可整理材料、校验和生成本地报告。对外动作必须先批准，已批准范围不得扩大。

## 定时任务

外部调度器负责按时启动，具体任务范围仍由仓库信封决定。先手动跑通，再配置定时任务。

- [通用规则](00-工作流系统/adapters/SCHEDULED_COMMON.md)
- [Claude Code](00-工作流系统/adapters/CLAUDE_CODE_SCHEDULED.md)
- [Codex](00-工作流系统/adapters/CODEX_SCHEDULED.md)

触发器须使用同一 `JOBFLOW_PROFILE_DIR`；搜索与邀约来源从个人覆盖配置读取。

## 数据与目录

| 路径 | 用途 |
|---|---|
| `JOBFLOW_PROFILE_DIR`（默认 `~/.config/jobflow/profile/`） | goals、个人渠道配置、onboarding 访谈、可选 identity |
| `JOBFLOW_RUNTIME_DIR`（默认 `~/.local/state/jobflow`） | 本地服务的 SQLite、token、pid |
| `00-工作流系统/` | 引擎、协议、CLI、runbook、测试、本地服务 |
| `00-工作流系统/state/`、`evidence/`、`approvals/` | 初始化后的状态、证据、审批 |
| `console/` | Next.js 本地控制台 |
| `01-现在在做/` | 当前投递、候选与状态视图 |
| `02-策略/` | 策略与复盘 |
| `03-简历/` | 简历材料 |
| `04-面试/` | 面试准备和 Case |
| `05-检索报告/` | 岗位报告、目录和检索结果 |

个人目录必须在仓库外。仓库内的用户数据默认被 `.gitignore` 忽略。
若想版本化自己的求职数据，只在**私有仓库**里调整忽略规则；不要提交到公开仓库。

## 安全边界

- Agent 不碰密码、验证码、Cookie、token；遇到登录或验证停下交还给你。
- 状态中只保存 `secret://` 凭据引用，不保存真实秘密。
- 检索授权不包含投递、发送、接受条款或修改平台资料。
- 遵守各平台规则；工具可用不代表平台允许所有自动化操作。

## 常见问题

**init 完为什么还没准备好？** init 只搭工作区并复制 goals 示例。运行 doctor，补齐目标定制、简历和个人渠道配置。

**缺 ego-browser 或 Node 怎么办？** 它们是建议项。浏览器限制要由 Agent 说明；Node 只影响控制台。identity.json 也可暂不提供。

**check-all 报错怎么办？** 先确认 init 已完成，再处理第一个报错。未装控制台依赖时会告警并跳过 TypeScript 检查。

更多说明见 [新手指南](docs/新手指南.md)。

## 参与开发

```bash
./00-工作流系统/scripts/install-hooks.sh
```

- `check-all.sh`：校验、生成视图、单元测试；先 init，可用虚构 demo。安装控制台依赖后还会检查 TypeScript。
- `check-publishable.sh`：检查待发布文件与历史中的敏感内容。私人关键词放在仓库外的 `~/.config/jobflow/publish-denylist.txt`，或用 `JOBFLOW_PUBLISH_DENYLIST` 指定。
- 测试使用临时 `JOBFLOW_PROFILE_DIR` 和 `JOBFLOW_RUNTIME_DIR`，不要接触真实个人配置。

## 许可证

MIT，见 [LICENSE](LICENSE)。
