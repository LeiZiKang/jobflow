#!/bin/bash
# 编译菜单栏 App 并安装到 ~/Applications/求职控制台.app。
# --dmg PATH 构建可分发的 universal DMG，不安装或退出本机 App。
# JOBFLOW_SIGN_IDENTITY 可选 Developer ID；--notarize 使用 JOBFLOW_NOTARY_PROFILE。
# JOBFLOW_NOTARY_KEYCHAIN 可选，指定该 profile 所在的非默认钥匙串。
# 构建中间产物放 $TMPDIR，不进工作树。
set +x # 不回显调用参数；脚本不读取、接收或输出任何凭据内容。
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SRC_DIR/../.." && pwd)"
DEST="${JOBFLOW_MENUBAR_APP:-$HOME/Applications/求职控制台.app}"
DMG=""
NOTARIZE=0
SIGN_IDENTITY="${JOBFLOW_SIGN_IDENTITY:-}"
NOTARY_PROFILE="${JOBFLOW_NOTARY_PROFILE:-}"
NOTARY_KEYCHAIN="${JOBFLOW_NOTARY_KEYCHAIN:-}"
die() { echo "错误：$*" >&2; exit 1; }
usage() { echo "用法：build.sh [--dmg <输出路径> [--notarize]]" >&2; exit 2; }
while [ "$#" -gt 0 ]; do
  case "$1" in
    --dmg)
      [ "$#" -ge 2 ] && [ -n "$2" ] && [[ "$2" != --* ]] && [ -z "$DMG" ] || usage
      DMG="$2"; shift 2 ;;
    --notarize)
      [ "$NOTARIZE" -eq 0 ] || usage
      NOTARIZE=1; shift ;;
    *) usage ;;
  esac
done
if [ "$NOTARIZE" -eq 1 ]; then
  [ -n "$DMG" ] || die "--notarize 必须与 --dmg 一起使用。"
  [ -n "$NOTARY_PROFILE" ] || die "--notarize 需要 JOBFLOW_NOTARY_PROFILE（钥匙串 profile 名）。"
  [ -n "$SIGN_IDENTITY" ] || die "--notarize 需要 JOBFLOW_SIGN_IDENTITY；ad-hoc 签名不能公证。"
fi
if [ -n "$SIGN_IDENTITY" ]; then
  [[ "$SIGN_IDENTITY" == "Developer ID Application: "* ]] || \
    die "JOBFLOW_SIGN_IDENTITY 必须是完整的 Developer ID Application 证书名称。"
fi
if [ -n "$DMG" ]; then
  mkdir -p "$(dirname "$DMG")"
  DMG="$(cd "$(dirname "$DMG")" && pwd)/$(basename "$DMG")"
fi
BUILD="$(mktemp -d)/求职控制台.app"
trap 'rm -rf "$(dirname "$BUILD")"' EXIT

# 仅接受服务明确返回 Accepted；退出码 0 并不等于审核通过。
# 不展示服务原始响应或自动下载日志，避免输出账户信息。
notarize() {
  local artifact="$1" result="$WORK/notary-result.json" rc=0 status submission
  local -a notary_args=(--keychain-profile "$NOTARY_PROFILE")
  if [ -n "$NOTARY_KEYCHAIN" ]; then
    notary_args+=(--keychain "$NOTARY_KEYCHAIN")
  fi
  echo "提交公证：$(basename "$artifact")"
  xcrun notarytool submit "$artifact" "${notary_args[@]}" --wait \
    --output-format json >"$result" 2>/dev/null || rc=$?
  status=$(plutil -extract status raw -o - "$result" 2>/dev/null) || status=""
  submission=$(plutil -extract id raw -o - "$result" 2>/dev/null) || submission=""
  if [ "$rc" -ne 0 ] || [ "$status" != Accepted ]; then
    echo "错误：公证未获 Accepted；检查 profile、网络或审核结果。获取日志命令：" >&2
    if [[ ! "$submission" =~ ^[[:xdigit:]]{8}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{12}$ ]]; then
      submission="<SUBMISSION_ID>"
      echo "未取得提交 ID；可先查询历史（如提交未创建，则不会有日志）：" >&2
      printf '  xcrun notarytool history --keychain-profile %q' "$NOTARY_PROFILE" >&2
      if [ -n "$NOTARY_KEYCHAIN" ]; then printf ' --keychain %q' "$NOTARY_KEYCHAIN" >&2; fi
      printf '\n' >&2
    fi
    printf '  xcrun notarytool log %q --keychain-profile %q' "$submission" "$NOTARY_PROFILE" >&2
    if [ -n "$NOTARY_KEYCHAIN" ]; then printf ' --keychain %q' "$NOTARY_KEYCHAIN" >&2; fi
    printf ' ./notary-log.json\n' >&2
    exit 1
  fi
}

sign_app_item() {
  if ! codesign --force --options runtime --timestamp --sign "$SIGN_IDENTITY" "$1" 2>/dev/null; then
    die "Developer ID 签名失败：检查 JOBFLOW_SIGN_IDENTITY 是否存在、证书是否有效，以及钥匙串是否已解锁且包含私钥。"
  fi
}

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

if [ -n "$SIGN_IDENTITY" ]; then
  # 先签内部可执行文件；身份错误也能在图标生成、打包和联网公证之前报出。
  sign_app_item "$BUILD/Contents/MacOS/JobflowMenu"
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
if [ -n "$SIGN_IDENTITY" ]; then
  # 从内到外签名；WKWebView / posix_spawn / SMAppService 无需额外 entitlement，见 RELEASING.md。
  sign_app_item "$BUILD"
else
  codesign --force --sign - "$BUILD"
fi
codesign --verify --strict --deep "$BUILD"

if [ -n "$DMG" ]; then
  if [ "$NOTARIZE" -eq 1 ]; then
    # ZIP 只用于送审。先给 App 装订，再将它装入最终 DMG，保证两层都有离线票据。
    ditto -c -k --keepParent "$BUILD" "$WORK/Jobflow.zip"
    notarize "$WORK/Jobflow.zip"
    xcrun stapler staple "$BUILD"
  fi
  STAGING="$WORK/dmg"
  mkdir -p "$STAGING"
  cp -R "$BUILD" "$STAGING/"
  ln -s /Applications "$STAGING/Applications"
  PACKAGE="$WORK/Jobflow.dmg"
  hdiutil create -volname Jobflow -srcfolder "$STAGING" -ov -format UDZO "$PACKAGE"
  if [ -n "$SIGN_IDENTITY" ]; then
    codesign --timestamp --sign "$SIGN_IDENTITY" "$PACKAGE" || die "DMG 签名失败；未发布输出文件。"
    codesign --verify --strict "$PACKAGE"
  fi
  if [ "$NOTARIZE" -eq 1 ]; then
    notarize "$PACKAGE"
    xcrun stapler staple "$PACKAGE"
    codesign --verify --strict --deep "$STAGING/求职控制台.app"
    codesign --verify --strict "$PACKAGE"
    spctl -a -vvv -t exec "$STAGING/求职控制台.app"
    spctl -a -vvv -t open --context context:primary-signature "$PACKAGE"
    xcrun stapler validate "$STAGING/求职控制台.app"
    xcrun stapler validate "$PACKAGE"
  fi
  # 仅在所选流程的全部检查通过后覆盖输出；失败不覆盖之前的发布包。
  mv -f "$PACKAGE" "$DMG"
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
