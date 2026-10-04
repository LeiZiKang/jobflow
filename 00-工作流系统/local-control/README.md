# Local Agent Control Plane

本目录是动态 Web Console 的本地 runtime。它不部署、不监听公网，也不直接修改
`state/*.json`。

## 进程

- `jobflowd.py`：`127.0.0.1:8791`，持有 SQLite runtime ledger 与只读 Agent workers。
- `console/`：`127.0.0.1:8788`，Next.js UI 和同源 API proxy。
  默认读取仓库根目录下的 `console/`；路径可用 `JOBFLOW_CONSOLE_DIR` 覆盖。
- `start.sh`：同时启动二者；关闭终端时只停止它自己创建的 controller。

SQLite 位于工作树之外的 `~/.local/state/jobflow/`（`JOBFLOW_RUNTIME_DIR` 可覆盖）。
**不要把它放回仓库**：它是运行产物不是仓库内容，而且里面有 jobflowd 的 bearer token，
放在树外就不存在被误提交的可能。路径解析写在 `00-工作流系统/bin/jobflow_paths.py`，
它保存 run、事件和 provider session
引用；删除后不会丢失 canonical 求职状态。访问 controller 需要启动时生成的 mode-600 bearer
token，浏览器端拿不到该 token。

启动器使用本地 lock，第二次双击只会打开已有控制台，不会删除其 token、杀进程或抢端口。
Search run 最长 180 秒，其他 run 最长 300 秒；关闭控制台时只终止本轮启动的 provider 子进程，
未完成 ensemble 记为 `interrupted`，不会自动重试。

## 当前可做

- 在网页查看投递、Application Case 和 HTML 报告。
- 查看 canonical Memory、revision、accepted/proposed 状态和来源。
- 启动 Codex 或 Claude 的只读 Primary run。
- 启动两个并行 Search runs，再由 Primary Evaluator 汇总。
- 查看结果、错误和运行状态。

## 当前不能做

- 修改 canonical state、批准候选、发送消息或执行最终投递。
- 跨 provider resume 隐藏 session。
- 自动处理登录、验证码或失效账号。
- 把 SQLite、provider transcript 或生成 HTML 当作业务真相。

长期记忆位于 `state/memory.json`，由 `python3 00-工作流系统/bin/memoryctl.py` 管理。`context_builder.py` 只把
accepted、未过期、与当前 scope 相关的记忆注入 Agent prompt；完整旧 session 不会自动进入。

Runtime adapters 强制 Codex `read-only` sandbox；Claude 只开放 Read/Glob/Grep/WebSearch/WebFetch。
如果 Claude CLI 已安装但账号失效，UI 会显示 `需要重新登录`，不会把“安装成功”冒充成可用。
Provider 子进程只继承路径、locale 和非 secret profile selector；不会继承 `OPENAI_API_KEY`、
`ANTHROPIC_API_KEY` 或 AWS secret 环境变量。本 MVP 面向本机已有的账号/配置，不接收网页输入的密钥。

控制台只通过 HTTP 与 jobflowd 通信，从不直接读写本仓库文件；两边唯一的契约是 jobflowd 的
端点形状，写在 `console/lib/types.ts`。改了 jobflowd 的返回结构，就要同步改那份类型。
