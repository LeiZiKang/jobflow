#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
STARTER="$ROOT/00-工作流系统/local-control/start.sh"

if [ ! -x "$STARTER" ]; then
  echo "找不到可执行的本地控制台启动器：$STARTER" >&2
  read -r -p "按回车关闭窗口…" _
  exit 1
fi

exec "$STARTER"
