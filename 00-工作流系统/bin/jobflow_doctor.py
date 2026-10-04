"""Read-only onboarding checks. Never print private values or exception text."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from jobflow_profile import ProfileError, load_channel_config, load_goals, profile_directory
from jobflow_screening import ScreeningError, validate_goals


def check_readiness(repo_root: Path) -> dict:
    root = repo_root.resolve()
    checks = []

    def add(key, required, ok, fix, message="已就绪"):
        checks.append({"id": key, "required": required,
                       "status": "ok" if ok else "missing" if required else "warn",
                       "message": message if ok else fix,
                       "fix": "无需修复。" if ok else fix})

    add("python", True, sys.version_info >= (3, 9), "请安装 Python 3.9 或更新版本，再运行 doctor。")
    add("workspace", True, (root / "00-工作流系统/state/current.json").is_file(),
        "运行 python3 00-工作流系统/bin/jobflow.py init。")
    goals_ok = False
    goals_fix = "按首次使用指南填写个人目录 goals.json，并运行 jobflow_screening.py --validate-profile。"
    try:
        goals = load_goals(repo_root=root)
        validate_goals(goals)
        example = json.loads((root / "00-工作流系统/examples/screening/goals.example.json").read_text(encoding="utf-8"))
        goals_ok = goals != example
        if not goals_ok:
            goals_fix = "还没按你的目标改；请确认目标、权重和硬线后编辑个人目录 goals.json。"
    except (ProfileError, ScreeningError, OSError, ValueError):
        pass
    add("goals", True, goals_ok, goals_fix)

    try:
        resume_ok = any(p.is_file() and not p.stem.lower().startswith("readme")
                        and p.suffix.lower() in {".pdf", ".md", ".json", ".docx", ".txt"}
                        for p in (root / "03-简历").rglob("*"))
    except OSError:
        resume_ok = False
    add("resume", True, resume_ok, "请把至少一份简历放进 03-简历/（PDF、MD、JSON、DOCX 或 TXT；README 不算）。")

    channels_ok = identity_ok = False
    try:
        directory = profile_directory(repo_root=root)
        # Presence only. Identity content is never needed for onboarding checks.
        identity_ok = (directory / "identity.json").is_file()
        if (directory / "search_channels.json").is_file():
            load_channel_config("search_channels.json", repo_root=root)
            channels_ok = True
    except (ProfileError, OSError):
        pass
    add("search_channels", True, channels_ok,
        "确认渠道后，把 config/search_channels.json 复制到个人目录并编辑。")

    node_ok = False
    try:
        node = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=5, check=False)
        version = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", node.stdout.strip())
        node_ok = node.returncode == 0 and version is not None and tuple(map(int, version.groups())) >= (20, 9, 0)
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        pass
    add("node", False, node_ok, "控制台需要 Node 20.9 或更新版本；不用控制台可跳过。")
    add("console_dependencies", False, (root / "console/node_modules").is_dir(),
        "需要控制台时运行 cd console && npm install。")
    add("ego_browser", False, shutil.which("ego-browser") is not None,
        "没有它 Agent 只能用未登录浏览器，见 docs/新手指南.md；安装 ego lite 并启用 ego-browser skill。",
        "命令已在 PATH；仍需确认 Agent skill 与平台登录态。")
    add("identity", False, identity_ok, "identity.json 可选，只在准备投递材料时按需填写。")
    return {"ready": all(c["status"] == "ok" for c in checks if c["required"]), "checks": checks}


def run_doctor(repo_root: Path, *, as_json: bool = False) -> int:
    result = check_readiness(repo_root)
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for check in result["checks"]:
            kind = "必需" if check["required"] else "建议"
            print(f"{check['status']:7} {check['id']} ({kind}): {check['message']}")
        print("准备好了：必需项全部 ok。" if result["ready"] else "尚未准备好：请补齐 missing 项。")
    return 0 if result["ready"] else 1
