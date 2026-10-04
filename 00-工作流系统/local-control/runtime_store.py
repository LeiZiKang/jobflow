#!/usr/bin/env python3
"""Disposable SQLite runtime ledger for the local jobflow controller.

The Git repository remains the canonical business state.  This module only
records ephemeral agent runs and their event stream.  It deliberately has no
API for changing files under ``state/`` and rejects credentials rather than
turning the runtime database into a secret store.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping


SCHEMA_VERSION = 1
DEFAULT_BUSY_TIMEOUT_MS = 5_000


class RuntimeStoreError(RuntimeError):
    """Base error for the runtime ledger."""


class RunNotFoundError(RuntimeStoreError):
    """Raised when a run referenced by an operation does not exist."""


class SecretValueError(RuntimeStoreError):
    """Raised when data looks like a credential rather than a safe reference."""


_SENSITIVE_KEYS = {
    "password",
    "passwd",
    "pwd",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "cookie",
    "cookies",
    "authorization",
    "credential",
    "credentials",
    "client_secret",
    "private_key",
    "secret",
}
_SECRET_TEXT_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:authorization|cookie)\s*:\s*(?!secret://)\S+"),
    re.compile(
        r"(?i)\b(?:password|passwd|api[_-]?key|access[_-]?token|"
        r"refresh[_-]?token)\s*[:=]\s*(?!secret://)\S+"
    ),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bgh(?:p|o|u|s|r)_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{16,}\b"),
    re.compile(r"\bxox(?:b|p|a|r|s)-[A-Za-z0-9-]{12,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
)


def _is_sensitive_key(key: str) -> bool:
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", key.strip())
    normalized = snake.lower().replace("-", "_")
    if normalized in _SENSITIVE_KEYS:
        return True
    return any(
        normalized.endswith(f"_{suffix}")
        for suffix in (
            "password",
            "passwd",
            "token",
            "api_key",
            "cookie",
            "authorization",
            "credential",
            "client_secret",
            "private_key",
            "secret",
        )
    )


_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    parent_run_id TEXT REFERENCES runs(run_id) ON DELETE RESTRICT,
    mode TEXT NOT NULL,
    role TEXT NOT NULL,
    backend TEXT NOT NULL,
    status TEXT NOT NULL,
    prompt TEXT,
    final_text TEXT,
    error TEXT,
    task_id TEXT,
    session_id TEXT,
    model TEXT,
    effort TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (parent_run_id IS NULL OR parent_run_id <> run_id)
);

CREATE INDEX IF NOT EXISTS idx_runs_parent_created
    ON runs(parent_run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_status_updated
    ON runs(status, updated_at DESC);

CREATE TABLE IF NOT EXISTS run_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(run_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_run_events_run_sequence
    ON run_events(run_id, sequence);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_json(value: Any, *, field: str) -> str:
    _reject_secret(value, path=field)
    try:
        return json.dumps(
            {} if value is None else value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be JSON serializable") from exc


def _reject_secret(value: Any, *, path: str) -> None:
    """Reject credential-shaped values while allowing ``secret://`` references."""

    if value is None or isinstance(value, (bool, int, float)):
        return
    if isinstance(value, str):
        if value.startswith("secret://"):
            return
        for pattern in _SECRET_TEXT_PATTERNS:
            if pattern.search(value):
                raise SecretValueError(
                    f"{path} appears to contain a credential; store only secret:// references"
                )
        return
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key)
            child_path = f"{path}.{key}"
            if _is_sensitive_key(key) and child is not None:
                if not (isinstance(child, str) and child.startswith("secret://")):
                    raise SecretValueError(
                        f"{child_path} is a secret field; store only a secret:// reference"
                    )
            _reject_secret(child, path=child_path)
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_secret(child, path=f"{path}[{index}]")
        return


class RuntimeStore:
    """Thread-safe run/event ledger using one SQLite connection per operation."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    ) -> None:
        self.db_path = Path(db_path).expanduser()
        if str(self.db_path) == ":memory:":
            raise ValueError(":memory: is incompatible with per-operation connections")
        if busy_timeout_ms <= 0:
            raise ValueError("busy_timeout_ms must be positive")
        self.busy_timeout_ms = int(busy_timeout_ms)
        self._init_lock = threading.Lock()
        self._initialize()

    def _new_connection(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            self.db_path,
            timeout=self.busy_timeout_ms / 1_000,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
        return connection

    def _initialize(self) -> None:
        with self._init_lock:
            connection = self._new_connection()
            try:
                journal_mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
                if str(journal_mode).lower() != "wal":
                    raise RuntimeStoreError(
                        f"SQLite refused WAL mode for {self.db_path}: {journal_mode}"
                    )
                connection.executescript(_SCHEMA)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            finally:
                connection.close()

    def _ensure_database(self) -> None:
        # The runtime ledger is intentionally disposable.  Recreate it even when
        # the file is removed while this store object remains alive.
        if not self.db_path.exists():
            self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        self._ensure_database()
        connection = self._new_connection()
        try:
            yield connection
        finally:
            connection.close()

    def create_run(
        self,
        run_id: str | None = None,
        *,
        parent_run_id: str | None = None,
        mode: str = "primary",
        role: str = "decider",
        backend: str = "local",
        status: str = "queued",
        prompt: str | None = None,
        final_text: str | None = None,
        error: str | None = None,
        task_id: str | None = None,
        session_id: str | None = None,
        model: str | None = None,
        effort: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create and return a run, optionally linked to an existing parent."""

        run_id = run_id or f"run-{uuid.uuid4().hex}"
        required = {
            "run_id": run_id,
            "mode": mode,
            "role": role,
            "backend": backend,
            "status": status,
        }
        for field, value in required.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} must be a non-empty string")
        for field, value in {
            "prompt": prompt,
            "final_text": final_text,
            "error": error,
        }.items():
            _reject_secret(value, path=field)
        metadata_json = _safe_json(metadata, field="metadata")
        now = _utc_now()
        with self._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                if parent_run_id is not None:
                    parent = connection.execute(
                        "SELECT 1 FROM runs WHERE run_id = ?", (parent_run_id,)
                    ).fetchone()
                    if parent is None:
                        raise RunNotFoundError(f"parent run not found: {parent_run_id}")
                connection.execute(
                    """
                    INSERT INTO runs (
                        run_id, parent_run_id, mode, role, backend, status,
                        prompt, final_text, error, task_id, session_id, model,
                        effort, metadata_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        parent_run_id,
                        mode,
                        role,
                        backend,
                        status,
                        prompt,
                        final_text,
                        error,
                        task_id,
                        session_id,
                        model,
                        effort,
                        metadata_json,
                        now,
                        now,
                    ),
                )
                connection.commit()
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
        result = self.get_run(run_id)
        assert result is not None
        return result

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Return one run, or ``None`` when it is absent."""

        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return self._run_dict(row) if row is not None else None

    def list_runs(
        self,
        *,
        status: str | None = None,
        parent_run_id: str | None = None,
        roots_only: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List newest runs with optional status or parent filtering."""

        if limit <= 0 or limit > 1_000:
            raise ValueError("limit must be between 1 and 1000")
        if parent_run_id is not None and roots_only:
            raise ValueError("parent_run_id and roots_only are mutually exclusive")
        clauses: list[str] = []
        parameters: list[Any] = []
        if status is not None:
            clauses.append("status = ?")
            parameters.append(status)
        if parent_run_id is not None:
            clauses.append("parent_run_id = ?")
            parameters.append(parent_run_id)
        elif roots_only:
            clauses.append("parent_run_id IS NULL")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(limit)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM runs"
                f"{where} ORDER BY created_at DESC, run_id DESC LIMIT ?",
                parameters,
            ).fetchall()
        return [self._run_dict(row) for row in rows]

    def update_run(self, run_id: str, **changes: Any) -> dict[str, Any]:
        """Update mutable execution fields and return the resulting run."""

        allowed = {
            "mode",
            "role",
            "backend",
            "status",
            "prompt",
            "final_text",
            "error",
            "task_id",
            "session_id",
            "model",
            "effort",
            "metadata",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"unknown run fields: {', '.join(sorted(unknown))}")
        if not changes:
            result = self.get_run(run_id)
            if result is None:
                raise RunNotFoundError(f"run not found: {run_id}")
            return result

        assignments: list[str] = []
        parameters: list[Any] = []
        for field, value in changes.items():
            if field in {"mode", "role", "backend", "status"}:
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{field} must be a non-empty string")
            if field in {"prompt", "final_text", "error"}:
                _reject_secret(value, path=field)
            column = "metadata_json" if field == "metadata" else field
            stored = _safe_json(value, field="metadata") if field == "metadata" else value
            assignments.append(f"{column} = ?")
            parameters.append(stored)
        assignments.append("updated_at = ?")
        parameters.append(_utc_now())
        parameters.append(run_id)

        with self._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    f"UPDATE runs SET {', '.join(assignments)} WHERE run_id = ?",
                    parameters,
                )
                if cursor.rowcount != 1:
                    raise RunNotFoundError(f"run not found: {run_id}")
                connection.commit()
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
        result = self.get_run(run_id)
        assert result is not None
        return result

    def append_event(
        self,
        run_id: str,
        event_type: str,
        payload: Mapping[str, Any] | list[Any] | None = None,
        *,
        message: str | None = None,
    ) -> dict[str, Any]:
        """Atomically append an event with a monotonically increasing run sequence."""

        if not isinstance(event_type, str) or not event_type.strip():
            raise ValueError("event_type must be a non-empty string")
        _reject_secret(message, path="message")
        payload_json = _safe_json(payload, field="payload")
        created_at = _utc_now()
        with self._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                exists = connection.execute(
                    "SELECT 1 FROM runs WHERE run_id = ?", (run_id,)
                ).fetchone()
                if exists is None:
                    raise RunNotFoundError(f"run not found: {run_id}")
                sequence = connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 FROM run_events WHERE run_id = ?",
                    (run_id,),
                ).fetchone()[0]
                cursor = connection.execute(
                    """
                    INSERT INTO run_events (
                        run_id, sequence, event_type, message, payload_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (run_id, sequence, event_type, message, payload_json, created_at),
                )
                event_id = cursor.lastrowid
                connection.execute(
                    "UPDATE runs SET updated_at = ? WHERE run_id = ?",
                    (created_at, run_id),
                )
                connection.commit()
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
        return {
            "event_id": event_id,
            "run_id": run_id,
            "sequence": sequence,
            "event_type": event_type,
            "message": message,
            "payload": json.loads(payload_json),
            "created_at": created_at,
        }

    def list_events(
        self,
        run_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Return a run's event stream in sequence order."""

        if after_sequence < 0:
            raise ValueError("after_sequence must be non-negative")
        if limit <= 0 or limit > 5_000:
            raise ValueError("limit must be between 1 and 5000")
        with self._connection() as connection:
            exists = connection.execute(
                "SELECT 1 FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if exists is None:
                raise RunNotFoundError(f"run not found: {run_id}")
            rows = connection.execute(
                """
                SELECT * FROM run_events
                WHERE run_id = ? AND sequence > ?
                ORDER BY sequence ASC
                LIMIT ?
                """,
                (run_id, after_sequence, limit),
            ).fetchall()
        return [self._event_dict(row) for row in rows]

    @staticmethod
    def _run_dict(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["metadata"] = json.loads(result.pop("metadata_json"))
        return result

    @staticmethod
    def _event_dict(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["payload"] = json.loads(result.pop("payload_json"))
        return result


__all__ = [
    "RuntimeStore",
    "RuntimeStoreError",
    "RunNotFoundError",
    "SecretValueError",
]
