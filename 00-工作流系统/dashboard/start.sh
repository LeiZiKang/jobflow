#!/bin/bash
# 启动本地看板。默认读取本脚本所在的 jobflow 仓库，端口 8787。
# 用法: ./start.sh [端口]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DEFAULT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PORT="${1:-8787}"
REPO="${JOBFLOW_REPO:-$REPO_DEFAULT}"
BROWSER="${JOBFLOW_BROWSER:-chrome}"
exec python3 "$SCRIPT_DIR/server.py" --repo "$REPO" --port "$PORT" --open --browser "$BROWSER"
