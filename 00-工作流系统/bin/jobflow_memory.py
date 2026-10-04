#!/usr/bin/env python3
"""Canonical, provenance-aware long-term memory for the jobflow repository."""

from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator


MEMORY_TYPES = {"fact", "preference", "decision", "lesson", "procedure", "open_question"}
MEMORY_STATES = {"proposed", "accepted", "rejected", "superseded"}
AUTHOR_TYPES = {"human", "agent", "system"}
SENSITIVITY = {"internal", "restricted"}
MEMORY_ID_PATTERN = re.compile(r"mem-[a-z0-9]+(?:-[a-z0-9]+)*")
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bxox(?:b|p|a|r|s)-[A-Za-z0-9-]{12,}\b"),
    re.compile(r"(?i)\b(?:password|api[_-]?key|access[_-]?token|cookie)\s*[:=]\s*\S+"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _contains_secret(value: Any) -> bool:
    if isinstance(value, str):
        if value.startswith("secret://"):
            return False
        return any(pattern.search(value) for pattern in SECRET_PATTERNS)
    if isinstance(value, dict):
        return any(_contains_secret(key) or _contains_secret(child) for key, child in value.items())
    if isinstance(value, list):
        return any(_contains_secret(child) for child in value)
    return False


_BIN_DIR = Path(__file__).resolve().parent
if str(_BIN_DIR) not in sys.path:
    sys.path.insert(0, str(_BIN_DIR))

from jobflow_paths import default_runtime_dir


class MemoryConflictError(RuntimeError):
    """Raised when a writer uses a stale expected revision."""


class MemoryStore:
    def __init__(self, system_dir: Path, runtime_dir: Path | None = None) -> None:
        self.system_dir = system_dir.resolve()
        self.repo_root = self.system_dir.parent.resolve()
        self.path = self.system_dir / "state" / "memory.json"
        # 锁文件不能留在仓库里：仓库在 iCloud 同步路径下，见 bin/jobflow_paths.py。
        # 测试传 runtime_dir 以保持隔离。
        self.lock_path = (runtime_dir or default_runtime_dir()) / "memory.lock"

    def load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError(f"missing memory file: {self.path.relative_to(self.repo_root)}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid memory JSON at {exc.lineno}:{exc.colno}: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ValueError("memory.json must contain an object")
        return value

    @contextmanager
    def locked(self) -> Iterator[None]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _write(self, document: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(document, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temporary.exists():
                temporary.unlink()

    def validate(self, document: dict[str, Any] | None = None) -> list[str]:
        errors: list[str] = []
        document = document if document is not None else self.load()
        if document.get("schema_version") != 1:
            errors.append("memory.json: schema_version must be 1")
        if not isinstance(document.get("revision"), int) or document.get("revision", -1) < 0:
            errors.append("memory.json: revision must be a non-negative integer")
        if not _parse_time(document.get("updated_at")):
            errors.append("memory.json: updated_at must be an ISO datetime")
        items = document.get("items")
        if not isinstance(items, list):
            return errors + ["memory.json: items must be a list"]
        ids: set[str] = set()
        for index, item in enumerate(items):
            label = f"memory.json.items[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{label} must be an object")
                continue
            memory_id = item.get("memory_id")
            if not isinstance(memory_id, str) or not MEMORY_ID_PATTERN.fullmatch(memory_id):
                errors.append(f"{label}: invalid memory_id")
            elif memory_id in ids:
                errors.append(f"{label}: duplicate memory_id {memory_id}")
            else:
                ids.add(memory_id)
            if item.get("type") not in MEMORY_TYPES:
                errors.append(f"{label}: invalid type")
            if item.get("status") not in MEMORY_STATES:
                errors.append(f"{label}: invalid status")
            if not isinstance(item.get("scope"), str) or not item.get("scope"):
                errors.append(f"{label}: scope is required")
            if not isinstance(item.get("subject"), str) or not item.get("subject"):
                errors.append(f"{label}: subject is required")
            statement = item.get("statement")
            if not isinstance(statement, str) or not statement.strip() or len(statement) > 4_000:
                errors.append(f"{label}: statement must be 1..4000 characters")
            if item.get("sensitivity") not in SENSITIVITY:
                errors.append(f"{label}: invalid sensitivity")
            tags = item.get("tags")
            if not isinstance(tags, list) or not all(isinstance(tag, str) and tag for tag in tags):
                errors.append(f"{label}: tags must be a string list")
            sources = item.get("source_refs")
            if not isinstance(sources, list) or not sources:
                errors.append(f"{label}: source_refs must be non-empty")
                sources = []
            for source in sources:
                if not isinstance(source, str) or not self._valid_source(source):
                    errors.append(f"{label}: invalid source ref {source!r}")
            author = item.get("author")
            if not isinstance(author, dict) or author.get("type") not in AUTHOR_TYPES or not author.get("id"):
                errors.append(f"{label}: valid author is required")
                author = {}
            if not _parse_time(item.get("created_at")) or not _parse_time(item.get("updated_at")):
                errors.append(f"{label}: created_at and updated_at must be ISO datetimes")
            valid_from = _parse_time(item.get("valid_from"))
            valid_until = _parse_time(item.get("valid_until"))
            if item.get("valid_from") is not None and not valid_from:
                errors.append(f"{label}: valid_from must be null or ISO datetime")
            if item.get("valid_until") is not None and not valid_until:
                errors.append(f"{label}: valid_until must be null or ISO datetime")
            if valid_from and valid_until and valid_until <= valid_from:
                errors.append(f"{label}: valid_until must be after valid_from")
            if item.get("status") == "accepted":
                review = item.get("review")
                if (
                    not isinstance(review, dict)
                    or review.get("decision") != "accepted"
                    or not _parse_time(review.get("reviewed_at"))
                    or not isinstance(review.get("reviewed_by"), dict)
                    or review["reviewed_by"].get("type") not in {"human", "agent"}
                    or not review["reviewed_by"].get("id")
                ):
                    errors.append(f"{label}: accepted memory requires a review")
                elif (
                    author.get("type") == "agent"
                    and review["reviewed_by"].get("type") == "agent"
                    and review["reviewed_by"].get("id") == author.get("id")
                ):
                    errors.append(f"{label}: an agent cannot accept its own memory")
                elif item.get("type") in {"preference", "decision"} and review["reviewed_by"].get("type") != "human":
                    errors.append(f"{label}: preferences and decisions require human review")
            if item.get("status") == "superseded" and not item.get("superseded_by"):
                errors.append(f"{label}: superseded memory requires superseded_by")
            if _contains_secret(item):
                errors.append(f"{label}: secret-like value detected")
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            for target in item.get("supersedes", []) if isinstance(item.get("supersedes"), list) else []:
                if target not in ids or target == item.get("memory_id"):
                    errors.append(f"memory.json.items[{index}]: invalid supersedes target {target!r}")
            superseded_by = item.get("superseded_by")
            if superseded_by is not None and superseded_by not in ids:
                errors.append(f"memory.json.items[{index}]: invalid superseded_by {superseded_by!r}")
        return errors

    def _valid_source(self, source: str) -> bool:
        if source.startswith("git:"):
            ref = source.removeprefix("git:")
            if not ref:
                return False
            result = subprocess.run(
                ["git", "cat-file", "-e", f"{ref}^{{commit}}"],
                cwd=self.repo_root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return result.returncode == 0
        raw = self.repo_root / source
        try:
            target = raw.resolve()
            target.relative_to(self.repo_root)
        except (OSError, ValueError):
            return False
        return not raw.is_symlink() and target.exists()

    def propose(
        self,
        *,
        memory_type: str,
        scope: str,
        subject: str,
        statement: str,
        source_refs: list[str],
        author_type: str,
        author_id: str,
        evidence_strength: str,
        tags: list[str] | None = None,
        sensitivity: str = "internal",
        valid_until: str | None = None,
        supersedes: list[str] | None = None,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        now = _now()
        item = {
            "memory_id": f"mem-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:10]}",
            "type": memory_type,
            "scope": scope,
            "subject": subject,
            "statement": statement.strip(),
            "status": "proposed",
            "source_refs": source_refs,
            "author": {"type": author_type, "id": author_id},
            "evidence_strength": evidence_strength,
            "tags": tags or [],
            "sensitivity": sensitivity,
            "created_at": now,
            "updated_at": now,
            "valid_from": now,
            "valid_until": valid_until,
            "supersedes": supersedes or [],
            "superseded_by": None,
            "review": None,
        }
        with self.locked():
            document = self.load()
            self._check_revision(document, expected_revision)
            candidate = {**document, "items": [*document.get("items", []), item]}
            errors = self.validate(candidate)
            if errors:
                raise ValueError("; ".join(errors))
            candidate["revision"] = document["revision"] + 1
            candidate["updated_at"] = now
            self._write(candidate)
        return item

    def decide(
        self,
        memory_id: str,
        decision: str,
        *,
        reviewer_type: str,
        reviewer_id: str,
        note: str,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        if decision not in {"accepted", "rejected"}:
            raise ValueError("decision must be accepted or rejected")
        now = _now()
        with self.locked():
            document = self.load()
            self._check_revision(document, expected_revision)
            items = document.get("items", [])
            item = next((entry for entry in items if entry.get("memory_id") == memory_id), None)
            if item is None:
                raise ValueError(f"unknown memory_id: {memory_id}")
            if item.get("status") != "proposed":
                raise ValueError(f"memory {memory_id} is already {item.get('status')}")
            if item.get("type") in {"preference", "decision"} and reviewer_type != "human":
                raise ValueError("preferences and decisions require human review")
            item["status"] = decision
            item["updated_at"] = now
            item["review"] = {
                "decision": decision,
                "reviewed_by": {"type": reviewer_type, "id": reviewer_id},
                "reviewed_at": now,
                "note": note,
            }
            if decision == "accepted":
                for target_id in item.get("supersedes", []):
                    target = next((entry for entry in items if entry.get("memory_id") == target_id), None)
                    if target is None or target.get("status") != "accepted":
                        raise ValueError(f"supersedes target must be accepted: {target_id}")
                    target["status"] = "superseded"
                    target["superseded_by"] = memory_id
                    target["updated_at"] = now
            candidate = {**document, "items": items}
            errors = self.validate(candidate)
            if errors:
                raise ValueError("; ".join(errors))
            candidate["revision"] = document["revision"] + 1
            candidate["updated_at"] = now
            self._write(candidate)
        return item

    @staticmethod
    def _check_revision(document: dict[str, Any], expected: int | None) -> None:
        if expected is not None and document.get("revision") != expected:
            raise MemoryConflictError(
                f"memory revision changed: expected {expected}, current {document.get('revision')}"
            )

    def list_items(
        self,
        *,
        status: str | None = None,
        scope: str | None = None,
        memory_type: str | None = None,
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        items = self.load().get("items", [])
        if not isinstance(items, list):
            return []
        needle = (query or "").casefold()
        output = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if status and item.get("status") != status:
                continue
            if scope and item.get("scope") != scope:
                continue
            if memory_type and item.get("type") != memory_type:
                continue
            tags = item.get("tags") if isinstance(item.get("tags"), list) else []
            haystack = " ".join(
                [str(item.get("subject", "")), str(item.get("statement", "")), *tags]
            ).casefold()
            if needle and needle not in haystack:
                continue
            output.append(item)
        return sorted(output, key=lambda item: (item.get("updated_at", ""), item.get("memory_id", "")), reverse=True)

    def context(
        self,
        *,
        scopes: Iterable[str] = ("global", "job_search"),
        query: str | None = None,
        max_items: int = 20,
        max_chars: int = 12_000,
    ) -> str:
        if max_items < 1 or max_items > 100 or max_chars < 500 or max_chars > 50_000:
            raise ValueError("invalid context bounds")
        scope_set = {"global", *scopes}
        now = datetime.now(timezone.utc)
        needle = (query or "").casefold()
        candidates: list[tuple[int, dict[str, Any]]] = []
        type_priority = {"preference": 6, "decision": 5, "procedure": 4, "fact": 3, "lesson": 2, "open_question": 1}
        items = self.load().get("items", [])
        if not isinstance(items, list):
            items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("status") != "accepted" or item.get("scope") not in scope_set:
                continue
            valid_from = _parse_time(item.get("valid_from"))
            valid_until = _parse_time(item.get("valid_until"))
            if valid_from and valid_from > now:
                continue
            if valid_until and valid_until <= now:
                continue
            tags = item.get("tags") if isinstance(item.get("tags"), list) else []
            haystack = " ".join(
                [str(item.get("subject", "")), str(item.get("statement", "")), *tags]
            ).casefold()
            relevance = 5 if needle and needle in haystack else 0
            scope_score = 3 if item.get("scope") != "global" else 1
            candidates.append((relevance + scope_score + type_priority.get(item.get("type"), 0), item))
        selected = [item for _, item in sorted(candidates, key=lambda pair: (pair[0], pair[1].get("updated_at", "")), reverse=True)[:max_items]]
        lines = ["# ACCEPTED LONG-TERM MEMORY", ""]
        for item in selected:
            lines.append(
                f"- [{item['memory_id']}] ({item['type']} · {item['scope']}) "
                f"{item['subject']}: {item['statement']}"
            )
            lines.append("  sources: " + ", ".join(item.get("source_refs", [])))
        result = "\n".join(lines) + "\n"
        return result[:max_chars]


__all__ = [
    "MemoryStore",
    "MemoryConflictError",
    "MEMORY_TYPES",
    "MEMORY_STATES",
]
