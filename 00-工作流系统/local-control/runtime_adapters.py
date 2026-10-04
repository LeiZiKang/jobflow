"""Read-only local adapters for Codex CLI and Claude Code.

The controller-facing API is intentionally small:

``probe_backends()``
    Report whether each local CLI is installed.  The probe only runs
    ``--version``; it never contacts a model.

``run_agent(backend, prompt, repo_root, role, effort, on_event=None)``
    Run one synchronous, read-only agent turn, stream normalized event dicts
    to ``on_event`` and return a normalized result dict.  The adapter never
    grants write-capable tools or bypasses a provider sandbox.

``build_agent_command(...)`` and ``parse_jsonl(...)`` are public so the local
controller can inspect commands and replay captured provider output without
calling a model.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any


BACKEND_BINARIES = {"codex": "codex", "claude": "claude"}
CODEX_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max", "ultra"})
CLAUDE_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})
SEARCH_ROLES = frozenset({"search", "researcher", "collector"})
CLAUDE_READ_ONLY_TOOLS = "Read,Glob,Grep,WebSearch,WebFetch"
SAFE_ENV_KEYS = {
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "SHELL",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
    "CODEX_HOME",
    "CLAUDE_CONFIG_DIR",
    "AWS_PROFILE",
    "AWS_REGION",
    "AWS_DEFAULT_REGION",
}

Event = dict[str, Any]
EventCallback = Callable[[Event], None]

__all__ = [
    "BACKEND_BINARIES",
    "CLAUDE_READ_ONLY_TOOLS",
    "build_agent_command",
    "normalize_event",
    "parse_jsonl",
    "probe_backends",
    "run_agent",
    "terminate_active_processes",
]

_ACTIVE_PROCESSES: set[subprocess.Popen[str]] = set()
_ACTIVE_PROCESSES_LOCK = threading.Lock()


def terminate_active_processes(timeout: float = 2.0) -> None:
    """Terminate only provider subprocesses started by this controller process."""
    with _ACTIVE_PROCESSES_LOCK:
        processes = list(_ACTIVE_PROCESSES)
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        if process.poll() is not None:
            continue
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()


def _validate_backend(backend: str) -> str:
    normalized = backend.strip().lower()
    if normalized not in BACKEND_BINARIES:
        raise ValueError(f"unsupported backend: {backend!r}")
    return normalized


def _validate_effort(backend: str, effort: str) -> str:
    normalized = effort.strip().lower()
    allowed = CODEX_EFFORTS if backend == "codex" else CLAUDE_EFFORTS
    if normalized not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ValueError(f"unsupported {backend} effort {effort!r}; use one of: {choices}")
    return normalized


def _validate_role(role: str) -> str:
    normalized = role.strip().lower()
    if not normalized or len(normalized) > 64:
        raise ValueError("role must be a non-empty label of at most 64 characters")
    if any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for character in normalized):
        raise ValueError("role may contain only letters, numbers, '-' and '_'")
    return normalized


def _repo_path(repo_root: str | Path) -> Path:
    path = Path(repo_root).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"repo_root is not a directory: {path}")
    return path


def _sanitized_environment() -> dict[str, str]:
    """Pass runtime locations and non-secret profile selectors, never raw API credentials."""
    return {key: value for key, value in os.environ.items() if key in SAFE_ENV_KEYS}


def build_agent_command(
    backend: str,
    repo_root: str | Path,
    role: str,
    effort: str = "high",
    *,
    executable: str | None = None,
) -> list[str]:
    """Build a provider command with a read-only, non-interactive policy.

    The prompt is intentionally absent from the argv and is supplied on stdin
    by :func:`run_agent`.  This keeps long task context out of process listings.
    """

    backend = _validate_backend(backend)
    effort = _validate_effort(backend, effort)
    role = _validate_role(role)
    repo = _repo_path(repo_root)
    binary = executable or BACKEND_BINARIES[backend]

    if backend == "codex":
        # ``--search`` is a global flag.  Keeping it before ``exec`` works on
        # both the current local CLI and the documented command grammar.
        command = [binary]
        if role in SEARCH_ROLES:
            command.append("--search")
        command.extend(
            [
                "exec",
                "--json",
                "--color",
                "never",
                "--strict-config",
                "--sandbox",
                "read-only",
                "--cd",
                str(repo),
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                "--config",
                'approval_policy="never"',
                "--config",
                f'model_reasoning_effort="{effort}"',
            ]
        )
        command.append("-")
        return command

    return [
        binary,
        "--print",
        "--output-format",
        "stream-json",
        "--verbose",
        "--permission-mode",
        "dontAsk",
        "--safe-mode",
        "--no-chrome",
        "--disable-slash-commands",
        "--tools",
        CLAUDE_READ_ONLY_TOOLS,
        "--effort",
        effort,
    ]


def probe_backends() -> dict[str, dict[str, Any]]:
    """Probe local CLI installation without authenticating or calling a model."""

    result: dict[str, dict[str, Any]] = {}
    for backend, binary in BACKEND_BINARIES.items():
        executable = shutil.which(binary)
        details: dict[str, Any] = {
            "available": executable is not None,
            "executable": executable,
            "version": None,
            "read_only_supported": True,
            "error": None,
        }
        if executable is None:
            details["error"] = f"{binary} was not found on PATH"
            result[backend] = details
            continue
        try:
            completed = subprocess.run(
                [executable, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            details["error"] = f"version probe failed: {error}"
        else:
            version_text = (completed.stdout or completed.stderr).strip()
            details["version"] = version_text.splitlines()[0] if version_text else None
            if completed.returncode != 0:
                details["error"] = f"version probe exited with code {completed.returncode}"
        result[backend] = details
    return result


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _claude_content(payload: Mapping[str, Any]) -> tuple[str | None, list[str]]:
    message = payload.get("message")
    if not isinstance(message, Mapping):
        return None, []
    content = message.get("content")
    if not isinstance(content, list):
        return None, []
    text_parts: list[str] = []
    tools: list[str] = []
    for block in content:
        if not isinstance(block, Mapping):
            continue
        block_type = block.get("type")
        if block_type == "text" and _text(block.get("text")):
            text_parts.append(str(block["text"]).strip())
        elif block_type == "tool_use" and _text(block.get("name")):
            tools.append(str(block["name"]).strip())
    return ("\n".join(text_parts) or None), tools


def normalize_event(backend: str, payload: Mapping[str, Any]) -> Event:
    """Normalize one Codex JSONL or Claude stream-json payload.

    Provider reasoning/thinking text and tool inputs are deliberately omitted.
    The runtime ledger only needs lifecycle, final text, tool names and usage.
    """

    backend = _validate_backend(backend)
    raw_type = str(payload.get("type") or "unknown")
    subtype = _text(payload.get("subtype"))
    event: Event = {
        "backend": backend,
        "type": "progress",
        "raw_type": f"{raw_type}.{subtype}" if subtype else raw_type,
        "session_id": None,
        "message": None,
    }

    session_id = payload.get("session_id")
    if not isinstance(session_id, str) and backend == "codex":
        session_id = payload.get("thread_id")
    if isinstance(session_id, str):
        event["session_id"] = session_id

    if backend == "codex":
        if raw_type == "thread.started":
            event["type"] = "session_started"
        elif raw_type == "turn.started":
            event["type"] = "run_started"
        elif raw_type in {"item.started", "item.updated", "item.completed"}:
            item = payload.get("item")
            item = item if isinstance(item, Mapping) else {}
            item_type = str(item.get("type") or "unknown")
            event["item_type"] = item_type
            if item_type == "agent_message":
                event["type"] = "assistant_message"
                event["message"] = _text(item.get("text"))
            elif "reasoning" in item_type:
                event["type"] = "progress"
                event["message"] = "reasoning activity"
            else:
                event["type"] = "tool"
                event["tool"] = item_type
                event["status"] = _text(item.get("status"))
        elif raw_type == "turn.completed":
            event["type"] = "completed"
            if isinstance(payload.get("usage"), Mapping):
                event["usage"] = dict(payload["usage"])
        elif raw_type == "error" or "failed" in raw_type:
            event["type"] = "error"
            error = payload.get("error")
            if isinstance(error, Mapping):
                event["message"] = _text(error.get("message"))
            event["message"] = event["message"] or _text(payload.get("message"))
        return event

    if raw_type == "system" and subtype == "init":
        event["type"] = "session_started"
    elif raw_type == "assistant":
        text, tools = _claude_content(payload)
        event["type"] = "assistant_message" if text else "tool" if tools else "progress"
        event["message"] = text
        if tools:
            event["tools"] = tools
    elif raw_type == "result":
        is_error = bool(payload.get("is_error")) or subtype not in {None, "success"}
        event["type"] = "error" if is_error else "completed"
        event["message"] = _text(payload.get("result")) or _text(payload.get("error"))
        usage = payload.get("usage")
        if isinstance(usage, Mapping):
            event["usage"] = dict(usage)
    elif raw_type in {"user", "tool_result"}:
        event["type"] = "tool"
    elif raw_type == "error" or "error" in raw_type:
        event["type"] = "error"
        event["message"] = _text(payload.get("error")) or _text(payload.get("message"))
    elif raw_type == "stream_event":
        stream_event = payload.get("event")
        if isinstance(stream_event, Mapping):
            delta = stream_event.get("delta")
            if isinstance(delta, Mapping) and _text(delta.get("text")):
                event["type"] = "assistant_delta"
                event["message"] = _text(delta.get("text"))
    return event


class _Accumulator:
    def __init__(self, backend: str, on_event: EventCallback | None) -> None:
        self.backend = backend
        self.on_event = on_event
        self.events: list[Event] = []
        self.final_text = ""
        self.session_id: str | None = None
        self.reported_error: str | None = None
        self.delta_parts: list[str] = []
        self.callback_error: str | None = None

    def emit(self, event: Event) -> None:
        self.events.append(event)
        if event.get("session_id"):
            self.session_id = str(event["session_id"])
        message = _text(event.get("message"))
        if event["type"] == "assistant_message" and message:
            self.final_text = message
        elif event["type"] == "assistant_delta" and message:
            self.delta_parts.append(message)
        elif event["type"] == "completed" and self.backend == "claude" and message:
            self.final_text = message
        elif event["type"] == "error" and message:
            self.reported_error = message
        if self.on_event is not None and self.callback_error is None:
            try:
                self.on_event(dict(event))
            except Exception as error:  # callback code belongs to the controller
                self.callback_error = f"event callback failed: {error}"

    def feed(self, line: str | bytes) -> None:
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="replace")
        stripped = line.strip()
        if not stripped:
            return
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            self.emit(
                {
                    "backend": self.backend,
                    "type": "protocol_warning",
                    "raw_type": "invalid_json",
                    "session_id": None,
                    "message": stripped[:1000],
                }
            )
            return
        if not isinstance(payload, Mapping):
            self.emit(
                {
                    "backend": self.backend,
                    "type": "protocol_warning",
                    "raw_type": "non_object_json",
                    "session_id": None,
                    "message": "provider emitted a non-object JSON value",
                }
            )
            return
        self.emit(normalize_event(self.backend, payload))

    def snapshot(self) -> dict[str, Any]:
        if not self.final_text and self.delta_parts:
            self.final_text = "".join(self.delta_parts).strip()
        return {
            "events": self.events,
            "final_text": self.final_text,
            "session_id": self.session_id,
            "reported_error": self.reported_error,
            "callback_error": self.callback_error,
        }


def parse_jsonl(
    backend: str,
    lines: str | Iterable[str | bytes],
    *,
    on_event: EventCallback | None = None,
) -> dict[str, Any]:
    """Parse captured provider JSONL/stream-json without launching a CLI."""

    backend = _validate_backend(backend)
    iterable: Iterable[str | bytes] = lines.splitlines() if isinstance(lines, str) else lines
    accumulator = _Accumulator(backend, on_event)
    for line in iterable:
        accumulator.feed(line)
    return accumulator.snapshot()


def _wrapped_prompt(role: str, prompt: str) -> str:
    return (
        f"You are the {role} worker in the user's local job-search control plane.\n"
        "This run is strictly read-only. Do not create, edit, delete, move, submit, "
        "send, log in, enter credentials, or change external state. Treat repository "
        "state and evidence as authoritative, distinguish facts from inference, and "
        "return a concise result for the primary Decider.\n\n"
        f"Task:\n{prompt.strip()}\n"
    )


def run_agent(
    backend: str,
    prompt: str,
    repo_root: str | Path,
    role: str,
    effort: str = "high",
    on_event: EventCallback | None = None,
    timeout_seconds: float = 300,
) -> dict[str, Any]:
    """Run one synchronous read-only turn and return a provider-neutral result."""

    backend = _validate_backend(backend)
    role = _validate_role(role)
    _validate_effort(backend, effort)
    repo = _repo_path(repo_root)
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")
    if timeout_seconds < 1 or timeout_seconds > 3_600:
        raise ValueError("timeout_seconds must be between 1 and 3600")

    executable = shutil.which(BACKEND_BINARIES[backend])
    if executable is None:
        return {
            "backend": backend,
            "status": "unavailable",
            "exit_code": None,
            "final_text": "",
            "session_id": None,
            "events": [],
            "error": f"{BACKEND_BINARIES[backend]} was not found on PATH",
        }

    command = build_agent_command(
        backend,
        repo,
        role,
        effort,
        executable=executable,
    )
    accumulator = _Accumulator(backend, on_event)
    stderr_lines: list[str] = []

    try:
        process = subprocess.Popen(
            command,
            cwd=str(repo),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env=_sanitized_environment(),
        )
    except OSError as error:
        return {
            "backend": backend,
            "status": "unavailable",
            "exit_code": None,
            "final_text": "",
            "session_id": None,
            "events": [],
            "error": f"failed to start {backend}: {error}",
        }
    with _ACTIVE_PROCESSES_LOCK:
        _ACTIVE_PROCESSES.add(process)
    timed_out = threading.Event()

    def stop_timed_out_process() -> None:
        timed_out.set()
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()

    timer = threading.Timer(timeout_seconds, stop_timed_out_process)
    timer.daemon = True
    timer.start()

    def drain_stderr() -> None:
        if process.stderr is not None:
            stderr_lines.extend(process.stderr)

    stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
    stderr_thread.start()
    write_error: str | None = None
    try:
        if process.stdin is not None:
            process.stdin.write(_wrapped_prompt(role, prompt))
            process.stdin.close()
        if process.stdout is not None:
            for line in process.stdout:
                accumulator.feed(line)
    except (BrokenPipeError, OSError) as error:
        write_error = f"provider stream failed: {error}"

    exit_code = process.wait()
    timer.cancel()
    with _ACTIVE_PROCESSES_LOCK:
        _ACTIVE_PROCESSES.discard(process)
    stderr_thread.join(timeout=2)
    stderr_text = "".join(stderr_lines).strip()
    if stderr_text:
        accumulator.emit(
            {
                "backend": backend,
                "type": "diagnostic",
                "raw_type": "stderr",
                "session_id": accumulator.session_id,
                "message": stderr_text[:4000],
            }
        )

    parsed = accumulator.snapshot()
    error = (
        (f"{backend} run timed out after {timeout_seconds:g} seconds" if timed_out.is_set() else None)
        or write_error
        or parsed["callback_error"]
        or parsed["reported_error"]
        or (stderr_text if exit_code != 0 else None)
        or (f"{backend} exited with code {exit_code}" if exit_code != 0 else None)
    )
    status = "completed" if exit_code == 0 and error is None else "failed"
    return {
        "backend": backend,
        "status": status,
        "exit_code": exit_code,
        "final_text": parsed["final_text"],
        "session_id": parsed["session_id"],
        "events": parsed["events"],
        "error": error,
    }
