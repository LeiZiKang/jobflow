# jobflow-dashboard

Jobflow 的本地看板。零依赖，只跑在 127.0.0.1。

> 这是兼容用的只读看板。需要 Agent 对话、并行检索、Runs 和统一报告入口时，使用根目录
> 的动态控制台启动脚本；动态控制台源码默认在仓库内 `console/`，本地
> controller 在 `00-工作流系统/local-control/`。

## 它是什么

**一个视图，不是第二份真相。**

数据全部实时读自当前仓库 `00-工作流系统/state/` 的 JSON 状态文件。
它永远不写状态——刷新页面看到的就是仓库当前的样子。

这样设计是因为求职仓库最容易犯的毛病是"同一件事在多个文档里写了不同版本"。
看板如果自己存一份数据，就又多了一个会漂移的副本。

## 跑起来

```bash
./00-工作流系统/dashboard/start.sh
```

或者在仓库根目录双击 `打开看板.command`。

默认显式使用 **Google Chrome**，不依赖 macOS 默认浏览器。需要临时使用系统默认浏览器时：

```bash
JOBFLOW_BROWSER=default ./00-工作流系统/dashboard/start.sh
```

只启动服务、不自动打开浏览器：

```bash
JOBFLOW_BROWSER=none ./00-工作流系统/dashboard/start.sh
```

自定义：

```bash
python3 server.py --repo /path/to/jobflow-workspace --port 8787 --open --browser chrome
```

## 页面

| 路径 | 内容 |
|---|---|
| `/` | 总览：已投递进度、面试中、今日投递、候选待决、投递表、下一步、定时任务、阻塞、当前 Decider |
| `/application/<id>` | 某个已进入面试的 application Case HTML |
| `/reports` | 所有 HTML 报告，按修改时间排序，点开直接看 |
| `/events` | append-only 操作记录最近 60 条 |
| `/document?f=...` | Case 内材料的只读打开入口，仅允许指定业务目录和文件类型 |
| `/api/state.json` | 原始状态 JSON，给别的工具用 |

## 安全

- 只绑 `127.0.0.1`，不对外。
- `/report` 只服务 `05-检索报告/` 目录下的 `.html`；目录穿越和其他后缀一律拒绝。
- `/application/<id>` 只能读取 state 中与该安全 application ID 精确绑定的
  `04-面试/公司/<id>/index.html`。
- `/document` 只允许 `02-策略`、`03-简历`、`04-面试`、`05-检索报告`、`06-证据`
  下的 HTML/Markdown/文本/PDF/常见图片；拒绝目录穿越、symlink 逃逸和其他后缀。
- 报告页带严格 CSP：禁止脚本、网络连接、表单与外部字体，避免未来生成的报告读取状态 API 或外传。
- 只读文件，不执行、不写入。

## 状态文件读不到时

看板会醒目报错，不会把损坏状态静默显示成 `0/15`。真相以 `jobflow.py validate` 为准。
