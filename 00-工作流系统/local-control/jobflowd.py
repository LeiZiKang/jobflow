#!/usr/bin/env python3
"""Local-only runtime controller for read-only Codex and Claude agent runs."""

from __future__ import annotations

import argparse
import html
import json
import os
import secrets
import signal
import sys
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from context_builder import evaluator_prompt, search_prompt
from jobflow_memory import MemoryStore
from jobflow_paths import default_runtime_dir
from jobflow_progress import phone_prep_path
from jobflow_today import build_today, read_manifests
from runtime_adapters import probe_backends, run_agent, terminate_active_processes
from runtime_store import RunNotFoundError, RuntimeStore


DEFAULT_REPO = Path(__file__).resolve().parents[2]
# runtime 必须落在 iCloud 之外，理由见 bin/jobflow_paths.py
DEFAULT_RUNTIME_DIR = default_runtime_dir()
MAX_REQUEST_BYTES = 128 * 1024
MAX_PROMPT_CHARS = 12_000
TERMINAL_RUN_STATES = {"completed", "failed", "interrupted", "unavailable"}
POST_SUBMISSION_STATES = {
    "submitted_verified",
    "follow_up_due",
    "interviewing",
    "offer",
    "rejected",
    "withdrawn",
    "closed",
}
DOCUMENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
DOCUMENT_ROOTS = {"02-策略", "03-简历", "04-面试", "05-检索报告", "06-证据"}


class LocalController:
    def update_status(self) -> dict:
        from jobflow_update import cached_status
        return cached_status(self.repo_root, self.update_runtime)

    def __init__(self, repo_root: Path, db_path: Path, max_workers: int = 6) -> None:
        self.repo_root = repo_root.resolve()
        self.update_runtime = db_path.parent
        self.store = RuntimeStore(db_path)
        self.memory_store = MemoryStore(self.repo_root / "00-工作流系统")
        self.pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="jobflow-run")
        self.orchestrator_pool = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="jobflow-orchestrator"
        )
        self._futures: dict[str, Future] = {}
        self._lock = threading.Lock()
        self._closing = threading.Event()
        probes = probe_backends()
        self._probes = probes
        self._backend_health = {
            backend: "installed_unverified" if details.get("available") else "unavailable"
            for backend, details in probes.items()
        }
        self._mark_abandoned_runs()
        for run in self.store.list_runs(limit=200):
            backend = run.get("backend")
            if backend in self._backend_health and self._backend_health[backend] == "installed_unverified":
                health = self._health_from_result(str(run.get("status") or ""), run.get("error"))
                if health != "degraded" or run.get("status") in TERMINAL_RUN_STATES:
                    self._backend_health[backend] = health

    def begin_shutdown(self) -> None:
        self._closing.set()
        terminate_active_processes()

    def close(self) -> None:
        self.begin_shutdown()
        self.orchestrator_pool.shutdown(wait=True, cancel_futures=True)
        self.pool.shutdown(wait=True, cancel_futures=True)

    def _track_future(self, run_id: str, future: Future) -> None:
        with self._lock:
            self._futures[run_id] = future

        def discard(_: Future) -> None:
            with self._lock:
                self._futures.pop(run_id, None)

        future.add_done_callback(discard)

    @staticmethod
    def _health_from_result(status: str, error: object) -> str:
        if status == "completed":
            return "ready"
        if error and any(
            marker in str(error).lower()
            for marker in ("expired", "reauthenticate", "unauthorized", "login required")
        ):
            return "auth_required"
        return "degraded"

    def _mark_abandoned_runs(self) -> None:
        for status in ("queued", "running"):
            for run in self.store.list_runs(status=status, limit=1_000):
                self.store.update_run(
                    run["run_id"],
                    status="interrupted",
                    error="Local controller restarted before this run completed.",
                )
                self.store.append_event(
                    run["run_id"],
                    "run_interrupted",
                    message="Controller restart detected; no external action was retried.",
                )

    def agents(self) -> list[dict]:
        return [
            {
                "agent_id": f"runtime-{backend}",
                "name": "Codex" if backend == "codex" else "Claude",
                "role": "可作为 Primary 或只读 Search Agent",
                "backend": backend,
                "model": "由本机账号配置决定",
                "effort": "max" if backend == "codex" else "max",
                "status": self._backend_health.get(backend, "unavailable"),
                "version": details.get("version"),
                "error": details.get("error"),
            }
            for backend, details in self._probes.items()
        ]

    def _load_state(self, name: str) -> dict:
        path = self.repo_root / "00-工作流系统/state" / name
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"state file must contain an object: {name}")
        return value

    def overview(self) -> dict:
        current = self._load_state("current.json")
        tasks = self._load_state("task_queue.json").get("tasks", [])
        active = self._load_state("active_decider.json")
        applications = self._load_state("applications.json").get("applications", [])
        tasks = tasks if isinstance(tasks, list) else []
        applications = applications if isinstance(applications, list) else []
        next_actions = sorted(
            [item for item in tasks if isinstance(item, dict) and item.get("status") not in {"done", "cancelled"}],
            key=lambda item: (item.get("priority", 999), item.get("task_id", "")),
        )
        return {
            "objective": current.get("ultimate_goal"),
            "phase": current.get("current_phase"),
            "updated_at": current.get("updated_at"),
            "metrics": {
                **(current.get("metrics") or {}),
                "interviewing": sum(item.get("status") == "interviewing" for item in applications if isinstance(item, dict)),
                "awaiting_user": sum(item.get("status") == "waiting_user" for item in next_actions),
            },
            "next_actions": next_actions,
            "active_decider": {
                "agent_id": active.get("agent") or "unclaimed",
                "name": active.get("agent") or "未领取",
                "backend": active.get("backend"),
                "status": active.get("status"),
                "lease_expires_at": active.get("lease_expires_at"),
            },
        }

    def applications(self) -> list[dict]:
        rows = self._load_state("applications.json").get("applications", [])
        output: list[dict] = []
        for item in rows if isinstance(rows, list) else []:
            if not isinstance(item, dict):
                continue
            case = item.get("case") or {}
            view_path = case.get("view_path") if isinstance(case, dict) else None
            phone_path = phone_prep_path(self.repo_root, item)
            output.append(
                {
                    **item,
                    "view_url": self._document_url(view_path),
                    "phone_prep_available": bool(phone_path),
                    "phone_prep_url": self._document_url(phone_path),
                }
            )
        return output

    def _document_url(self, relative: object, *, root: str | None = None, suffix: str | None = None) -> str | None:
        if not isinstance(relative, str) or not relative or ".." in Path(relative).parts:
            return None
        if root and Path(relative).parts[0] != root:
            return None
        try:
            target, _ = self.resolve_document(relative)
            if suffix and target.suffix.lower() != suffix:
                return None
            raw = self.repo_root / relative
            if any(part.is_symlink() for part in [raw, *raw.parents] if part != self.repo_root and self.repo_root in part.parents):
                return None
        except (ValueError, OSError):
            return None
        return f"/api/document?path={quote(relative, safe='')}"

    def materials(self) -> dict:
        """Only explicit private registry entries; never enumerate resume files."""
        if not (self.repo_root / "00-工作流系统/state/personal_materials.json").is_file():
            return {"resumes": []}
        document = self._load_state("personal_materials.json")
        if document.get("schema_version") != 1 or not isinstance(document.get("resumes"), list):
            raise ValueError("invalid personal materials registry")
        rows = []
        seen = set()
        for item in document["resumes"]:
            if not isinstance(item, dict) or any(not isinstance(item.get(key), str) or not item[key].strip() for key in ("id", "label", "language")):
                raise ValueError("invalid resume registry entry")
            if item["id"] in seen:
                raise ValueError("duplicate resume registry id")
            seen.add(item["id"])
            url = self._document_url(item.get("path"), root="03-简历", suffix=".pdf")
            rows.append({"id": item["id"], "label": item["label"], "language": item["language"],
                         "available": bool(url), "view_url": url,
                         "source_url": self._document_url(item.get("source_path"), root="03-简历"),
                         "reason": None if url else "登记的 PDF 不存在或不在允许的材料路径内"})
        return {"resumes": rows}

    def today(self) -> dict:
        return build_today(self.applications(), self.repo_root)

    def submission_evidence(self, application_id: str) -> bytes:
        app = next((a for a in self.applications() if a.get("application_id") == application_id), None)
        if app is None:
            raise ValueError("unknown application")
        e = lambda value: html.escape(str(value or "未记录"))
        body = f'<h1>{e(app.get("company"))} · 投递证据</h1><p>{e(app.get("role"))}</p><p>当前状态：{e(app.get("status"))} · 提交日期：{e(app.get("submitted_at"))}</p>'
        body += '<p>这里只展示该申请登记的证据；发送消息、准备材料不等于已核实投递。</p>'
        if app.get("platform_readback"):
            body += f'<h2>登记的平台回读</h2><pre>{e(app["platform_readback"])}</pre>'
        manifests = read_manifests(self.repo_root, app)
        for ref, manifest in manifests:
            result = manifest.get("result") or {}
            if not isinstance(result, dict):
                continue
            body += f'<section><h2>{e(manifest.get("operation_type"))}</h2><p>{e(manifest.get("occurred_at"))} · {e(result.get("status"))}</p><pre>{e(result.get("platform_readback"))}</pre><p>来源：{e(ref)}</p></section>'
        body += '<h2>其他登记来源</h2><ul>'
        for ref in app.get("evidence_refs", []):
            url = self._document_url(ref)
            body += '<li>' + (f'<a href="{e(url)}">{e(ref)}</a>' if url else e(ref)) + '</li>'
        body += '</ul>'
        return f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>投递证据</title><style>:root{{color-scheme:dark;background:#191b20;color:#eef0f4}}body{{max-width:900px;margin:auto;padding:24px;font:16px/1.7 system-ui}}pre{{white-space:pre-wrap}}a{{color:#9bc9ff}}p,li,pre{{overflow-wrap:anywhere}}section{{border-top:1px solid #777;padding:16px 0}}@media(prefers-color-scheme:light){{:root{{color-scheme:light;background:#fff;color:#222}}a{{color:#165ca4}}}}</style><body>{body}</body></html>'.encode("utf-8")

    def memory(self) -> dict:
        document = self.memory_store.load()
        errors = self.memory_store.validate(document)
        if errors:
            raise ValueError("; ".join(errors))
        items = self.memory_store.list_items()
        return {
            "schema_version": document.get("schema_version"),
            "revision": document.get("revision"),
            "updated_at": document.get("updated_at"),
            "items": items,
            "counts": {
                status: sum(item.get("status") == status for item in items)
                for status in ("accepted", "proposed", "rejected", "superseded")
            },
            "context_preview": self.memory_store.context(
                scopes=["job_search"], max_items=20, max_chars=12_000
            ),
        }

    def reports(self) -> list[dict]:
        base = self.repo_root / "05-检索报告"
        rows: list[dict] = []
        for path in base.rglob("*.html") if base.is_dir() else []:
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(self.repo_root).as_posix()
            rows.append(
                {
                    "report_id": relative,
                    "title": ("主动联系日报 · 日期索引" if path.stem == "index" else f"主动联系日报 · {path.stem}") if "/主动联系日报/" in relative else path.stem,
                    "kind": "主动联系日报" if "/主动联系日报/" in relative else "岗位档案" if "岗位档案/" in relative else "检索报告",
                    "path": relative,
                    "modified_at": datetime.fromtimestamp(
                        path.stat().st_mtime, tz=timezone.utc
                    ).isoformat(),
                    "view_url": f"/api/document?path={quote(relative, safe='')}",
                }
            )
        return sorted(rows, key=lambda item: item["modified_at"], reverse=True)

    def resolve_document(self, relative: str) -> tuple[Path, str]:
        if not relative or Path(relative).is_absolute():
            raise ValueError("invalid document path")
        raw = self.repo_root / relative
        target = raw.resolve()
        try:
            parts = target.relative_to(self.repo_root).parts
        except ValueError as exc:
            raise ValueError("document escapes repository") from exc
        if not parts or parts[0] not in DOCUMENT_ROOTS:
            raise ValueError("document is outside the allowlist")
        if raw.is_symlink() or not target.is_file():
            raise ValueError("document must be a regular file")
        content_type = DOCUMENT_TYPES.get(target.suffix.lower())
        if not content_type:
            raise ValueError("unsupported document type")
        return target, content_type

    def create_single(
        self,
        prompt: str,
        backend: str,
        effort: str,
        *,
        role: str = "primary",
        parent_run_id: str | None = None,
        mode: str = "single",
    ) -> dict:
        if self._closing.is_set():
            raise RuntimeError("controller is shutting down")
        prompt = self._validated_prompt(prompt)
        if backend not in {"codex", "claude"}:
            raise ValueError("backend must be codex or claude")
        run = self.store.create_run(
            parent_run_id=parent_run_id,
            mode=mode,
            role=role,
            backend=backend,
            status="queued",
            prompt=prompt,
            effort=effort,
            metadata={"canonical_write_allowed": False, "external_actions_allowed": False},
        )
        self.store.append_event(run["run_id"], "run_queued", message="Read-only run queued.")
        future = self.pool.submit(self._execute_run, run["run_id"], prompt, backend, role, effort)
        self._track_future(run["run_id"], future)
        return self.get_run(run["run_id"])

    def create_ensemble(self, prompt: str, evaluator_backend: str = "codex", effort: str = "max") -> dict:
        if self._closing.is_set():
            raise RuntimeError("controller is shutting down")
        prompt = self._validated_prompt(prompt)
        installed = [name for name in ("codex", "claude") if self._probes.get(name, {}).get("available")]
        if not installed:
            raise RuntimeError("No supported local agent runtime is available.")
        ready = [name for name in installed if self._backend_health.get(name) == "ready"]
        preferred = ready or (["codex"] if "codex" in installed else installed[:1])
        if evaluator_backend not in preferred:
            evaluator_backend = preferred[0]
        search_backends = preferred[:2]
        if len(search_backends) == 1:
            search_backends.append(search_backends[0])
        parent = self.store.create_run(
            mode="search_ensemble",
            role="orchestrator",
            backend=evaluator_backend,
            status="queued",
            prompt=prompt,
            effort=effort,
            metadata={
                "search_backends": search_backends,
                "canonical_write_allowed": False,
                "external_actions_allowed": False,
            },
        )
        self.store.append_event(
            parent["run_id"],
            "ensemble_queued",
            message=f"Parallel search queued on {', '.join(search_backends)}.",
        )
        future = self.orchestrator_pool.submit(
            self._execute_ensemble,
            parent["run_id"],
            prompt,
            search_backends,
            evaluator_backend,
            effort,
        )
        self._track_future(parent["run_id"], future)
        return self.get_run(parent["run_id"])

    @staticmethod
    def _validated_prompt(prompt: str) -> str:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")
        prompt = prompt.strip()
        if len(prompt) > MAX_PROMPT_CHARS:
            raise ValueError(f"prompt exceeds {MAX_PROMPT_CHARS} characters")
        return prompt

    def _execute_run(self, run_id: str, prompt: str, backend: str, role: str, effort: str) -> dict:
        if self._closing.is_set():
            self.store.update_run(run_id, status="interrupted", error="Controller is shutting down.")
            self.store.append_event(run_id, "run_interrupted", message="Run did not start.")
            return self.get_run(run_id)
        self.store.update_run(run_id, status="running", error=None)
        self.store.append_event(run_id, "run_started", message=f"{backend} {role} started.")

        def on_event(event: dict) -> None:
            event_type = str(event.get("type") or "runtime_event")
            message = event.get("message")
            safe_payload = {
                key: value
                for key, value in event.items()
                if key not in {"message"} and key not in {"reasoning", "thinking", "input"}
            }
            self.store.append_event(run_id, event_type, message=message, payload=safe_payload)
            if event.get("session_id"):
                self.store.update_run(run_id, session_id=str(event["session_id"]))

        try:
            result = run_agent(
                backend,
                prompt,
                self.repo_root,
                role,
                effort,
                on_event=on_event,
                timeout_seconds=180 if role == "search" else 300,
            )
            status = str(result.get("status") or "failed")
            final_text = str(result.get("final_text") or "")
            error = result.get("error")
            with self._lock:
                self._backend_health[backend] = self._health_from_result(status, error)
            self.store.update_run(
                run_id,
                status=status,
                final_text=final_text,
                error=str(error) if error else None,
                session_id=result.get("session_id"),
            )
            self.store.append_event(
                run_id,
                "run_finished",
                message="Run completed." if status == "completed" else f"Run ended as {status}.",
                payload={"status": status, "exit_code": result.get("exit_code")},
            )
        except Exception as exc:
            self.store.update_run(run_id, status="failed", error=str(exc))
            self.store.append_event(run_id, "run_failed", message=str(exc))
        return self.get_run(run_id)

    def _execute_ensemble(
        self,
        parent_run_id: str,
        request: str,
        search_backends: list[str],
        evaluator_backend: str,
        effort: str,
    ) -> dict:
        self.store.update_run(parent_run_id, status="running")
        self.store.append_event(parent_run_id, "ensemble_started", message="Parallel search started.")
        lanes = ["broad current-job discovery", "source validation, duplicates, and risk audit"]
        child_futures: list[Future] = []
        child_ids: list[str] = []
        for backend, lane in zip(search_backends, lanes):
            child_prompt = search_prompt(self.repo_root, request, lane)
            child = self.store.create_run(
                parent_run_id=parent_run_id,
                mode="search_child",
                role="search",
                backend=backend,
                status="queued",
                prompt=child_prompt,
                effort="high",
                metadata={"lane": lane, "canonical_write_allowed": False},
            )
            self.store.append_event(child["run_id"], "run_queued", message=f"Search lane: {lane}")
            child_ids.append(child["run_id"])
            child_futures.append(
                self.pool.submit(
                    self._execute_run,
                    child["run_id"],
                    child_prompt,
                    backend,
                    "search",
                    "high",
                )
            )
        child_results = [future.result() for future in child_futures]
        if self._closing.is_set():
            self.store.update_run(
                parent_run_id,
                status="interrupted",
                error="Controller stopped before primary evaluation.",
            )
            self.store.append_event(
                parent_run_id,
                "ensemble_interrupted",
                message="Search results were not evaluated or retried.",
            )
            return self.get_run(parent_run_id)
        self.store.append_event(
            parent_run_id,
            "search_completed",
            message=f"{len(child_results)} search runs completed; evaluator starting.",
            payload={"child_run_ids": child_ids},
        )
        evaluation = evaluator_prompt(self.repo_root, request, child_results)
        evaluator = self.store.create_run(
            parent_run_id=parent_run_id,
            mode="primary_evaluation",
            role="primary_evaluator",
            backend=evaluator_backend,
            status="queued",
            prompt=evaluation,
            effort=effort,
            metadata={"input_run_ids": child_ids, "canonical_write_allowed": False},
        )
        evaluator_result = self._execute_run(
            evaluator["run_id"], evaluation, evaluator_backend, "primary_evaluator", effort
        )
        final_status = "completed" if evaluator_result.get("status") == "completed" else "failed"
        self.store.update_run(
            parent_run_id,
            status=final_status,
            final_text=evaluator_result.get("final_text"),
            error=evaluator_result.get("error"),
            metadata={
                "search_backends": search_backends,
                "child_run_ids": child_ids,
                "evaluator_run_id": evaluator["run_id"],
                "canonical_write_allowed": False,
                "external_actions_allowed": False,
            },
        )
        self.store.append_event(
            parent_run_id,
            "ensemble_finished",
            message=f"Primary evaluation ended as {final_status}.",
            payload={"evaluator_run_id": evaluator["run_id"]},
        )
        return self.get_run(parent_run_id)

    def get_run(self, run_id: str) -> dict:
        run = self.store.get_run(run_id)
        if run is None:
            raise RunNotFoundError(f"run not found: {run_id}")
        run["events"] = self.store.list_events(run_id, limit=1_000)
        run["children"] = self.store.list_runs(parent_run_id=run_id, limit=100)
        return run

    def list_runs(self, limit: int = 100) -> list[dict]:
        return self.store.list_runs(limit=limit)


class ControlHandler(BaseHTTPRequestHandler):
    server_version = "jobflowd/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        return

    @property
    def controller(self) -> LocalController:
        return self.server.controller  # type: ignore[attr-defined]

    @property
    def bearer_token(self) -> str:
        return self.server.bearer_token  # type: ignore[attr-defined]

    def _send(self, payload: dict | list, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if content_type.startswith("text/html"):
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; "
                "font-src 'self' data:; script-src 'none'; connect-src 'none'; "
                "frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            )
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        expected_host = f"127.0.0.1:{self.server.server_address[1]}"
        if self.headers.get("Host") != expected_host:
            self._send({"error": "invalid host"}, 421)
            return False
        if self.path == "/healthz":
            return True
        if self.headers.get("Authorization") != f"Bearer {self.bearer_token}":
            self._send({"error": "unauthorized"}, 401)
            return False
        return True

    def _json_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0 or length > MAX_REQUEST_BYTES:
            raise ValueError("invalid request body size")
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            raise ValueError("Content-Type must be application/json")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("request body must be an object")
        return payload

    def do_GET(self) -> None:
        if not self._authorized():
            return
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/healthz":
                return self._send(
                    {
                        "service": "jobflowd",
                        "version": 1,
                        "repo": str(self.controller.repo_root),
                        "read_only_agent_runs": True,
                    }
                )
            if parsed.path == "/update":
                return self._send(self.controller.update_status())
            if parsed.path == "/agents":
                return self._send({"agents": self.controller.agents()})
            if parsed.path == "/overview":
                return self._send(self.controller.overview())
            if parsed.path == "/applications":
                return self._send({"applications": self.controller.applications()})
            if parsed.path == "/materials":
                return self._send(self.controller.materials())
            if parsed.path == "/today":
                return self._send(self.controller.today())
            if parsed.path == "/submission-evidence":
                app_id = parse_qs(parsed.query).get("application_id", [""])[0]
                return self._send_bytes(self.controller.submission_evidence(app_id), "text/html; charset=utf-8")
            if parsed.path == "/reports":
                return self._send({"reports": self.controller.reports()})
            if parsed.path == "/memory":
                return self._send(self.controller.memory())
            if parsed.path == "/document":
                query = parse_qs(parsed.query)
                relative = unquote(query.get("path", [""])[0])
                target, content_type = self.controller.resolve_document(relative)
                body = target.read_bytes()
                if target.suffix.lower() == ".html":
                    body = body.replace(b'href="/document?f=', b'href="/api/document?path=')
                return self._send_bytes(body, content_type)
            if parsed.path == "/runs":
                query = parse_qs(parsed.query)
                limit = int(query.get("limit", ["100"])[0])
                return self._send({"runs": self.controller.list_runs(limit)})
            if parsed.path.startswith("/runs/"):
                run_id = parsed.path.removeprefix("/runs/")
                return self._send(self.controller.get_run(run_id))
            return self._send({"error": "not found"}, 404)
        except RunNotFoundError as exc:
            return self._send({"error": str(exc)}, 404)
        except (TypeError, ValueError) as exc:
            return self._send({"error": str(exc)}, 400)

    def do_POST(self) -> None:
        if not self._authorized():
            return
        parsed = urlparse(self.path)
        try:
            payload = self._json_body()
            if parsed.path == "/runs":
                run = self.controller.create_single(
                    str(payload.get("prompt") or ""),
                    str(payload.get("backend") or "codex"),
                    str(payload.get("effort") or "max"),
                )
                return self._send(run, 202)
            if parsed.path == "/ensembles":
                run = self.controller.create_ensemble(
                    str(payload.get("prompt") or ""),
                    str(payload.get("backend") or "codex"),
                    str(payload.get("effort") or "max"),
                )
                return self._send(run, 202)
            return self._send({"error": "not found"}, 404)
        except (RuntimeError, TypeError, ValueError) as exc:
            return self._send({"error": str(exc)}, 400)


def write_token(path: Path, token: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(token + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Local jobflow Agent runtime controller")
    parser.add_argument("--repo", default=str(DEFAULT_REPO))
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    args = parser.parse_args()
    repo_root = Path(args.repo).expanduser().resolve()
    runtime_dir = Path(args.runtime_dir).expanduser().resolve()
    if not (repo_root / "00-工作流系统/state").is_dir():
        print(f"Invalid jobflow repository: {repo_root}", file=sys.stderr)
        return 1
    if not 1024 <= args.port <= 65535:
        print("Port must be between 1024 and 65535.", file=sys.stderr)
        return 1
    token = secrets.token_urlsafe(32)
    token_path = runtime_dir / "control-token"
    write_token(token_path, token)
    controller = LocalController(repo_root, runtime_dir / "runs.sqlite3")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), ControlHandler)
    server.controller = controller  # type: ignore[attr-defined]
    server.bearer_token = token  # type: ignore[attr-defined]
    def stop_server(*_: object) -> None:
        controller.begin_shutdown()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop_server)
    print(
        "JOBFLOWD_READY="
        + json.dumps(
            {
                "url": f"http://127.0.0.1:{args.port}",
                "token_file": str(token_path),
                "repo": str(repo_root),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\njobflowd stopped.", flush=True)
    finally:
        controller.close()
        try:
            token_path.unlink()
        except FileNotFoundError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
