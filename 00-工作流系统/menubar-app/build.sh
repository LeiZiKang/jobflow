#!/bin/bash
# 编译菜单栏 App 并安装到 ~/Applications/求职控制台.app。
# --dmg PATH 构建可分发的 universal DMG，不安装或退出本机 App。
# 构建中间产物放 $TMPDIR，不进工作树。
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SRC_DIR/../.." && pwd)"
DEST="${JOBFLOW_MENUBAR_APP:-$HOME/Applications/求职控制台.app}"
DMG=""
if [ "$#" -gt 0 ]; then
  if [ "$#" -ne 2 ] || [ "$1" != "--dmg" ] || [ -z "$2" ]; then
    echo "用法：build.sh [--dmg <输出路径>]" >&2
    exit 2
  fi
  DMG="$2"
  mkdir -p "$(dirname "$DMG")"
  DMG="$(cd "$(dirname "$DMG")" && pwd)/$(basename "$DMG")"
fi
BUILD="$(mktemp -d)/求职控制台.app"
trap 'rm -rf "$(dirname "$BUILD")"' EXIT

mkdir -p "$BUILD/Contents/MacOS"
if [ -n "$DMG" ]; then
  for arch in arm64 x86_64; do
    swiftc -O -target "$arch-apple-macosx13.0" \
      -o "$(dirname "$BUILD")/JobflowMenu-$arch" "$SRC_DIR/main.swift" "$SRC_DIR/MainWindow.swift"
  done
  lipo -create "$(dirname "$BUILD")/JobflowMenu-arm64" "$(dirname "$BUILD")/JobflowMenu-x86_64" \
    -output "$BUILD/Contents/MacOS/JobflowMenu"
else
  swiftc -O -target "$(uname -m)-apple-macosx13.0" \
    -o "$BUILD/Contents/MacOS/JobflowMenu" "$SRC_DIR/main.swift" "$SRC_DIR/MainWindow.swift"
fi
cp "$SRC_DIR/Info.plist" "$BUILD/Contents/Info.plist"
if [ -z "$DMG" ]; then
  # 开发者本机构建保留路径；DMG 首次启动由用户选择。
  /usr/libexec/PlistBuddy -c "Add :JobflowRepo string $REPO_DIR" "$BUILD/Contents/Info.plist"
fi

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

if [ -n "$DMG" ]; then
  STAGING="$WORK/dmg"
  mkdir -p "$STAGING"
  cp -R "$BUILD" "$STAGING/"
  ln -s /Applications "$STAGING/Applications"
  hdiutil create -volname Jobflow -srcfolder "$STAGING" -ov -format UDZO "$DMG"
  echo "已构建 DMG：$DMG"
  exit 0
fi

# 已在运行就先退出，避免旧进程继续托管控制台。
if pgrep -xq JobflowMenu; then
  osascript -e 'tell application id "local.jobflow.menubar" to quit' >/dev/null 2>&1 || pkill -x JobflowMenu || true
  for _ in $(seq 1 40); do pgrep -xq JobflowMenu || break; sleep 0.25; done
fi

mkdir -p "$(dirname "$DEST")"
rm -rf "$DEST"
cp -R "$BUILD" "$DEST"
echo "已安装：$DEST"
