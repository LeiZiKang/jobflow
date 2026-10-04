#!/bin/bash
# 推到公开仓库之前跑：只检查会被 git 跟踪的文件（含暂存区），以及已有提交的历史。
# 命中任何一条就失败。用户数据目录被 .gitignore 忽略，不在检查范围内。
#
# 额外的私人关键词（自己的名字、手机号、投过的公司）不要写进本文件——
# 写到仓库外的 ~/.config/jobflow/publish-denylist.txt（每行一个正则），
# 或用 JOBFLOW_PUBLISH_DENYLIST 指向别的文件。
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

fail=0
report() { echo "FAIL: $1"; fail=1; }

# 将要发布的文件：已跟踪 + 未跟踪但未被忽略
FILES=()
while IFS= read -r -d '' f; do FILES+=("$f"); done < <(git ls-files -z --cached --others --exclude-standard)
[ "${#FILES[@]}" -gt 0 ] || { echo "FAIL: 没有找到要发布的文件"; exit 1; }

scan() { # $1 = 说明, $2 = 正则
  local hits
  hits=$(printf '%s\0' "${FILES[@]}" | xargs -0 grep -InE -- "$2" 2>/dev/null | grep -v '^00-工作流系统/scripts/check-publishable.sh:' || true)
  if [ -n "$hits" ]; then report "$1"; echo "$hits" | head -20; fi
}

# 1. 手机号（允许空格/横线分隔）
scan "疑似手机号" '(\+?86[ -]?)?\b1[3-9][0-9][ -]?[0-9]{4}[ -]?[0-9]{4}\b'

# 2. 邮箱：只允许 example.com / example.org / noreply
emails=$(printf '%s\0' "${FILES[@]}" | xargs -0 grep -IohE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' 2>/dev/null \
  | grep -viE '@example\.(com|org)$|^noreply@|@anthropic\.com$|@users\.noreply\.github\.com$' | sort -u || true)
[ -z "$emails" ] || { report "出现非示例邮箱"; echo "$emails"; }

# 3. 个人绝对路径
mac_home='/'"Users"
scan "个人绝对路径" "${mac_home}"'/[A-Za-z0-9_.-]+|/home/[A-Za-z0-9_.-]+/'

# 4. 密钥形状
scan "疑似密钥或 token" '(gh[pousr]_[A-Za-z0-9]{20,}|\bsk-(ant-|proj-)?[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|xox[abpr]-[A-Za-z0-9-]{10,})'

# 5. 二进制文档与截图（图标等资源应在构建时生成，不提交）
# 唯一例外：docs/images/ 下的 PNG（README 截图，只能用 init --demo 的虚构数据截取），单张不超过 1 MB
bins=$(printf '%s\n' "${FILES[@]}" | grep -iE '\.(pdf|png|jpe?g|heic|docx?|xlsx?|sqlite|db)$' | grep -vE '^docs/images/[A-Za-z0-9._-]+\.png$' || true)
for img in $(printf '%s\n' "${FILES[@]}" | grep -E '^docs/images/[A-Za-z0-9._-]+\.png$' || true); do
  [ "$(wc -c < "$img")" -le 1048576 ] || report "截图超过 1 MB：$img"
done
[ -z "$bins" ] || { report "出现二进制文档/图片"; echo "$bins"; }

# 6. 用户数据目录不应被发布
data=$(printf '%s\n' "${FILES[@]}" | grep -E '^(0[1-6]-[^/]+/|00-工作流系统/(state|events|evidence|approvals)/|\.agent-memory/|assets/)' \
  | grep -vE '/(README\.md|\.gitkeep)$' || true)
[ -z "$data" ] || { report "用户数据目录里有文件将被发布"; echo "$data" | head -20; }

# 7. 仓库外的私人关键词表
DENY="${JOBFLOW_PUBLISH_DENYLIST:-$HOME/.config/jobflow/publish-denylist.txt}"
if [ -f "$DENY" ]; then
  while IFS= read -r pat; do
    [ -z "$pat" ] || [[ "$pat" == \#* ]] && continue
    scan "命中私人关键词表" "$pat"
    if git rev-parse -q --verify HEAD >/dev/null && git log -p --all --format= | grep -qE -- "$pat"; then
      report "git 历史里命中私人关键词表（重写历史或重新建仓库）"
    fi
  done < "$DENY"
else
  echo "WARN: 没有私人关键词表 ${DENY}，只做了通用检查"
fi

# 8. 提交作者邮箱必须是 noreply（个人邮箱会永久公开在历史里）
if git rev-parse -q --verify HEAD >/dev/null; then
  authors=$(git log --all --format='%ae%n%ce' | sort -u | grep -viE '@users\.noreply\.github\.com$|^noreply@' || true)
  [ -z "$authors" ] || { report "提交历史里有非 noreply 邮箱"; echo "$authors"; }
fi
next_email=$(git config user.email || true)
case "$next_email" in
  *@users.noreply.github.com) ;;
  *) report "当前 git user.email 不是 GitHub noreply 邮箱：先 git config user.email <id>+<login>@users.noreply.github.com" ;;
esac

if [ "$fail" -ne 0 ]; then
  echo "NOT PUBLISHABLE"
  exit 1
fi
echo "OK: publishable"
