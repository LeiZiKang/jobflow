#!/usr/bin/env python3
"""Runtime 路径解析。

runtime 目录放的是 SQLite run ledger（WAL 模式，守护进程运行期间持续重写）、
bearer token、pid 和 lock。它**不放在仓库里**，两个理由：

1. 它是运行产物，不是仓库内容。仓库是求职工作的持久记忆，只该有纯文本。
2. 里面有 jobflowd 的 bearer token。放在工作树之外，就不存在被 `git add -f`
   误提交的可能——这条在仓库开源之后尤其重要。

默认落在 XDG state 目录（macOS 上即 `~/.local/state/jobflow`），不写死任何
个人路径，换机器、别人 clone 都能直接跑。

优先级：
  1. 环境变量 `JOBFLOW_RUNTIME_DIR`
  2. `$XDG_STATE_HOME/jobflow`
  3. `~/.local/state/jobflow`

同一条规则也写在 `local-control/start.sh`，两边必须一致。

runtime 外置这条是开源默认约束：仓库只保存可审计文本状态，运行锁和 token
永远放在工作树之外。
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "JOBFLOW_RUNTIME_DIR"
XDG_VAR = "XDG_STATE_HOME"
XDG_FALLBACK = Path("~/.local/state")
APP_NAME = "jobflow"


def default_runtime_dir() -> Path:
    """返回 runtime 目录。不创建它——由调用方决定什么时候落盘。"""
    override = os.environ.get(ENV_VAR)
    if override:
        return Path(override).expanduser().resolve()
    state_home = os.environ.get(XDG_VAR)
    base = Path(state_home).expanduser() if state_home else XDG_FALLBACK.expanduser()
    return (base / APP_NAME).resolve()
