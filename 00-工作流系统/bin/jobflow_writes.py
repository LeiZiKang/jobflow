"""Serialize cooperating writers and reject writes by another Decider session.

Rollback protects Python exceptions. Process-kill recovery is deliberately not
claimed: generated views can be rebuilt; interrupted writes require validate.
No credentials or runtime provider database are read by this module.
"""
from contextlib import contextmanager
import fcntl
from functools import wraps
import hashlib
import os
from pathlib import Path
import tempfile
import threading

_locks = {}
_registry_lock = threading.Lock()
_local = threading.local()


@contextmanager
def locked(repo):
    key = str(repo.system_dir)
    with _registry_lock:
        lock = _locks.setdefault(key, threading.RLock())
    with lock:
        active = getattr(_local, "held", set())
        if key in active:
            yield False
            return
        directory = Path(tempfile.gettempdir()) / ("jobflow-writer-" + hashlib.sha256(key.encode()).hexdigest()[:20])
        directory.mkdir(mode=0o700, exist_ok=True)
        fd = os.open(directory / "writer.lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            _local.held = active | {key}
            yield True
        finally:
            _local.held = active
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def assert_owner(repo):
    from jobflow import _effective_decider_status
    lease = repo.load("active_decider.json")
    if _effective_decider_status(lease) == "claimed" and repo.session_ref != lease.get("session_ref"):
        raise ValueError("write rejected: active Decider session owns this repository; use its session-ref or wait for release")


def state_paths(repo):
    paths = set(repo.state_dir.glob("*.json")) - {repo.state_dir / "memory.json"}
    paths.update(repo.approvals_dir.glob("approval-*.json"))
    paths.update(repo.evidence_manifests())
    paths.update([repo.events_path, repo.system_dir / "DECIDER_BRIEF.md"])
    return paths


def mutation(method):
    @wraps(method)
    def wrapped(repo, *args, **kwargs):
        with locked(repo) as outer:
            if not outer:
                return method(repo, *args, **kwargs)
            if method.__name__ != "claim_decider":
                assert_owner(repo)
            paths = state_paths(repo)
            if (repo.repo_root / "01-现在在做").is_dir():
                paths.update(repo.render_views())
            paths.add(repo.system_dir / "推进求职.html")
            backup = {p: p.read_bytes() if p.is_file() else None for p in paths}
            try:
                return method(repo, *args, **kwargs)
            except Exception:
                from jobflow import _atomic_write_text
                for p in state_paths(repo) | paths:
                    if p not in backup or backup[p] is None:
                        if p.is_file():
                            p.unlink()
                    else:
                        _atomic_write_text(p, backup[p].decode("utf-8"))
                raise
    return wrapped


def read_snapshot(method):
    @wraps(method)
    def wrapped(repo, *args, **kwargs):
        with locked(repo):
            return method(repo, *args, **kwargs)
    return wrapped
