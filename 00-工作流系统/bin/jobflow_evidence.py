"""Evidence v2: exact targets/payloads and one-time execution claims.

An explicitly frozen migration index preserves old attestations without turning
their free-text approvals into reusable execution permissions.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone


def frozen(repo, path):
    policy = repo.state_dir / "evidence_policy.json"
    if not policy.exists():
        return False
    rel = path.relative_to(repo.repo_root).as_posix()
    item = repo.load("evidence_policy.json").get("historical_manifests", {}).get(rel)
    if not item or hashlib.sha256(path.read_bytes()).hexdigest() != item.get("sha256"):
        return False
    manifest = json.loads(path.read_text())
    aid = (manifest.get("approval_binding") or {}).get("approval_id")
    ap = repo.approvals_dir / f"{aid}.json"
    return ap.is_file() and hashlib.sha256(ap.read_bytes()).hexdigest() == item.get("approval_sha256")


def target_for(repo, application_id, operation, platform):
    app = next((a for a in repo.load("applications.json")["applications"] if a["application_id"] == application_id), None)
    if not app:
        raise ValueError("unknown application target")
    if not platform or not operation:
        raise ValueError("operation and platform are required")
    return dict(application_id=application_id, company=app["company"], role=app["role"], platform=platform, operation_type=operation)


def check(repo, approval, application_id, task_id, operation, platform, payloads, for_claim=False):
    from jobflow import _parse_datetime
    if approval.get("binding_version") != 2:
        raise ValueError("legacy/free-text approval cannot authorize new execution; request exact target and payload approval")
    if approval.get("task_id") != task_id:
        raise ValueError("approval task mismatch")
    target = target_for(repo, application_id, operation, platform)
    if approval.get("target") != target:
        raise ValueError("approval target/platform/operation mismatch")
    if approval.get("approved_payloads") != payloads:
        raise ValueError("approval payload mismatch: content or attachments changed")
    content_ref = approval.get("content_ref")
    if content_ref and not any(a["path"] == content_ref and a["sha256"] == approval.get("content_sha256") for a in payloads):
        raise ValueError("approval payload hash differs from the approved message digest")
    for artifact in payloads:
        actual = repo._artifact_record(f"{artifact['kind']}={artifact['path']}")
        if actual != artifact:
            raise ValueError("approved payload has changed on disk")
    expiry = _parse_datetime(approval.get("expires_at"))
    now = datetime.now(timezone.utc)
    if for_claim:
        if approval.get("decision") != "approved" or not expiry or expiry <= now:
            raise ValueError("approval is not approved or has expired")
        task = next(t for t in repo.load("task_queue.json")["tasks"] if t["task_id"] == task_id)
        if task["status"] in {"done", "cancelled", "blocked"}:
            raise ValueError("execution task is not available")
        statuses = {t["task_id"]: t["status"] for t in repo.load("task_queue.json")["tasks"]}
        if any(statuses.get(dep) != "done" for dep in task.get("depends_on", [])):
            raise ValueError("execution task dependencies are incomplete")
    else:
        claimed = _parse_datetime(approval.get("claimed_at"))
        if approval.get("decision") != "executing" or not claimed or not expiry or claimed > expiry:
            raise ValueError("a valid one-time execution claim is required before recording external evidence")
        if now > claimed + timedelta(minutes=30):
            raise ValueError("execution claim timed out; preserve unverified result and review manually, do not retry")
    return target


def validate_manifest(repo, path, manifest):
    from jobflow import EXTERNAL_EVIDENCE_OPERATIONS, _parse_datetime
    errors = []
    rel = path.relative_to(repo.repo_root).as_posix()
    op = manifest.get("operation_type")
    if op not in EXTERNAL_EVIDENCE_OPERATIONS:
        return errors
    binding = manifest.get("approval_binding") or {}
    ap = repo.approvals_dir / f"{binding.get('approval_id')}.json"
    if not ap.is_file():
        return errors  # core emits the missing approval error
    approval = json.loads(ap.read_text())
    if binding.get("scope") != approval.get("scope"):
        errors.append(f"{rel}: approval scope mismatch")
    if manifest.get("binding_version") != 2:
        if not frozen(repo, path):
            errors.append(f"{rel}: historical evidence is not in the frozen migration index")
        return errors
    try:
        target = target_for(repo, manifest.get("application_id"), op, manifest.get("target", {}).get("platform"))
        if approval.get("target") != target:
            errors.append(f"{rel}: approval target mismatch")
        if manifest.get("target") != {k: target[k] for k in ("platform", "company", "role")}:
            errors.append(f"{rel}: manifest target differs from application")
        if approval.get("approved_payloads") != manifest.get("payload_artifacts"):
            errors.append(f"{rel}: actual payload differs from approval")
        content_ref = approval.get("content_ref")
        if content_ref and not any(a.get("path") == content_ref and a.get("sha256") == approval.get("content_sha256") for a in manifest.get("payload_artifacts", [])):
            errors.append(f"{rel}: payload does not match the approved content digest")
        if (manifest.get("result", {}).get("status") == "verified_success"
                and manifest.get("executor", {}).get("actor_id") == manifest.get("audit", {}).get("auditor_id")):
            errors.append(f"{rel}: new external evidence requires a different auditor")
        if approval.get("decision") != "consumed" or rel not in approval.get("consumption_evidence_refs", []):
            errors.append(f"{rel}: external execution approval was not consumed by this manifest")
        claim = _parse_datetime(approval.get("claimed_at"))
        expiry = _parse_datetime(approval.get("expires_at"))
        if not claim or not expiry or claim > expiry or manifest.get("execution_id") != approval.get("execution_id"):
            errors.append(f"{rel}: invalid or expired execution claim")
    except ValueError as exc:
        errors.append(f"{rel}: {exc}")
    return errors


def successful_submission(repo, app):
    """Approval provenance and platform success are distinct checks."""
    for ref in app.get("evidence_manifests", []):
        path = repo.repo_root / ref
        try:
            m = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        result = m.get("result") or {}
        if (m.get("application_id") == app.get("application_id") and m.get("operation_type") == "application_submit"
                and result.get("status") == "verified_success" and result.get("platform_readback")
                and result.get("proof_artifacts") and (m.get("audit") or {}).get("outcome") == "pass"):
            if not repo.verify_evidence_manifest(path, strict=False):
                return True
    return False
