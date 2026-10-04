"""Read-only Shanghai-day submission accounting; never derives submissions from messages."""
from datetime import date, datetime
import json
from pathlib import Path
import re
from urllib.parse import quote
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("Asia/Shanghai")
VERIFIED_STAGES = {"submitted_verified", "follow_up_due", "interviewing", "offer", "closed", "withdrawn", "rejected"}
PREPARED_STAGES = {"approved", "application_prepared", "awaiting_final_submit"}


def local_day(value):
    if not isinstance(value, str):
        return None
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return date.fromisoformat(value).isoformat()
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return instant.astimezone(ZONE).date().isoformat() if instant.tzinfo else None
    except ValueError:
        return None


def read_manifests(root, app):
    """Only explicit manifests in this application's fixed evidence directory."""
    root = Path(root).resolve()
    aid = app.get("application_id", "")
    if not isinstance(aid, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", aid):
        return []
    base = root / "00-工作流系统/evidence" / aid
    manifests = []
    refs = app.get("evidence_manifests", [])
    for ref in refs if isinstance(refs, list) else []:
        if not isinstance(ref, str) or Path(ref).is_absolute() or ".." in Path(ref).parts:
            continue
        path = root / ref
        try:
            path.resolve().relative_to(base)
            if path.name != "manifest.json" or any(p.is_symlink() for p in [path, *path.parents] if p != root and root in p.parents):
                continue
            document = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(document, dict) and document.get("application_id") == aid:
                manifests.append((ref, document))
        except (OSError, ValueError):
            continue
    return manifests


def successful(manifest, operation):
    result = manifest.get("result")
    audit = manifest.get("audit")
    return (manifest.get("operation_type") == operation and isinstance(result, dict)
            and result.get("status") == "verified_success" and bool(result.get("platform_readback"))
            and bool(result.get("proof_artifacts")) and isinstance(audit, dict) and audit.get("outcome") == "pass")


def build_today(applications, root, now=None):
    now = now or datetime.now(ZONE)
    if now.tzinfo is None:
        raise ValueError("today clock requires a timezone")
    day = now.astimezone(ZONE).date().isoformat()
    try:
        policy = json.loads((Path(root) / "00-工作流系统/state/evidence_policy.json").read_text())
        legacy_ids = set(policy.get("legacy_application_ids", []))
    except (OSError, ValueError, TypeError):
        legacy_ids = set()
    groups = {key: [] for key in ("verified", "unverified", "prepared", "message_only", "undated")}
    unique = {}
    conflicts = []
    for app in applications:
        if not isinstance(app, dict) or not isinstance(app.get("application_id"), str):
            continue
        aid = app["application_id"]
        if aid in unique and unique[aid] != app:
            conflicts.append(aid)
        else:
            unique[aid] = app
    for aid, app in unique.items():
        if aid in conflicts:
            continue
        status = app.get("status")
        submitted = app.get("submitted_at")
        submitted_day = local_day(submitted)
        manifests = read_manifests(root, app)
        legacy = app.get("legacy_evidence") is True and aid in legacy_ids and bool(app.get("evidence_refs"))
        proof = legacy or any(successful(m, "application_submit") for _, m in manifests)
        row = {key: app.get(key) for key in ("application_id", "company", "role", "channel", "status", "submitted_at", "phone_prep_available", "phone_prep_url")}
        row["evidence_url"] = "/api/submission-evidence?application_id=" + quote(aid, safe="")
        if status in VERIFIED_STAGES and proof and submitted_day == day:
            groups["verified"].append(row)
        elif submitted_day == day and (status == "submitted_unverified" or status in VERIFIED_STAGES):
            groups["unverified"].append(row)
        elif status in PREPARED_STAGES:
            groups["prepared"].append(row)
        if (status in VERIFIED_STAGES or status == "submitted_unverified") and not submitted_day:
            groups["undated"].append(row)
        messages = [m for _, m in manifests if successful(m, "external_send") and local_day(m.get("occurred_at")) == day]
        if messages and not (status in VERIFIED_STAGES and proof and submitted_day == day):
            groups["message_only"].append({**row, "message_at": max(m["occurred_at"] for m in messages)})
    for rows in groups.values():
        rows.sort(key=lambda r: (r.get("submitted_at") or "", r["application_id"]), reverse=True)
    companies = {str(row.get("company") or "").strip().casefold() for row in groups["verified"]} - {""}
    return {"date": day, "timezone": "Asia/Shanghai", "verified_count": len(groups["verified"]),
            "company_count": len(companies), "groups": groups, "conflicting_application_ids": sorted(set(conflicts))}
