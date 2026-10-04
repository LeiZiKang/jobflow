# 用 Codex 接管本仓库

1. 在仓库根目录启动 Codex（应用或 `codex`）。第一次会问是否信任该目录，选信任。
2. Codex 会读根目录 `AGENTS.md`，它和 `CLAUDE.md` 是同一份约定，按 `00-工作流系统/START_HERE.md` 冷启动。
3. 还没初始化（没有 `00-工作流系统/state/current.json`）时，直接说"帮我初始化"，
   Agent 会按 `runbooks/首次使用.md` 带你走一遍。
4. 运行完整检查确认环境正常：

```bash
./00-工作流系统/scripts/check-all.sh
```

## 沙箱注意事项

- Codex 默认的 workspace-write 沙箱通常不能联网，`npm install`、浏览器操作要在允许联网的模式下做，
  或者由你在终端里手动执行。
- jobflowd 的运行产物写在 `~/.local/state/jobflow`（`JOBFLOW_RUNTIME_DIR` 可改），
  个人目标在 `~/.config/jobflow/profile`（`JOBFLOW_PROFILE_DIR` 可改）。这两个目录都在仓库外，
  沙箱需要能写它们，或者把环境变量指到工作区里被 `.gitignore` 忽略的位置。
- 设置 `PYTHONPYCACHEPREFIX` 可以避免 `__pycache__` 落进仓库，`check-all.sh` 已默认这么做。

## 常用环境变量

| 变量 | 默认值 | 什么时候改 |
|---|---|---|
| `JOBFLOW_PROFILE_DIR` | `~/.config/jobflow/profile` | 多个人用同一台机器 / 测试 |
| `JOBFLOW_RUNTIME_DIR` | `~/.local/state/jobflow` | 沙箱不能写 home |
| `JOBFLOW_CONSOLE_DIR` | 仓库内 `console/` | 控制台放在别处 |
