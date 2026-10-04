"""Shared, read-only macOS environment checks and process-local Node resolution."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess


def tools_directory() -> Path:
    return Path(os.environ.get("JOBFLOW_TOOLS_DIR") or Path.home() / ".local/share/jobflow/tools").expanduser().absolute()


def applications_directory() -> Path:
    return Path(os.environ.get("JOBFLOW_APPLICATIONS_DIR") or Path.home() / "Applications").expanduser().absolute()


def installed_app(item: str) -> Path | None:
    names = {"ego_browser": {"egolite", "ego"}, "menubar_app": {"jobflow"}}[item]
    for directory in (Path(os.environ.get("JOBFLOW_SYSTEM_APPLICATIONS_DIR", "/Applications")), applications_directory()):
        for app in directory.glob("*.app"):
            if re.sub(r"[\s_-]", "", app.stem).lower() in names and app.is_dir():
                return app
    return None


def xcode_clt_ready() -> bool:
    if platform.system() != "Darwin":
        return False
    try:
        result = subprocess.run(["/usr/bin/xcode-select", "-p"], capture_output=True, text=True, timeout=5)
        return result.returncode == 0 and Path(result.stdout.strip()).is_dir()
    except (OSError, subprocess.TimeoutExpired):
        return False


def node_qualified(node: Path) -> bool:
    if not node.is_file() or not os.access(node, os.X_OK):
        return False
    try:
        result = subprocess.run([str(node), "--version"], capture_output=True, text=True, timeout=5)
        version = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", result.stdout.strip())
        return result.returncode == 0 and version is not None and tuple(map(int, version.groups())) >= (20, 9, 0)
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        return False


def resolve_node() -> Path | None:
    # Search all PATH entries, including a qualified binary behind an old one.
    for directory in os.get_exec_path():
        node = Path(directory or ".").absolute() / "node"
        if node_qualified(node):
            return node
    node = tools_directory() / "node/bin/node"
    return node if node_qualified(node) else None


def node_environment(node: Path) -> dict:
    return {**os.environ, "PATH": str(node.parent) + os.pathsep + os.environ.get("PATH", "")}


def resolve_npm(node: Path) -> str | None:
    return shutil.which("npm", path=node_environment(node)["PATH"])


def console_directory(repo_root: Path) -> Path:
    return Path(os.environ.get("JOBFLOW_CONSOLE_DIR") or repo_root / "console")


def console_dependencies_ready(console_dir: Path) -> bool:
    """A leftover node_modules directory is not a usable install."""
    return all(path.is_file() and os.access(path, os.X_OK)
               for path in (console_dir / "node_modules/.bin" / name for name in ("tsc", "next")))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("console_dir", type=Path, nargs="?")
    parser.add_argument("--node-bin", action="store_true", help="Print the selected Node bin directory; no writes")
    args = parser.parse_args()
    if args.node_bin:
        node = resolve_node()
        if node:
            print(node.parent)
            return 0
        return 1
    if args.console_dir is None:
        parser.error("console_dir or --node-bin required")
    return 0 if console_dependencies_ready(args.console_dir) else 1


if __name__ == "__main__":
    raise SystemExit(main())
