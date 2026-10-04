"""Consent-based macOS setup. Standard library only; doctor owns readiness checks."""
from __future__ import annotations

# Pinned LTS; update deliberately after checking the official release and checksums.
# https://nodejs.org/en/blog/release/v24.21.0
NODE_VERSION = "24.21.0"
MENU_URL = "https://github.com/LeiZiKang/jobflow/releases/latest/download/Jobflow.dmg"
ITEMS = ("xcode_clt", "node", "console_dependencies", "ego_browser", "menubar_app")

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile

from jobflow_environment import (applications_directory, console_directory, installed_app,
                                 node_environment, node_qualified, resolve_node, resolve_npm,
                                 tools_directory)
from jobflow_doctor import resolve_language

ROOT = Path(__file__).resolve().parents[2]


def architecture(machine: str | None = None) -> str:
    value = (machine or platform.machine()).lower()
    if value in ("arm64", "aarch64"):
        return "arm64"
    if value in ("x86_64", "amd64", "x64"):
        return "x64"
    raise ValueError("Unsupported macOS architecture: " + value)


def node_urls(arch: str) -> tuple[str, str]:
    arch = architecture(arch)
    base = f"https://nodejs.org/dist/v{NODE_VERSION}/"
    return base + f"node-v{NODE_VERSION}-darwin-{arch}.tar.gz", base + "SHASUMS256.txt"


def read_doctor(root: Path, lang: str) -> dict:
    process = subprocess.run([sys.executable, str(root / "00-工作流系统/bin/jobflow.py"),
                              "doctor", "--json", "--lang", lang], capture_output=True, text=True)
    if process.returncode not in (0, 1):
        raise RuntimeError("doctor failed; run jobflow.py doctor for details")
    return json.loads(process.stdout)


def plan(result: dict) -> list[str]:
    missing = {c.get("install") for c in result["checks"] if c["status"] != "ok"}
    return [item for item in ITEMS if item in missing]


def describe(item: str, root: Path, lang: str) -> str:
    arch = architecture()
    console = console_directory(root)
    node_url, sums = node_urls(arch)
    # Sizes are planning estimates, not measurements or download guarantees.
    records = {
        "xcode_clt": (
            "Xcode 命令行工具 / Xcode Command Line Tools (git + python3; not full Xcode)",
            "https://developer.apple.com/download/all/ (Apple system installer)",
            "约 / about 1–3 GB download, several GB installed; Apple dialog gives actual size",
            "/Library/Developer/CommandLineTools (or an existing Xcode developer directory)",
            "用户自行删除该目录；如需管理员密码，仅由用户在终端/系统界面处理 / user removes that directory; admin authentication is user-only"),
        "node": (f"Node.js {NODE_VERSION} LTS + npm; 控制台运行时 / console runtime",
                 f"{node_url}\nSHA-256: {sums}", "约 / about 40–70 MB download, 150–250 MB installed",
                 str(tools_directory() / "node"), "删除此 node 目录 / remove this node directory"),
        "console_dependencies": (
            "控制台依赖 / console dependencies (Next.js + TypeScript; npm ci with lockfile)",
            "https://registry.npmjs.org/ (console/package-lock.json resolved URLs)",
            "约 / about 100–500 MB download, 0.5–1 GB installed; depends on architecture/cache",
            str(console / "node_modules") + "; npm cache: " + str(tools_directory() / "npm-cache"),
            "删除上述 node_modules 和 npm-cache / remove the listed node_modules and npm-cache"),
        "ego_browser": ("ego lite; 复用浏览器登录态 / reuse browser sessions",
                        f"https://cdn.ego.app/setup/macos/{arch}/egolite.dmg\nhttps://lite.ego.app/",
                        "估计 / estimate 200–500 MB download, 0.5–1 GB installed; actual release may vary",
                        str(applications_directory()) + "/*.app",
                        "退出 App 后将它移到废纸篓；浏览数据由用户在 App 中管理 / quit and move app to Trash; manage browser data in the app"),
        "menubar_app": ("Jobflow 菜单栏 App（可选）/ optional menu bar launcher",
                        MENU_URL + "\nhttps://github.com/LeiZiKang/jobflow/releases",
                        "估计 / estimate 1–30 MB download; actual release may vary",
                        str(applications_directory() / "Jobflow.app"),
                        "退出后将 Jobflow.app 移到废纸篓 / quit and move Jobflow.app to Trash"),
    }
    labels = ("安装及用途", "官方来源", "大约大小", "安装到", "卸载方法") if lang == "zh" else ("Install / purpose", "Official source", "Approximate size", "Destination", "Uninstall")
    lines = [f"\n[{item}]"] + [f"{key}: {value}" for key, value in zip(labels, records[item])]
    if item == "menubar_app":
        lines.append("未公证，Gatekeeper 可能拦截。右键→打开，或系统设置→隐私与安全性→仍要打开；首次启动选择仓库文件夹。 / Not notarized: use right-click → Open or System Settings → Privacy & Security → Open Anyway; choose the repository on first launch.")
    lines.append("不修改 shell 配置、代理、网络或系统设置；不读取、输入或缓存密码。 / No shell, proxy, network or system settings changes; no password handling.")
    return "\n".join(lines)


def download(url: str, destination: Path) -> None:
    # System curl uses the system trust store. One attempt, bounded duration,
    # HTTPS-only redirects; never modify proxy settings or execute remote scripts.
    result = subprocess.run(["/usr/bin/curl", "--fail", "--location", "--show-error", "--silent",
                             "--proto", "=https", "--proto-redir", "=https", "--connect-timeout", "20",
                             "--max-time", "600", "--output", str(destination), url], capture_output=True, text=True)
    if result.returncode:
        # Do not echo remote response/proxy credentials. curl's code is enough
        # to distinguish DNS, connection, HTTP, TLS, and timeout failures.
        reason = {5: "proxy DNS", 6: "DNS", 7: "connection", 22: "HTTP error / asset unavailable",
                  28: "timeout", 35: "TLS", 60: "certificate"}.get(result.returncode, "download failure")
        raise RuntimeError(f"{reason} (curl {result.returncode}). Network/proxy/company restrictions may apply; no retry or settings change.")


def verify_sha256(archive: Path, sums: Path) -> None:
    entries = [line.split() for line in sums.read_text(encoding="utf-8").splitlines()]
    expected = [fields[0] for fields in entries if len(fields) == 2 and fields[1].lstrip("*") == archive.name]
    digest = hashlib.sha256()
    with archive.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    if len(expected) != 1 or expected[0].lower() != digest.hexdigest():
        raise ValueError("SHA-256 verification failed; refusing installation")


def safe_extract(archive: Path, target: Path, top: str) -> None:
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        links = {m.name.rstrip("/") for m in members if m.issym()}
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != top:
                raise ValueError("Unsafe archive path")
            if any(str(parent) in links for parent in path.parents):
                raise ValueError("Archive writes through a symlink")
            if not (member.isfile() or member.isdir() or member.issym()):
                raise ValueError("Unsupported archive member")
            if member.mode & 0o7000:
                raise ValueError("Unsafe archive permissions")
            if member.issym():
                if PurePosixPath(member.linkname).is_absolute():
                    raise ValueError("Unsafe archive link")
                resolved = (target / member.name).parent.joinpath(member.linkname).resolve()
                try:
                    resolved.relative_to(target / top)
                except ValueError:
                    raise ValueError("Archive link escapes installation") from None
        tar.extractall(target, members=members)


def install_node_archive(archive: Path, sums: Path, arch: str) -> None:
    verify_sha256(archive, sums)  # Must precede any extraction or destination writes.
    parent = tools_directory()
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".node-", dir=parent) as temporary:
        stage = Path(temporary)
        top = f"node-v{NODE_VERSION}-darwin-{architecture(arch)}"
        safe_extract(archive, stage, top)
        source = stage / top
        if not node_qualified(source / "bin/node") or not (source / "bin/npm").is_file():
            raise ValueError("Archive has no working Node >= 20.9 and npm")
        destination = parent / "node"
        backup = stage / "previous"
        if destination.exists() or destination.is_symlink():
            destination.rename(backup)
        try:
            source.rename(destination)
        except OSError:
            if backup.exists() or backup.is_symlink():
                backup.rename(destination)
            raise


def install_dmg(item: str, dmg: Path) -> None:
    if installed_app(item):
        return
    # A mountpoint owned by this call makes cleanup precise, even on copy failure.
    with tempfile.TemporaryDirectory(prefix="jobflow-dmg-") as temporary:
        mount = Path(temporary) / "volume"
        mount.mkdir()
        attached = False
        try:
            subprocess.run(["/usr/bin/hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", str(mount), str(dmg)], check=True)
            attached = True
            candidates = [p for p in mount.glob("*.app") if p.is_dir() and not p.is_symlink()]
            if len(candidates) != 1:
                raise ValueError("Expected exactly one app in the official DMG; install manually")
            source = candidates[0]
            if item == "menubar_app" and source.name != "Jobflow.app":
                raise ValueError("Unexpected menu bar app name")
            parent = applications_directory()
            parent.mkdir(parents=True, exist_ok=True)
            destination = parent / source.name
            if destination.exists() or destination.is_symlink():
                raise ValueError("Destination already exists; refusing overwrite")
            with tempfile.TemporaryDirectory(prefix=".jobflow-app-", dir=parent) as staging:
                staged = Path(staging) / source.name
                subprocess.run(["/usr/bin/ditto", str(source), str(staged)], check=True)
                staged.rename(destination)
        finally:
            if attached or os.path.ismount(mount):
                subprocess.run(["/usr/bin/hdiutil", "detach", str(mount)], check=True)
    subprocess.run(["/usr/bin/open", str(destination)], check=True)


def install(item: str, root: Path) -> str:
    if item == "xcode_clt":
        subprocess.run(["/usr/bin/xcode-select", "--install"], check=True)
        print("请在系统弹窗中安装；管理员密码仅由你本人输入。装好后告诉 Agent，再运行 doctor。 / Finish the Apple dialog yourself, then tell your agent and rerun doctor.")
        return "pending-user"
    if item == "node":
        arch = architecture()
        url, checksum = node_urls(arch)
        with tempfile.TemporaryDirectory(prefix="jobflow-node-") as temporary:
            archive = Path(temporary) / url.rsplit("/", 1)[1]
            sums = Path(temporary) / "SHASUMS256.txt"
            download(url, archive)
            download(checksum, sums)
            install_node_archive(archive, sums, arch)
    elif item == "console_dependencies":
        node = resolve_node()
        if node is None or resolve_npm(node) is None:
            raise ValueError("Node >= 20.9 and npm required; ask consent for node separately. No implicit dependency installation.")
        console = console_directory(root)
        # Keep package sources reviewable and don't silently use a custom registry.
        lock = console / "package-lock.json"
        if lock.is_file():
            packages = json.loads(lock.read_text()).get("packages", {})
            if any(p.get("resolved", "").startswith(("http:", "https:")) and not p["resolved"].startswith("https://registry.npmjs.org/") for p in packages.values()):
                raise ValueError("Nonstandard package source in lockfile; review and install manually")
        subprocess.run([resolve_npm(node), "ci" if lock.is_file() else "install", "--registry=https://registry.npmjs.org/",
                        "--cache", str(tools_directory() / "npm-cache"), "--fetch-retries=0", "--fetch-timeout=60000",
                        "--no-audit", "--no-fund"], cwd=console, env=node_environment(node), check=True)
    elif item in ("ego_browser", "menubar_app"):
        if installed_app(item):
            return "skipped"
        url = f"https://cdn.ego.app/setup/macos/{architecture()}/egolite.dmg" if item == "ego_browser" else MENU_URL
        with tempfile.TemporaryDirectory(prefix="jobflow-download-") as temporary:
            dmg = Path(temporary) / "download.dmg"
            download(url, dmg)
            install_dmg(item, dmg)
        if item == "ego_browser":
            print("请按 ego lite 引导完成首次设置并启用 Agent 侧 ego-browser skill；平台登录由你完成。 / Finish ego lite onboarding, enable the agent-side ego-browser skill, and sign in yourself.")
    return "installed"


def print_summary(result: dict) -> None:
    for check in result["checks"]:
        print(f"{check['status']:7} {check['id']} install={check.get('install') or '-'}: {check['message']}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Read-only doctor summary; same readiness exit code")
    mode.add_argument("--yes", metavar="ITEM", choices=ITEMS, action="append", help="One item only, AFTER explicit user consent in conversation")
    parser.add_argument("--lang", choices=("zh", "en"))
    args = parser.parse_args(argv)
    if args.yes and len(args.yes) != 1:
        parser.error("--yes requires exactly one item")
    args.yes = args.yes[0] if args.yes else None
    lang = resolve_language(args.lang)
    result = read_doctor(ROOT, lang)
    if args.check:
        print_summary(result)
        return 0 if result["ready"] else 1
    if platform.system() != "Darwin":
        print("目前只支持 macOS / Currently only macOS is supported.", file=sys.stderr)
        return 1
    outcomes = []
    failures = False
    pending_user = False
    for item in ([args.yes] if args.yes else ITEMS):
        result = read_doctor(ROOT, lang)
        if item not in plan(result):
            outcomes.append((item, "skipped (already ready)"))
            continue
        print(describe(item, ROOT, lang), flush=True)
        if not args.yes:
            try:
                reply = input("同意安装？ / Install? [y/N] ").strip().lower()
            except EOFError:
                reply = ""
            if reply not in ("y", "yes"):
                outcomes.append((item, "skipped (declined)"))
                continue
        try:
            outcome = install(item, ROOT)
            if outcome == "pending-user":
                pending_user = True
                outcomes.append((item, outcome))
                break  # Wait for the user before running doctor again.
            result = read_doctor(ROOT, lang)
            print_summary(result)
            if outcome not in ("pending-user", "skipped") and item in plan(result):
                raise RuntimeError("Post-install doctor check still not ready; manual inspection needed")
            outcomes.append((item, outcome))
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, tarfile.TarError) as error:
            failures = True
            outcomes.append((item, "failed"))
            print(f"ERROR [{item}]: {error}\n请用上面的官方来源手动安装，再运行 setup.sh --check。 / Install manually from the official source above, then rerun setup.sh --check.", file=sys.stderr)
    print("\n汇总 / Summary:")
    for item, outcome in outcomes:
        print(f"{item}: {outcome}")
    if pending_user:
        print("等待用户完成系统安装后再检测 / Waiting for user completion before rechecking.")
    else:
        print_summary(read_doctor(ROOT, lang))
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Setup: {error}", file=sys.stderr)
        raise SystemExit(1)
