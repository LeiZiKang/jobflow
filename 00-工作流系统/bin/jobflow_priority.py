"""Evidence-based attention priority. Low priority never closes a job or skips checks."""
from copy import deepcopy
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo


def assess(snapshot):
    observed = datetime.fromisoformat(snapshot["observed_at"].replace("Z", "+00:00"))
    if observed.tzinfo is None:
        raise ValueError("observed_at requires a timezone")
    as_of = observed.astimezone(ZoneInfo("Asia/Shanghai")).date()
    waiting_on = snapshot.get("waiting_on")
    if waiting_on not in {"user", "employer", "unknown"}:
        raise ValueError("waiting_on must be user, employer or unknown")
    for key in ("last_outbound_date", "last_inbound_date", "waiting_since"):
        if snapshot.get(key) and date.fromisoformat(snapshot[key]) > as_of:
            raise ValueError(f"{key} cannot be after the observation")
    result = dict(level=None, rank=25, label="待核实", reason="尚未确认当前轮到谁行动", as_of=as_of.isoformat(),
                  confidence="low", waiting_days=None, verification="verified")
    if not snapshot.get("response_window_verified") or waiting_on == "unknown":
        return result
    if waiting_on == "user":
        if not snapshot.get("action_needed"):
            raise ValueError("waiting for user requires an explicit action")
        result.update(level=1, rank=10, label="先处理", reason=snapshot["action_needed"], confidence="high")
        return result
    if not snapshot.get("waiting_since"):
        raise ValueError("waiting for employer requires the first unanswered date")
    since = date.fromisoformat(snapshot["waiting_since"])
    if snapshot.get("last_inbound_date") and date.fromisoformat(snapshot["last_inbound_date"]) > since:
        raise ValueError("new employer reply must start a new conversation assessment")
    days = (as_of - since).days
    effective_days = days
    promised = snapshot.get("expected_reply_date")
    if promised:
        effective_days = max(0, (as_of - max(since, date.fromisoformat(promised))).days)
    level = 4 if effective_days >= 14 else 3 if effective_days >= 7 else 2
    labels = {2: "正常跟进", 3: "降低关注", 4: "低优先"}
    reason = f"等对方 {days} 天，未见新回复"
    if promised and date.fromisoformat(promised) >= as_of:
        reason = f"对方约定 {promised} 回复，暂不降级"
    result.update(level=level, rank=level * 10, label=labels[level], reason=reason, confidence="high", waiting_days=days)
    return result


def save(repo, application_id, snapshot, actor):
    from jobflow import _resolve_repo_ref, _scan_secrets, _atomic_write_json, _iso
    snapshot = deepcopy(snapshot)
    assessment = assess(snapshot)
    observed = datetime.fromisoformat(snapshot["observed_at"].replace("Z", "+00:00"))
    if observed > datetime.now(timezone.utc):
        raise ValueError("cannot record a future observation")
    if not snapshot.get("source_refs"):
        raise ValueError("chat priority needs source evidence")
    for ref in snapshot["source_refs"]:
        _resolve_repo_ref(repo.repo_root, ref)
    errors = []
    _scan_secrets(snapshot, "engagement", errors)
    if errors:
        raise ValueError("; ".join(errors))
    document = repo.load("applications.json")
    app = next((a for a in document["applications"] if a["application_id"] == application_id), None)
    if not app or app["status"] in {"closed", "withdrawn", "rejected"}:
        raise ValueError("priority requires an active application")
    prior = app.get("engagement") or {}
    if prior.get("observed_at") and datetime.fromisoformat(prior["observed_at"].replace("Z", "+00:00")) > observed:
        raise ValueError("cannot replace newer chat evidence")
    if (prior.get("waiting_on") == snapshot.get("waiting_on") == "employer"
            and prior.get("waiting_since") and snapshot.get("waiting_since")
            and snapshot["waiting_since"] > prior["waiting_since"]
            and (snapshot.get("last_inbound_date") or "") <= (prior.get("last_inbound_date") or "")):
        raise ValueError("another outgoing follow-up cannot reset the unanswered waiting period")
    app["engagement"] = snapshot
    app["attention_priority"] = assessment
    if snapshot.get("platform_contact_label"):
        app["platform_contact_label"] = snapshot["platform_contact_label"]
    document["updated_at"] = _iso(datetime.now(timezone.utc))
    _atomic_write_json(repo.state_dir / "applications.json", document)
    repo.record_event("chat_priority_assessed", f"{application_id}: {assessment['label']}; {assessment['reason']}", actor,
                      [application_id], snapshot["source_refs"])
    return assessment


def refresh(app, observation):
    """Daily no-reply observations age the same unanswered thread, not a new clock."""
    snapshot = app.get("engagement")
    if not snapshot:
        return
    if observation["outcome"] == "blocked":
        if app.get("attention_priority"):
            app["attention_priority"]["verification"] = "blocked"
        return
    if observation["outcome"] in {"no_reply", "unread"} and snapshot.get("waiting_on") == "employer":
        snapshot = deepcopy(snapshot)
        snapshot["observed_at"] = observation["observed_at"]
        snapshot["source_refs"] = list(dict.fromkeys(snapshot.get("source_refs", [])[:1] + [observation["source_ref"]]))
        app["engagement"] = snapshot
        app["attention_priority"] = assess(snapshot)
    elif observation["outcome"] == "replied":
        app["engagement"] = {**snapshot, "waiting_on": "unknown", "response_window_verified": False}
        app["attention_priority"] = dict(level=None, rank=15, label="回复待判断", reason="有回复记录，需重新确认下一步由谁行动",
                                         as_of=observation["observed_at"][:10], confidence="medium", waiting_days=None, verification="needs_review")
