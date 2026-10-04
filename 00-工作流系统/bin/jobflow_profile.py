#!/usr/bin/env python3
"""Read private profile files outside the repository; never read identity for scoring."""

from __future__ import annotations

import json
import os
from pathlib import Path


class ProfileError(ValueError):
    """Invalid or unsafe profile location/content (messages never contain values)."""


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _outside_repository(path: Path, repo_root: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == repo_root or repo_root in resolved.parents:
        raise ProfileError("Personal profile must be outside the repository")
    return resolved


def profile_directory(*, repo_root: Path | None = None) -> Path:
    """Resolve only; do not create or migrate personal files."""
    root = (repo_root or repository_root()).resolve()
    value = os.environ.get("JOBFLOW_PROFILE_DIR")
    path = Path(value) if value else Path.home() / ".config/jobflow/profile"
    return _outside_repository(path, root)


def _load_file(name: str, *, repo_root: Path | None = None) -> dict:
    root = (repo_root or repository_root()).resolve()
    directory = profile_directory(repo_root=root)
    path = _outside_repository(directory / name, root)
    # A goals.json symlink must not escape into arbitrary personal files.
    if path.parent != directory:
        raise ProfileError("Profile file must remain inside the profile directory")
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise ProfileError("Profile file is missing, unreadable, or invalid JSON") from None
    if not isinstance(result, dict):
        raise ProfileError("Profile file must contain a JSON object")
    return result


def load_goals(*, repo_root: Path | None = None) -> dict:
    """Read goals.json only. The scoring module validates its specific contract."""
    return _load_file("goals.json", repo_root=repo_root)


def load_identity(*, repo_root: Path | None = None) -> dict:
    """Explicit opt-in for a future application workflow; never called by scorer."""
    return _load_file("identity.json", repo_root=repo_root)
