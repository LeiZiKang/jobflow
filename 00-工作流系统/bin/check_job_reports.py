#!/usr/bin/env python3
"""Check every per-job HTML report in 05-检索报告/岗位报告 against the dossier template rules."""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPORT_DIR = "05-检索报告/岗位报告"
SECTIONS = ["业务与产品", "JD 要点", "薪资", "公司背景", "WLB", "匹配面", "投递建议"]
NATURE_TAGS = ["自研产品", "外包·交付", "外包", "未核实"]


def problems(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    found = []
    heads = re.findall(r'<h2><span class="num">(\d\d)</span>([^<]*)</h2>', text)
    numbers = [n for n, _ in heads]
    if numbers != [f"{i:02d}" for i in range(1, 8)]:
        found.append(f"章节编号应为 01-07 顺序，实际 {numbers}")
    for (_, title), expected in zip(heads, SECTIONS):
        if expected not in title:
            found.append(f"章节「{title.strip()}」应包含「{expected}」")
    head = re.search(r'<div class="jhead">(.*?)</div>\s*(?:<!--|<h2)', text, re.S)
    if not head:
        found.append("缺少头部 .jhead")
    else:
        block = head.group(1)
        if 'class="jdlink"' not in block:
            found.append("原始 JD 链接不在头部 .jhead 里")
        tags = re.search(r'<div class="tags">(.*?)</div>', block, re.S)
        if not tags or not any(t in tags.group(1) for t in NATURE_TAGS):
            found.append("头部 tags 缺少用工性质（自研产品 / 外包·交付 / 未核实）")
        if tags and "jdlink" in tags.group(1):
            found.append("JD 链接应在 tags 下方，不在 tags 里面")
    base = re.search(r"^:root\{[^}]*--bg:#([0-9a-fA-F]{6})", text, re.M)
    if not base or sum(int(base.group(1)[i:i + 2], 16) for i in (0, 2, 4)) / 3 > 80:
        found.append(":root 基色应为暗色（--bg 深色），亮色只放 prefers-color-scheme: light 分支")
    # 新报告必须在头部写工作地址。
    stamp = re.search(r"-(20\d{6})-", path.name)
    if stamp and stamp.group(1) >= "20260919" and "工作地址" not in (head.group(1) if head else ""):
        found.append("头部缺少「📍 工作地址」一行（查不到也要写「未能核实」）")
    if "{{" in text:
        found.append("仍有未填写的 {{占位符}}")
    # v2 opt-in: old evidence is not retroactively relabeled complete.
    if re.search(r'<meta\s+name=[\"\']jobflow-report-version[\"\']\s+content=[\"\']2[\"\']', text):
        for label in ("招聘主体", "合同主体", "直接股东", "持股比例", "控制链", "最终母公司", "证据断点", "硬线状态", "证据覆盖率", "配置版本"):
            if label not in text:
                found.append(f"v2报告缺少必填证据项：{label}")
        if 'class="ownership-evidence"' not in text:
            found.append("v2报告缺少股权证据表 ownership-evidence")
    return found


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[2]
    report_dir = root / REPORT_DIR
    files = [path for path in sorted(report_dir.glob("*.html")) if not path.name.startswith("_模板")] if report_dir.exists() else []
    bad = 0
    for path in files:
        issues = problems(path)
        if issues:
            bad += 1
            print(f"FAIL {path.relative_to(root)}")
            for issue in issues:
                print(f"  - {issue}")
    if bad:
        print(f"FAIL: {bad}/{len(files)} 份岗位报告不合模板")
        return 1
    print(f"OK: {len(files)} 份岗位报告符合模板")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
