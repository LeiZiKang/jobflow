#!/bin/bash
# 编译菜单栏 App 并安装到 ~/Applications/求职控制台.app。
# 仓库搬家后要重新运行一次，App 里记的是编译时的仓库路径。
# 构建中间产物放 $TMPDIR，不进工作树。
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SRC_DIR/../.." && pwd)"
DEST="${JOBFLOW_MENUBAR_APP:-$HOME/Applications/求职控制台.app}"
BUILD="$(mktemp -d)/求职控制台.app"
trap 'rm -rf "$(dirname "$BUILD")"' EXIT

mkdir -p "$BUILD/Contents/MacOS"
swiftc -O -target "$(uname -m)-apple-macosx13.0" \
  -o "$BUILD/Contents/MacOS/JobflowMenu" "$SRC_DIR/main.swift" "$SRC_DIR/MainWindow.swift"
cp "$SRC_DIR/Info.plist" "$BUILD/Contents/Info.plist"
# 把当前仓库位置写进 App，装到 ~/Applications 之后仍然知道去哪找 start.sh。
/usr/libexec/PlistBuddy -c "Add :JobflowRepo string $REPO_DIR" "$BUILD/Contents/Info.plist"

# 图标：画 1024 母版，缩出 iconset，打成 icns。
WORK="$(dirname "$BUILD")"
swift "$SRC_DIR/make-icon.swift" "$WORK/icon-1024.png"
ICONSET="$WORK/AppIcon.iconset"
mkdir -p "$ICONSET" "$BUILD/Contents/Resources"
for s in 16 32 128 256 512; do
  sips -z $s $s "$WORK/icon-1024.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) "$WORK/icon-1024.png" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$BUILD/Contents/Resources/AppIcon.icns"
codesign --force --sign - "$BUILD"

# 已在运行就先退出，避免旧进程继续托管控制台。
if pgrep -xq JobflowMenu; then
  osascript -e 'tell application id "local.jobflow.menubar" to quit' >/dev/null 2>&1 || pkill -x JobflowMenu || true
  for _ in $(seq 1 40); do pgrep -xq JobflowMenu || break; sleep 0.25; done
fi

mkdir -p "$(dirname "$DEST")"
rm -rf "$DEST"
cp -R "$BUILD" "$DEST"
echo "已安装：$DEST"
