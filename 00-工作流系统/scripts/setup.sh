#!/bin/bash
# macOS bootstrap only. All regular checks and installation plans live in Python.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/jf-pyc}"
if [ "$(uname -s)" != Darwin ]; then
  echo "目前只支持 macOS / Currently only macOS is supported." >&2
  exit 1
fi
# /usr/bin/python3 can be an Apple stub on a new Mac. Never invoke that stub
# during --check: it can open an unsolicited system installation dialog.
PYTHON="$(command -v python3 || true)"
if [ -n "$PYTHON" ] && { [ "$PYTHON" != /usr/bin/python3 ] || /usr/bin/xcode-select -p >/dev/null 2>&1; }; then
  exec "$PYTHON" "$ROOT/00-工作流系统/bin/jobflow_setup.py" "$@"
fi
# Bootstrap exception: doctor cannot run yet. Do not duplicate its checks.
case "${1:-}" in
  --check)
    echo "doctor unavailable: python3 missing; install=xcode_clt. Other checks unknown."
    exit 1 ;;
  --yes)
    if [ "$#" -ne 2 ] || [ "$2" != xcode_clt ]; then
      echo "Python unavailable. Only --yes xcode_clt is possible after explicit consent." >&2
      exit 2
    fi ;;
  "") ;;
  *) echo "Usage: setup.sh [--check | --yes xcode_clt]; bootstrap needs Python first." >&2; exit 2 ;;
esac
cat <<'INFO'
安装 / Install: Apple Xcode Command Line Tools（非完整 Xcode），提供 git 和 python3。
官方来源 / Official: Apple 系统安装窗口 / https://developer.apple.com/download/all/
大小 / Size: 约 1–3 GB 下载，安装占数 GB；以 Apple 弹窗为准。
位置 / Destination: /Library/Developer/CommandLineTools
卸载 / Uninstall: 用户自行删除该目录；若需要管理员验证，由用户本人完成。
不修改 shell 配置、代理、网络或系统设置；不读取、输入、缓存密码。
No shell/proxy/network/system settings changes or password handling.
INFO
if [ "${1:-}" != --yes ]; then
  answer=""
  read -r -p "同意安装？ / Install? [y/N] " answer || true
  case "$answer" in y|Y|yes|YES) ;; *) echo "Skipped. / 已跳过。"; exit 0 ;; esac
fi
if ! /usr/bin/xcode-select --install; then
  echo "无法触发安装；请从上述 Apple 官方来源手动安装。 / Could not open installer; use the Apple source above." >&2
  exit 1
fi
echo "pending-user: 请在弹窗中完成安装，装好后告诉 Agent，再运行 setup.sh --check。"
echo "Finish the Apple dialog yourself; tell your agent when done, then rerun setup.sh --check."
