#!/bin/bash
# Start the local Agent controller and dynamic Next.js console as one foreground stack.
set -euo pipefail

CONTROL_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$CONTROL_DIR/../.." && pwd)"
source "$ROOT/00-工作流系统/scripts/node-path.sh"
if ! jobflow_node_path; then
  echo "需要 Node >= 20.9；可以运行 00-工作流系统/scripts/setup.sh 逐项同意安装。" >&2
  exit 1
fi
# Read-only resolver hook for offline verification, before runtime writes.
if [ "${1:-}" = --resolve-node ]; then
  command -v node
  exit 0
fi
# runtime 放 SQLite run ledger、bearer token、pid、lock。它在工作树之外：
# 是运行产物不是仓库内容，而且 token 放在树外就不可能被误提交。
# 规则与 bin/jobflow_paths.py 一致，改一边就要改另一边。
RUNTIME_DIR="${JOBFLOW_RUNTIME_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/jobflow}"

# Web Console 源码默认在仓库内 console/；也可用 JOBFLOW_CONSOLE_DIR 覆盖。
WEB_DIR="${JOBFLOW_CONSOLE_DIR:-$ROOT/console}"
CONTROL_PORT="${JOBFLOWD_PORT:-8791}"
WEB_PORT="${JOBFLOW_WEB_PORT:-8788}"
BROWSER="${JOBFLOW_CONSOLE_BROWSER:-default}"
WEB_URL="http://127.0.0.1:$WEB_PORT/"
LOCK_DIR="$RUNTIME_DIR/console.lock"
PID_FILE="$RUNTIME_DIR/console.pid"
CONTROL_PID=""

# JOBFLOW_CONSOLE_BROWSER：default（系统默认浏览器）/ none（不打开）/ codex（Codex 应用内浏览器）/ 其他值当作 macOS 应用名
open_console() {
  case "$BROWSER" in
    none) : ;;
    default)
      if command -v open >/dev/null 2>&1; then open "$WEB_URL" || true
      elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$WEB_URL" >/dev/null 2>&1 || true
      fi ;;
    codex)
      DEEP_LINK="$(python3 -c 'import sys, urllib.parse; print("codex://browser?" + urllib.parse.urlencode({"url": sys.argv[1]}))' "$WEB_URL")"
      /usr/bin/open -b com.openai.codex "$DEEP_LINK" || open "$WEB_URL" ;;
    *) /usr/bin/open -a "$BROWSER" "$WEB_URL" || true ;;
  esac
}

mkdir -p "$RUNTIME_DIR"
if [ -d "$LOCK_DIR" ]; then
  EXISTING_PID="$(tr -d '\r\n' < "$PID_FILE" 2>/dev/null || true)"
  case "$EXISTING_PID" in
    ""|*[!0-9]*) EXISTING_PID="" ;;
  esac
  if [ -n "$EXISTING_PID" ] && kill -0 "$EXISTING_PID" 2>/dev/null; then
    echo "本地控制台已在运行：$WEB_URL"
    open_console
    exit 0
  fi
  if ! rmdir "$LOCK_DIR" 2>/dev/null; then
    echo "检测到非空的 stale lock：$LOCK_DIR；为避免误删，请人工检查。" >&2
    exit 1
  fi
  rm -f "$PID_FILE" "$RUNTIME_DIR/control-token"
fi
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "另一个控制台启动过程正在进行，请稍后重试。" >&2
  exit 1
fi
printf '%s\n' "$$" > "$PID_FILE"
rm -f "$RUNTIME_DIR/control-token"

PYTHONPYCACHEPREFIX="${JOBFLOW_PYCACHE:-${PYTHONPYCACHEPREFIX:-/tmp/jf-pyc}}" \
  python3 "$CONTROL_DIR/jobflowd.py" \
  --repo "$ROOT" \
  --port "$CONTROL_PORT" \
  --runtime-dir "$RUNTIME_DIR" \
  >"$RUNTIME_DIR/jobflowd.log" 2>&1 &
CONTROL_PID=$!

cleanup() {
  if [ -n "$CONTROL_PID" ] && kill -0 "$CONTROL_PID" 2>/dev/null; then
    kill "$CONTROL_PID" 2>/dev/null || true
    wait "$CONTROL_PID" 2>/dev/null || true
  fi
  rm -f "$RUNTIME_DIR/control-token" "$PID_FILE"
  rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 100); do
  if [ -s "$RUNTIME_DIR/control-token" ]; then
    break
  fi
  if ! kill -0 "$CONTROL_PID" 2>/dev/null; then
    echo "jobflowd 启动失败：" >&2
    tail -50 "$RUNTIME_DIR/jobflowd.log" >&2 || true
    exit 1
  fi
  sleep 0.1
done

if [ ! -s "$RUNTIME_DIR/control-token" ]; then
  echo "等待 jobflowd 超时。日志：$RUNTIME_DIR/jobflowd.log" >&2
  exit 1
fi

if [ ! -f "$WEB_DIR/package.json" ]; then
  echo "找不到 Web Console 源码：$WEB_DIR" >&2
  echo "用 JOBFLOW_CONSOLE_DIR 指定路径，或确认仓库内 console/ 已存在。" >&2
  exit 1
fi

if [ ! -x "$WEB_DIR/node_modules/.bin/next" ]; then
  echo "Web Console 依赖尚未安装。请运行：" >&2
  echo "  00-工作流系统/scripts/setup.sh（逐项同意安装 / per-item consent）" >&2
  exit 1
fi

JOBFLOWD_TOKEN="$(tr -d '\r\n' < "$RUNTIME_DIR/control-token")"
export JOBFLOWD_TOKEN
export JOBFLOWD_URL="http://127.0.0.1:$CONTROL_PORT"
export JOBFLOW_REPO="$ROOT"
export NEXT_TELEMETRY_DISABLED=1

(
  for _ in $(seq 1 120); do
    if curl -fsS "$WEB_URL" >/dev/null 2>&1; then
      open_console
      exit 0
    fi
    sleep 0.25
  done
) &

echo "本地控制台：http://127.0.0.1:$WEB_PORT/"
echo "Agent controller：http://127.0.0.1:$CONTROL_PORT/"
echo "关闭此窗口或按 Ctrl+C 会停止本轮服务；canonical repo 不受影响。"

cd "$WEB_DIR"
"$WEB_DIR/node_modules/.bin/next" dev --hostname 127.0.0.1 --port "$WEB_PORT"
