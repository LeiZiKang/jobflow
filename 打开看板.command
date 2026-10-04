#!/bin/bash
# 双击打开求职看板。源码随本仓库保存，关掉这个窗口即停止。
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
STARTER="$REPO_DIR/00-工作流系统/dashboard/start.sh"
if [ ! -x "$STARTER" ]; then
  echo "找不到可执行的看板启动器：$STARTER" >&2
  echo "请确认仓库完整并运行：chmod +x '$STARTER'" >&2
  read -r -p "按回车关闭窗口…" _
  exit 1
fi
exec "$STARTER"
