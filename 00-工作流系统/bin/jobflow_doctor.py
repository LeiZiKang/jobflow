"""Read-only onboarding checks. Never print private values or exception text."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import platform

from jobflow_profile import ProfileError, load_channel_config, load_goals, profile_directory
from jobflow_screening import ScreeningError, validate_goals
from jobflow_environment import (console_dependencies_ready, console_directory, resolve_node,
                                 installed_app, xcode_clt_ready, resolve_npm)


def profile_copy_command(source: str, name: str) -> str:
    # Keep private paths out of output; let the user's shell expand its own env.
    directory = '${JOBFLOW_PROFILE_DIR:-$HOME/.config/jobflow/profile}'
    return f'mkdir -p "{directory}" && cp -i "{source}" "{directory}/{name}"'


def resolve_language(lang: str | None = None) -> str:
    if lang is not None:
        if lang not in ("en", "zh"):
            raise ValueError("Unsupported language")
        return lang
    configured = os.environ.get("JOBFLOW_LANG", "").lower()
    if configured in ("en", "zh"):
        return configured
    return "zh" if os.environ.get("LANG", "").lower().startswith("zh") else "en"


def check_readiness(repo_root: Path, *, lang: str | None = None) -> dict:
    language = resolve_language(lang)

    def tr(zh, en):
        return zh if language == "zh" else en

    root = repo_root.resolve()
    checks = []

    def add(key, required, ok, fix, message=None, install=None, missing=False):
        if install:
            fix += tr(" 可以运行 `00-工作流系统/scripts/setup.sh` 让它帮你装（须逐项同意）。",
                      " You can run `00-工作流系统/scripts/setup.sh` to install it with your per-item consent.")
        message = message or tr("已就绪", "Ready")
        checks.append({"id": key, "required": required,
                       "status": "ok" if ok else "missing" if required or missing else "warn",
                       "install": install,
                       "message": message if ok else fix,
                       "fix": tr('无需修复。', 'No action needed.') if ok else fix})

    add("python", True, sys.version_info >= (3, 9), tr('请安装 Python 3.9 或更新版本，再运行 doctor。', 'Install Python 3.9 or later, then run doctor again.'), install="xcode_clt")
    add("macos", True, platform.system() == "Darwin", tr('目前只支持 macOS。', 'Currently only macOS is supported.'))
    add("xcode_clt", True, xcode_clt_ready(),
        tr('需要 Apple Xcode 命令行工具（非完整 Xcode），提供 git 和 python3。',
           'Apple Xcode Command Line Tools (not full Xcode) provide git and python3.'), install="xcode_clt")
    add("workspace", True, (root / "00-工作流系统/state/current.json").is_file(),
        tr('运行 python3 00-工作流系统/bin/jobflow.py init。', 'Run python3 00-工作流系统/bin/jobflow.py init.'))
    goals_ok = False
    goals_fix = (tr('确认目标后复制模板并编辑：', 'After confirming your goals, copy the template and edit it: ') + profile_copy_command(
        "00-工作流系统/examples/screening/goals.example.json", "goals.json")
        + tr('；再运行 python3 00-工作流系统/bin/jobflow_screening.py --validate-profile。', '; then run python3 00-工作流系统/bin/jobflow_screening.py --validate-profile.'))
    try:
        goals = load_goals(repo_root=root)
        validate_goals(goals)
        example = json.loads((root / "00-工作流系统/examples/screening/goals.example.json").read_text(encoding="utf-8"))
        # Omitted and null sorting preferences both mean undecided. Removing
        # this field alone must not make an otherwise untouched template ready.
        goals_ok = {**goals, "foreign_first": goals.get("foreign_first")} != {
            **example, "foreign_first": example.get("foreign_first")}
        if not goals_ok:
            goals_fix = tr('还没按你的目标改；请确认目标、权重和硬线后编辑个人目录 goals.json。', 'The goals template has not been customized. Confirm your goals, weights, and hard rules, then edit goals.json in your personal directory.')
    except (ProfileError, ScreeningError, OSError, ValueError):
        pass
    add("goals", True, goals_ok, goals_fix)

    try:
        resume_ok = any(p.is_file() and not p.stem.lower().startswith("readme")
                        and p.suffix.lower() in {".pdf", ".md", ".json", ".docx", ".txt"}
                        for p in (root / "03-简历").rglob("*"))
    except OSError:
        resume_ok = False
    add("resume", True, resume_ok, tr('请把至少一份简历放进 03-简历/（PDF、MD、JSON、DOCX 或 TXT；README 不算）。', 'Add at least one resume to 03-简历/ (PDF, MD, JSON, DOCX, or TXT; README files do not count).'))

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
        tr('确认渠道后复制并编辑：', 'After confirming your channels, copy the template and edit it: ') + profile_copy_command(
            "00-工作流系统/config/search_channels.json", "search_channels.json"))

    node = resolve_node()
    add("node", False, node is not None, tr('控制台需要 Node 20.9 或更新版本；不用控制台可跳过。', 'The console needs Node 20.9 or later. Skip this if you do not need the console.'), install="node", missing=True)
    add("console_dependencies", False, console_dependencies_ready(console_directory(root)) and node is not None and resolve_npm(node) is not None,
        tr('控制台依赖缺失或不完整，或没有可用 npm；安装使用 lockfile 的 npm ci。',
           'Console dependencies are incomplete or npm is unavailable; installation uses npm ci with the lockfile.'), install="console_dependencies")
    add("ego_browser", False, shutil.which("ego-browser") is not None or installed_app("ego_browser") is not None,
        tr('安装 ego lite，再按应用引导启用 Agent 侧 ego-browser skill。', 'Install ego lite, then follow its onboarding to enable the agent-side ego-browser skill.'),
        tr('已发现命令或 App；仍需用户完成首次设置，并核实 Agent skill 与平台登录态。', 'Command or app found; finish first-run setup and verify the agent skill and platform sign-ins.'), install="ego_browser")
    add("menubar_app", False, installed_app("menubar_app") is not None,
        tr('可选菜单栏 App 可从 GitHub Releases 安装，无需自己编译。', 'The optional menu bar app is available from GitHub Releases; no local build is needed.'), install="menubar_app")
    add("identity", False, identity_ok, tr('identity.json 可选，只在准备投递材料时按需填写。', 'identity.json is optional. Add it only when needed to prepare application materials.'))
    return {"ready": all(c["status"] == "ok" for c in checks if c["required"]), "checks": checks}


def run_doctor(repo_root: Path, *, as_json: bool = False, lang: str | None = None) -> int:
    language = resolve_language(lang)
    result = check_readiness(repo_root, lang=language)
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for check in result["checks"]:
            kind = ("必需" if check["required"] else "建议") if language == "zh" else ("required" if check["required"] else "optional")
            print(f"{check['status']:7} {check['id']} ({kind}): {check['message']}")
        if language == "zh":
            print("准备好了：必需项全部 ok。" if result["ready"] else "尚未准备好：请补齐 missing 项。")
        else:
            print("Ready: all required checks passed." if result["ready"] else "Not ready: complete the missing required items.")
    return 0 if result["ready"] else 1
