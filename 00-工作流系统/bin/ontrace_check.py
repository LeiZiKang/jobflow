"""Enumerate and atomically record every active application's daily observation."""
import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from jobflow import JobflowRepo, _parse_datetime, _resolve_repo_ref
from jobflow_writes import mutation

JOB_ID = "job-daily-ontrace-check"
ACTIVE = {"submitted_unverified", "submitted_verified", "follow_up_due", "interviewing", "offer"}


def targets(repo):
    rows = [a for a in repo.load("applications.json")["applications"]
            if a.get("status") in ACTIVE and (a.get("submitted_at") or a.get("status") == "submitted_unverified")]
    return sorted(rows, key=lambda a: (a.get("attention_priority") or {}).get("rank", 25))


@mutation
def record(repo, result_ref, actor):
    path = _resolve_repo_ref(repo.repo_root, result_ref)
    result = json.loads(path.read_text(encoding="utf-8"))
    scheduled = _parse_datetime(result.get("scheduled_for"))
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    job = repo.find_job(JOB_ID)
    if not job.get("enabled"):
        raise ValueError("On trace job is disabled")
    if not scheduled or scheduled.tzinfo is None:
        raise ValueError("timezone-aware scheduled_for is required")
    slot = scheduled.astimezone(ZoneInfo("Asia/Shanghai"))
    local_time = job.get("schedule", {}).get("local_time", "10:00")
    expected_hour, expected_minute = (int(part) for part in local_time.split(":"))
    not_before = job.get("not_before")
    if (slot.hour, slot.minute) != (expected_hour, expected_minute) or slot > now \
            or (not_before and slot.date().isoformat() < not_before):
        raise ValueError(f"result must belong to an eligible past {local_time} Asia/Shanghai slot")
    previous = _parse_datetime((job.get("last_run") or {}).get("scheduled_for"))
    if previous and previous >= scheduled:
        raise ValueError("this or a newer daily slot is already recorded")
    expected = {a["application_id"] for a in targets(repo)}
    observations = result.get("observations", [])
    ids = [o.get("application_id") for o in observations]
    if len(ids) != len(set(ids)) or set(ids) != expected:
        raise ValueError("every current On trace application needs exactly one observation")
    checked = 0
    blocked = []
    for obs in observations:
        when = _parse_datetime(obs.get("observed_at"))
        if not when or when.tzinfo is None or when < scheduled or when > now:
            raise ValueError("observation must be between the scheduled slot and now")
        # A round recorded after midnight observes on a later date than its slot; next check must follow both.
        next_due = max(slot.date(), when.astimezone(ZoneInfo("Asia/Shanghai")).date(), when.date()) + timedelta(days=1)
        repo.record_followup(obs["application_id"], obs["outcome"], obs["observed_at"], obs["source_ref"], obs["note"],
                             next_due.isoformat(), actor)
        if obs.get("engagement") and obs["outcome"] != "blocked":
            snapshot = {**obs["engagement"], "observed_at": obs["observed_at"], "source_refs": [obs["source_ref"]]}
            repo.record_chat_priority(obs["application_id"], snapshot, actor)
        if obs["outcome"] == "blocked":
            blocked.append(obs["application_id"] + ": " + obs["note"])
        else:
            checked += 1
    status = "completed" if not blocked else "partial" if checked else "blocked"
    return repo.record_run(JOB_ID, status, f"逐岗位核实：{checked} 个取得观察，{len(blocked)} 个受阻。", actor, [], None, None,
                           "; ".join(blocked) or None, [result_ref],
                           [f"active_applications={len(expected)}", f"checked_applications={checked}", f"blocked_applications={len(blocked)}"], result["scheduled_for"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["targets", "record"])
    parser.add_argument("--result")
    parser.add_argument("--actor")
    args = parser.parse_args()
    repo = JobflowRepo()
    if args.command == "targets":
        rows = [{k: a.get(k) for k in ("application_id", "company", "role", "channel", "job_url", "status", "last_platform_check_at", "employer_entity", "platform_contact_label", "engagement", "attention_priority")} for a in targets(repo)]
        print(json.dumps({"targets": rows}, ensure_ascii=False, indent=2))
        return 0
    if not args.result or not args.actor:
        parser.error("record requires --result and --actor")
    try:
        value = record(repo, args.result, args.actor)
        print(json.dumps(value["last_run"], ensure_ascii=False, indent=2))
        return 0
    except (ValueError, KeyError) as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
