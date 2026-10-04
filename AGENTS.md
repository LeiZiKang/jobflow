# Agent 入口

开始任何任务前，先读 `00-工作流系统/START_HERE.md`。

先运行 `python3 00-工作流系统/bin/jobflow.py doctor`。如果 `00-工作流系统/state/current.json` 不存在，或 doctor 必需项不全（退出码 1），先读 `00-工作流系统/runbooks/首次使用.md`，分阶段带用户补齐准备。已有 state 时不重复 init。纯引擎开发使用临时 profile/runtime 验收，不要求开发者填写真实求职资料。

目前只支持 macOS。环境缺项按首次使用 runbook 逐项说明安装内容、用途、官方来源、大约大小、位置和卸载方法，用户明确同意后才运行 `./00-工作流系统/scripts/setup.sh --yes <item>`。拒绝就跳过，不反复劝；也可让用户运行 setup.sh 交互模式。新 Mac 无 git / python3 时，先征得同意触发 Apple 命令行工具安装，用户完成后再检测。管理员密码与系统弹窗由用户本人处理，不读、不输入、不缓存密码；不改 shell 配置、代理、网络或系统设置。Agent 的命令确认或沙箱限制是正常授权提示，受限时交还用户在终端运行。

For English-speaking users, follow [the English onboarding runbook](00-工作流系统/runbooks/onboarding.en.md) and [getting started](docs/getting-started.en.md). The Chinese and English onboarding runbooks are equivalent; the Chinese version takes precedence if they differ.

## 红线

1. 对外动作一律先要用户批准。包括投递、发消息、跟进、改平台资料、接受条款。已批准范围不得扩大。
2. 不谎报进度。区分计划、Agent 声称、仓库记录、平台回读。没有平台回读，不说已验证。
3. 凭据一律不碰。状态里只存 `secret://` 引用。遇到登录页、验证码、凭据输入，停下交还用户。
4. Git 只提交本任务相关文件。不要夹带用户已有改动。用户未要求时不要 commit。

## 浏览器

优先用能复用用户登录态的浏览器 skill，例如 `ego-browser`。本 session 没有时，必须先告诉用户，由用户决定。不得静默换用未登录浏览器后声称看过登录内容。

## 报告

给用户看的报告用 HTML。深色主题写进 `:root`，亮色只作为 `prefers-color-scheme: light` 降级。

岗位报告套 `05-检索报告/岗位档案/_模板-岗位档案.html`。如果模板还没生成，先按 runbook 说明报告阻塞，不临时发明另一套格式。

对外文字不要 AI 腔。短句，口语，不加“背景：”这类标签。

## 协作方式

不无条件同意用户。先给结论。提出方案时说明风险、未覆盖边界、为什么选它。建议标注置信度。

## 收尾

任务结束前：

- 更新结构化状态，或说明为什么不需要。
- 跑 `./00-工作流系统/scripts/check-all.sh`。
- 写清做完、没做完、卡点、下一步。
- 新记忆只能提 proposed，用 `00-工作流系统/bin/memoryctl.py`，不要直接写 accepted。
