"""Shared, read-only checks for optional console dependencies."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def console_directory(repo_root: Path) -> Path:
    return Path(os.environ.get("JOBFLOW_CONSOLE_DIR") or repo_root / "console")


def console_dependencies_ready(console_dir: Path) -> bool:
    """A leftover node_modules directory is not a usable install."""
    return all(path.is_file() and os.access(path, os.X_OK)
               for path in (console_dir / "node_modules/.bin" / name for name in ("tsc", "next")))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("console_dir", type=Path)
    args = parser.parse_args()
    return 0 if console_dependencies_ready(args.console_dir) else 1


if __name__ == "__main__":
    raise SystemExit(main())
