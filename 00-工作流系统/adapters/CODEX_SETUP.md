# 用 Codex 接管本仓库

1. 在仓库根目录启动 Codex（应用或 `codex`）。第一次会问是否信任该目录，选信任。
2. Codex 会读根目录 `AGENTS.md`，它和 `CLAUDE.md` 是同一份约定，按 `00-工作流系统/START_HERE.md` 冷启动。
3. 还没初始化或 doctor 必需项未齐时，直接说"帮我初始化"，
   The agent follows [onboarding](../runbooks/onboarding.en.md) ([Chinese edition](../runbooks/首次使用.md)).
4. 运行完整检查确认环境正常：

```bash
./00-工作流系统/scripts/check-all.sh
```

## 沙箱注意事项

- Codex 默认的 workspace-write 沙箱通常不能联网，`npm install`、浏览器操作要在允许联网的模式下做，
  或者由你在终端里手动执行。
- profile 默认在 `~/.config/jobflow/profile`，`JOBFLOW_PROFILE_DIR` **只能指向仓库外**，例如仓库同级目录。被 gitignore 忽略也不能放在仓库内。
- runtime 默认在 `~/.local/state/jobflow`；`JOBFLOW_RUNTIME_DIR` 可以指向仓库内已被忽略的 `tmp/runtime/`。它含运行数据库、锁和 token，不要跟踪或发布。
- 确认目标目录在沙箱可写范围内；同级目录不可写时由用户配置可写范围，或选择仓库外可写临时目录，不绕过 profile 边界。

从仓库根目录执行，先确认这两个位置可写：

```bash
export JOBFLOW_PROFILE_DIR="$(dirname "$PWD")/jobflow-profile"
export JOBFLOW_RUNTIME_DIR="$PWD/tmp/runtime"
mkdir -p "$JOBFLOW_PROFILE_DIR" "$JOBFLOW_RUNTIME_DIR"
python3 00-工作流系统/bin/jobflow.py doctor
```

把同样的变量传给后续 Agent 和定时任务。

设置 `PYTHONPYCACHEPREFIX` 可以避免 `__pycache__` 落进仓库，`check-all.sh` 已默认这么做。

## 常用环境变量

| 变量 | 默认值 | 什么时候改 |
|---|---|---|
| `JOBFLOW_PROFILE_DIR` | `~/.config/jobflow/profile` | 多个人用同一台机器 / 测试 |
| `JOBFLOW_RUNTIME_DIR` | `~/.local/state/jobflow` | 沙箱不能写 home |
| `JOBFLOW_CONSOLE_DIR` | 仓库内 `console/` | 控制台放在别处 |
