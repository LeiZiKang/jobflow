"""Per-opportunity work queue. Reconciliation never grants external permission."""
from __future__ import annotations

from jobflow_metrics import verified_progress

from datetime import date, datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

TERMINAL = {"done", "cancelled"}
APP_TERMINAL = {"closed", "withdrawn", "rejected"}
PREFIX = "00-工作流系统/"


def phone_prep_path(repo_root, application):
    """A ready flag alone is not proof that a safe per-application script exists."""
    prep = application.get("phone_prep")
    aid = application.get("application_id")
    if not isinstance(prep, dict) or prep.get("status") != "ready" or not isinstance(aid, str):
        return None
    if not re.fullmatch(r"[A-Za-z0-9_-]+", aid):
        return None
    relative = f"04-面试/电话准备/{aid}.html"
    if prep.get("path") != relative:
        return None
    root = Path(repo_root).resolve()
    target = root / relative
    try:
        target.resolve().relative_to(root)
        if any(part.is_symlink() for part in [target, *target.parents] if part != root and root in part.parents):
            return None
        return relative if target.is_file() else None
    except (OSError, ValueError):
        return None


def identity(item):
    """Use platform + job ID; company names are not unique job identities."""
    url = item.get("url") or item.get("job_url") or ""
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    platform = "boss" if host == "zhipin.com" or host.endswith(".zhipin.com") else "liepin" if host == "liepin.com" or host.endswith(".liepin.com") else host
    match = re.search(r"/(?:job_detail/|job/|a/)([^/.]+)", parsed.path)
    job_id = item.get("platform_job_id") or (match.group(1) if match else "")
    return f"{platform}:{job_id}" if platform and job_id else None


def load_progress(repo):
    path = repo.state_dir / "progress.json"
    return repo.load("progress.json") if path.exists() else {"schema_version": 1, "revision": 0, "drafts": []}


def task(task_id, title, kind, ref, priority=3, **extra):
    return dict(task_id=task_id, title=title, status="pending", priority=priority,
                role="auditor" if kind in {"followup", "scheduler"} else "researcher",
                objective=title, depends_on=[], inputs=[ref, PREFIX + "runbooks/推进求职.md"],
                allowed_actions=["read_repo", "browse_platform_read_only", "draft_local_materials"],
                forbidden_actions=["send_message", "apply", "login", "enter_credentials", "change_profile"],
                output_path=PREFIX + "evidence/progress/<task-id>/", approval_required=False,
                stop_conditions=["login_required", "credential_prompt", "captcha", "ownership_lost"],
                acceptance=["有可复核来源及观察时间；未知明确标记", "不发送、不投递、不扩大授权范围", "将结论及下一步回写结构化状态"],
                source=ref, managed_by="progress", progress_kind=kind, **extra)


def sync(repo, actor):
    from jobflow import _atomic_write_json, _iso, _scan_secrets
    now = _iso(datetime.now(timezone.utc))
    current = repo.load("current.json")
    candidates = repo.load("candidates.json")["candidates"]
    apps = repo.load("applications.json")["applications"]
    jobs = repo.load("recurring_jobs.json")["jobs"]
    doc = repo.load("task_queue.json")
    progress = load_progress(repo)
    before = json.dumps([doc, progress, current], sort_keys=True, ensure_ascii=False)
    by_id = {t["task_id"]: t for t in doc["tasks"]}
    progress["as_of_date"] = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    expected = set()

    def upsert(new):
        expected.add(new["task_id"])
        old = by_id.get(new["task_id"])
        if old is None:
            doc["tasks"].append(new)
            by_id[new["task_id"]] = new
        elif old.get("managed_by") == "progress":
            # Preserve real results, blockers, and in-progress ownership.
            for key in ("title", "objective", "priority", "inputs", "not_before"):
                if key in new:
                    old[key] = new[key]

    for c in candidates:
        if c.get("source_draft_id") and c.get("decision_state") == "awaiting_user":
            decision_task = task("task-decide-" + c["candidate_id"], f"用户决定：{c['company']} · {c['role']}", "candidate_decision", c["dossier"], 6,
                                 candidate_id=c["candidate_id"])
            decision_task.update(role="decider", status="waiting_user", approval_required=True,
                                 allowed_actions=["read_repo", "summarize", "request_user_decision"],
                                 objective="审核已完成；请用户决定这个具体岗位，未批准不得进入投递准备。")
            upsert(decision_task)
        linked = [a for a in apps if a.get("candidate_id") == c["candidate_id"] or (identity(c) and identity(c) == identity(a))]
        if c.get("decision_state") == "approved" and not linked:
            tid = "task-prepare-" + c["candidate_id"]
            p = 2 if c.get("ownership_priority") == "foreign" else 3
            t = task(tid, f"准备 {c['company']} · {c['role']}", "prepare", c["dossier"], p, candidate_id=c["candidate_id"])
            t["objective"] = "只核实已批准的这一个岗位仍有效、核对现有文字事实与材料，产出可供用户批准的发送包。岗位范围已批，无需重问；文字、附件与最终提交未批则不得发送。"
            t["inputs"].append(PREFIX + "state/candidates.json")
            if c.get("message_draft_ref"):
                t["inputs"].append(c["message_draft_ref"])
            upsert(t)

    for a in apps:
        # This is a preparation reminder, never a gate on recording a real submission.
        aid = a["application_id"]
        phone_id = "task-phone-prep-" + aid
        ready_path = phone_prep_path(repo.repo_root, a)
        submitted = bool(a.get("submitted_at")) or a.get("status") in {
            "submitted_unverified", "submitted_verified", "follow_up_due", "interviewing", "offer"
        }
        previous = by_id.get(phone_id)
        if ready_path and previous and previous.get("managed_by") == "progress":
            expected.add(phone_id)
            if previous["status"] != "done":
                previous.update(status="done", updated_at=now, last_actor=actor,
                                last_note="岗位专属电话准备脚本已登记且文件存在。", evidence_refs=[ready_path])
        elif submitted and a.get("status") not in APP_TERMINAL:
            t = task(phone_id, f"准备电话沟通：{a['company']} · {a['role']}", "phone_prep",
                     PREFIX + "state/applications.json", 2, application_id=aid)
            t.update(objective="为该已投岗位准备可随来电快速打开的电话脚本；核对实际 JD、简历事实、工时与用工关系。未知明确标记，不改简历，不自动回复。",
                     output_path=f"04-面试/电话准备/{aid}.html")
            upsert(t)
            if previous and previous.get("managed_by") == "progress" and previous["status"] in TERMINAL:
                previous.update(status="pending", updated_at=now, last_actor=actor,
                                last_note="当前缺少已登记且存在的 ready 电话脚本，重新列为待准备。")
        due = a.get("follow_up_due")
        if (a.get("status") in APP_TERMINAL or not due
                or a.get("follow_up_state") in {"cancelled", "completed"}):
            continue
        t = task(f"task-check-{a['application_id']}-{due}", f"核实 {a['company']} 的当前回复", "followup", PREFIX + "state/applications.json", 1,
                 application_id=a["application_id"], not_before=due)
        t["priority"] = (a.get("attention_priority") or {}).get("level") or 1
        t["objective"] = "只读查看当前回复与待办。已有新回复就更新状态；尚无回复只记观察时间，不自动发送追问。用工性质改变时保留待决定事项，不替用户决定。"
        upsert(t)

    # Every draft gets a durable disposition; promote requires an explicit review.
    existing = {d["draft_id"]: d for d in progress["drafts"]}
    linked_items = [("application", a["application_id"], identity(a)) for a in apps]
    linked_items += [("candidate", c["candidate_id"], identity(c)) for c in candidates]
    for source in sorted((repo.repo_root / "05-检索报告/每日岗位检索").glob("*.candidates.json")):
        data = json.loads(source.read_text(encoding="utf-8"))
        for draft in data.get("candidates", []):
            did = draft["candidate_id"]
            relative = source.relative_to(repo.repo_root).as_posix()
            digest = hashlib.sha256(json.dumps(draft, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if did not in existing:
                item = dict(draft_id=did, source_ref=relative, source_sha256=digest,
                            company=draft.get("company"), role=draft.get("role"), url=draft.get("url"),
                            platform_job_id=draft.get("platform_job_id"), status="pending_review")
                progress["drafts"].append(item)
                existing[did] = item
            item = existing[did]
            if item["source_sha256"] != digest:
                raise ValueError(f"draft {did} changed after intake; append a new draft ID instead")
            matches = [(kind, rid) for kind, rid, key in linked_items if key and key == identity(draft)]
            if matches and item["status"] == "pending_review":
                item.update(status="linked_existing", linked_kind=matches[0][0], linked_id=matches[0][1],
                            reviewed_at=now, review_note="平台岗位 ID 与现有记录一致；不重复建档。")
            if item["status"] == "pending_review":
                upsert(task("task-review-" + did, f"审核草稿：{draft['company']} · {draft['role']}", "draft_review", relative, 4, draft_id=did))

    for job in jobs:
        if not job.get("enabled") or not job.get("next_due"):
            continue
        due = job["next_due"]
        t = task(f"task-check-{job['job_id']}-{due}", f"核实检索运行与记账：{job['title']}", "scheduler", PREFIX + "state/recurring_jobs.json", 5,
                 job_id=job["job_id"], not_before=due)
        t["objective"] = "只读核对调度器与仓库最后运行记录；明确区分未触发、未记账与平台阻塞，不自动修改排期或开关。补跑需遵守既有 runbook。"
        upsert(t)

    for old in doc["tasks"]:
        if old.get("managed_by") == "progress" and old["task_id"] not in expected and old["status"] not in TERMINAL:
            resolved = old.get("progress_kind") == "candidate_decision" and any(c["candidate_id"] == old.get("candidate_id") and c["decision_state"] in {"approved", "declined"} for c in candidates)
            old.update(status="done" if resolved else "cancelled", updated_at=now,
                       last_note="用户决定已记录。" if resolved else "来源已关闭、已处理或已有后继记录；自动取消重复待办。", last_actor=actor)

    # Decisions are scoped to remaining candidate IDs, regardless of batch date.
    pending = {c["candidate_id"] for c in candidates if c["decision_state"] == "awaiting_user"}
    for decision in current.get("open_decisions", []):
        if "candidate_ids" not in decision:
            continue
        decision["candidate_ids"] = [cid for cid in decision["candidate_ids"] if cid in pending]
        for key, ids in decision.get("decider_recommendation", {}).items():
            decision["decider_recommendation"][key] = [cid for cid in ids if cid in pending]
        decision["question"] = "仅决定仍未批准的岗位；已批准岗位独立推进准备，不再重复审批岗位范围。"
    current["open_decisions"] = [d for d in current.get("open_decisions", []) if "candidate_ids" not in d or d["candidate_ids"]]
    current["next_action_ids"] = [t["task_id"] for t in doc["tasks"] if t["status"] not in TERMINAL]
    current["current_phase"] = "per_opportunity_progress"
    metrics = current["metrics"]
    metrics["candidate_dossiers_in_latest_comparison"] = len(candidates)
    progress["counts"] = dict(approved_unprepared=sum(t["progress_kind"] == "prepare" and t["status"] not in TERMINAL for t in doc["tasks"] if t.get("managed_by") == "progress"),
                              drafts_pending=sum(d["status"] == "pending_review" for d in progress["drafts"]))
    if json.dumps([doc, progress, current], sort_keys=True, ensure_ascii=False) != before:
        progress.update(updated_at=now, revision=progress["revision"] + 1)
        doc["updated_at"] = current["updated_at"] = now
        errors = []
        _scan_secrets(progress, "progress.json", errors)
        if errors:
            raise ValueError("; ".join(errors))
        _atomic_write_json(repo.state_dir / "progress.json", progress)
        _atomic_write_json(repo.state_dir / "task_queue.json", doc)
        _atomic_write_json(repo.state_dir / "current.json", current)
        repo.record_event("progress_reconciled", "按岗位同步准备、草稿审核、跟进与检索运行检查；未授予外部操作权限。", actor, current["next_action_ids"], [PREFIX + "state/progress.json"])
    return progress


def review_draft(repo, draft_id, disposition, note, evidence_ref, actor, dossier=None):
    from jobflow import _atomic_write_json, _resolve_repo_ref, _iso
    _resolve_repo_ref(repo.repo_root, evidence_ref)
    if not note.strip():
        raise ValueError("review note is required")
    progress = load_progress(repo)
    item = next((d for d in progress["drafts"] if d["draft_id"] == draft_id), None)
    if not item or item["status"] != "pending_review":
        raise ValueError("draft must be pending_review")
    if disposition not in {"promoted", "rejected", "stale"}:
        raise ValueError("invalid draft disposition")
    if disposition == "promoted":
        if not dossier or not dossier.endswith(".html"):
            raise ValueError("promoting requires a reviewed HTML dossier")
        _resolve_repo_ref(repo.repo_root, dossier)
        draft = next(d for d in json.loads((repo.repo_root / item["source_ref"]).read_text())["candidates"] if d["candidate_id"] == draft_id)
        candidate_doc = repo.load("candidates.json")
        if any(identity(draft) and identity(draft) == identity(c) for c in candidate_doc["candidates"] + repo.load("applications.json")["applications"]):
            raise ValueError("job already exists; run sync-progress to link it")
        cid = draft_id.replace("draft-", "cand-", 1)
        candidate_doc["candidates"].append(dict(candidate_id=cid, batch_id="reviewed-drafts", company=draft["company"], role=draft["role"],
                                              channel=draft.get("channel"), salary=draft.get("salary", "待核实"), url=draft.get("url"), platform_job_id=draft.get("platform_job_id"),
                                              decision_state="awaiting_user", recommendation="needs_user_decision", dossier=dossier, key_tradeoff=note,
                                              source_draft_id=draft_id, review_evidence_ref=evidence_ref))
        candidate_doc["updated_at"] = _iso(datetime.now(timezone.utc))
        _atomic_write_json(repo.state_dir / "candidates.json", candidate_doc)
        current = repo.load("current.json")
        current.setdefault("open_decisions", []).append(dict(decision_id="decision-" + cid, question="请决定是否投递该已审核岗位。", source=dossier, candidate_ids=[cid]))
        _atomic_write_json(repo.state_dir / "current.json", current)
        item["candidate_id"] = cid
    item.update(status=disposition, review_note=note, reviewed_by=actor, reviewed_at=_iso(datetime.now(timezone.utc)), review_evidence_ref=evidence_ref)
    progress["revision"] += 1
    _atomic_write_json(repo.state_dir / "progress.json", progress)
    tasks = repo.load("task_queue.json")
    for t in tasks["tasks"]:
        if t.get("draft_id") == draft_id and t["status"] not in TERMINAL:
            t.update(status="done", last_note=note, evidence_refs=[evidence_ref])
    _atomic_write_json(repo.state_dir / "task_queue.json", tasks)
    repo.record_event("draft_reviewed", f"{draft_id}: {disposition}. {note}", actor, [draft_id], [evidence_ref])
    return item


def prepare_candidate(repo, candidate_id, message_file, evidence_ref, job_url, actor):
    from jobflow import _atomic_write_json, _resolve_repo_ref, _iso
    c = next((c for c in repo.load("candidates.json")["candidates"] if c["candidate_id"] == candidate_id), None)
    if not c or c["decision_state"] != "approved":
        raise ValueError("only an approved candidate can be prepared")
    if not identity(c) or identity(c) != identity({"url": job_url}):
        raise ValueError("JD must match the approved candidate platform/job ID")
    _resolve_repo_ref(repo.repo_root, message_file)
    _resolve_repo_ref(repo.repo_root, evidence_ref)
    payload = repo._artifact_record("message=" + message_file)
    apps = repo.load("applications.json")
    if any(a.get("candidate_id") == candidate_id or identity(a) == identity(c) for a in apps["applications"]):
        raise ValueError("candidate already has an application; continue it instead of duplicating")
    now = _iso(datetime.now(timezone.utc))
    aid = "app-" + candidate_id.removeprefix("cand-")
    if any(a["application_id"] == aid for a in apps["applications"]):
        raise ValueError("application ID already exists")
    app = dict(application_id=aid, candidate_id=candidate_id, company=c["company"], role=c["role"], channel=c["channel"],
               job_url=job_url, platform_job_id=c.get("platform_job_id"), status="application_prepared", updated_at=now,
               preparation=dict(message=payload, evidence_ref=evidence_ref, prepared_by=actor, prepared_at=now),
               evidence_refs=[evidence_ref], resume_version="附件尚待确认", follow_up_due=None, follow_up_state=None)
    apps["applications"].append(app)
    apps["updated_at"] = now
    _atomic_write_json(repo.state_dir / "applications.json", apps)
    doc = repo.load("task_queue.json")
    prep_id = "task-prepare-" + candidate_id
    for t in doc["tasks"]:
        if t["task_id"] == prep_id:
            t.update(status="done", last_note="已产出具体发送包；等待最终批准。", evidence_refs=[evidence_ref, message_file])
    t = task("task-submit-" + aid, "确认发送包：" + c["company"] + " · " + c["role"], "final_approval", message_file, 2, application_id=aid, candidate_id=candidate_id)
    t.update(status="waiting_user", role="operator", managed_by="preparation", approval_required=True,
             depends_on=[prep_id], objective="用户审核具体文字、附件和目标后，领取一次性审批再执行；只允许这个岗位。没有最终批准不得发送。",
             allowed_actions=["read_repo", "prepare_application", "browse_approved_job"],
             forbidden_actions=["submit_without_final_approval", "add_unapproved_job", "login", "enter_credentials"],
             inputs=[message_file, evidence_ref, c["dossier"], PREFIX + "runbooks/推进求职.md"],
             acceptance=["有精确目标和发送文件的一次性审批", "平台回读与截图；未成功则明确未验证", "应用状态和后续检查日期已记账"])
    doc["tasks"].append(t)
    _atomic_write_json(repo.state_dir / "task_queue.json", doc)
    repo.record_event("candidate_prepared", f"{candidate_id}: local packet ready, not sent", actor, [candidate_id, aid], [message_file, evidence_ref])
    return app


def record_followup(repo, application_id, outcome, observed_at, source_ref, note, next_check_due, actor):
    from jobflow import _atomic_write_json, _resolve_repo_ref, _parse_datetime, _iso
    _resolve_repo_ref(repo.repo_root, source_ref)
    observed = _parse_datetime(observed_at)
    now = datetime.now(timezone.utc)
    if not observed or observed.tzinfo is None or observed > now:
        raise ValueError("observed-at must be a past timezone-aware timestamp")
    if not note.strip() or outcome not in {"no_reply", "replied", "unread", "blocked"}:
        raise ValueError("outcome and observation note are required")
    if not next_check_due or date.fromisoformat(next_check_due) <= observed.date():
        raise ValueError("next-check-due must be after the observation date")
    doc = repo.load("applications.json")
    app = next((a for a in doc["applications"] if a["application_id"] == application_id), None)
    if not app or app["status"] in APP_TERMINAL or (not app.get("submitted_at") and app["status"] != "submitted_unverified"):
        raise ValueError("follow-up requires an active submitted application")
    previous = _parse_datetime(app.get("last_platform_check_at"))
    if previous and observed <= previous:
        raise ValueError("observation is not newer than the last platform check")
    observation = dict(outcome=outcome, observed_at=observed_at, source_ref=source_ref, note=note, actor=actor)
    app.setdefault("follow_up_observations", []).append(observation)
    import jobflow_priority
    jobflow_priority.refresh(app, observation)
    if outcome != "blocked":
        app.update(last_platform_check_at=observed_at, platform_check_source=source_ref, platform_readback=note,
                   follow_up_due=next_check_due, follow_up_state="scheduled")
    app["updated_at"] = doc["updated_at"] = _iso(now)
    _atomic_write_json(repo.state_dir / "applications.json", doc)
    tasks = repo.load("task_queue.json")
    for t in tasks["tasks"]:
        if t.get("application_id") == application_id and t.get("progress_kind") == "followup" and t["status"] not in TERMINAL:
            t.update(status="blocked" if outcome == "blocked" else "done", last_note=note, evidence_refs=[source_ref])
    _atomic_write_json(repo.state_dir / "task_queue.json", tasks)
    repo.record_event("followup_observed", f"{application_id}: {outcome}; {note}", actor, [application_id], [source_ref])
    return observation


def validate(repo):
    if not (repo.state_dir / "progress.json").exists():
        return []
    p = load_progress(repo)
    tasks = repo.load("task_queue.json")["tasks"]
    cs = repo.load("candidates.json")["candidates"]
    apps = repo.load("applications.json")["applications"]
    errors = []
    from jobflow import _scan_secrets
    _scan_secrets(p, "progress.json", errors)
    if p.get("schema_version") != 1 or not isinstance(p.get("revision"), int):
        errors.append("progress.json: invalid schema/revision")
    ids = [d["draft_id"] for d in p["drafts"]]
    if len(ids) != len(set(ids)):
        errors.append("progress.json: duplicate draft ID")
    for d in p["drafts"]:
        if d["status"] == "pending_review" and not any(t.get("draft_id") == d["draft_id"] and t["status"] not in TERMINAL for t in tasks):
            errors.append(f"{d['draft_id']}: pending draft lacks an active review task")
    for c in cs:
        if c.get("source_draft_id") and c["decision_state"] == "awaiting_user" and not any(t.get("candidate_id") == c["candidate_id"] and t.get("progress_kind") == "candidate_decision" and t["status"] not in TERMINAL for t in tasks):
            errors.append(f"{c['candidate_id']}: reviewed candidate lacks a user-decision task")
        linked = any(a.get("candidate_id") == c["candidate_id"] or identity(c) and identity(c) == identity(a) for a in apps)
        if c["decision_state"] == "approved" and not linked and not any(t.get("candidate_id") == c["candidate_id"] and t["status"] not in TERMINAL for t in tasks):
            errors.append(f"{c['candidate_id']}: approved job has no active next task")
    for t in tasks:
        if t.get("managed_by") == "progress" and {"send_message", "apply", "submit"} & set(t.get("allowed_actions", [])):
            errors.append(f"{t['task_id']}: progress reconciliation cannot authorize external actions")
    return errors


def render(repo):
    import jobflow_catalog
    e = html.escape
    tasks = repo.load("task_queue.json")["tasks"]
    current = repo.load("current.json")
    cs = repo.load("candidates.json")["candidates"]
    p = load_progress(repo)
    today = date.fromisoformat(p.get("as_of_date") or current["updated_at"][:10])
    groups = [("先推进已有机会", lambda t: t.get("progress_kind") in {"prepare", "followup", "phone_prep"}),
              ("把检索结果变成候选", lambda t: t.get("progress_kind") == "draft_review"),
              ("需要你决定", lambda t: t["status"] == "waiting_user"),
              ("运行检查与其他任务", lambda t: True)]
    used = set()
    sections = []
    labels = dict(pending="可开始", in_progress="进行中", waiting_user="等你决定", blocked="受阻")
    for title, predicate in groups:
        cards = []
        for t in sorted(tasks, key=lambda x: (x.get("priority", 99), x["task_id"])):
            if t["status"] in TERMINAL or t["task_id"] in used or not predicate(t):
                continue
            used.add(t["task_id"])
            refs = [r for r in t.get("inputs", []) if isinstance(r, str) and (repo.repo_root / r).is_file() and not r.endswith(".json") and not r.startswith(PREFIX)]
            if not refs and t.get("progress_kind") == "followup":
                refs = ["01-现在在做/投递记录.md"]
            links = " · ".join(f'<a href="../{e(r, quote=True)}" target="_blank" rel="noopener noreferrer">{e(r.split("/")[-1])}</a>' for r in refs)
            label = labels.get(t["status"], t["status"])
            if t.get("not_before") and t["not_before"] > today.isoformat():
                label = "到期再处理 · " + t["not_before"]
            cards.append(f'<article><span class="tag">{e(label)}</span><h3>{e(t["title"])}</h3><p>{e(t["objective"])}</p><p>{links}</p><details><summary>交给 Agent 执行</summary><p>请按任务 {e(t["task_id"])} 推进，完成后回写结果与下一步，遇到审批门就停在具体发送包。</p></details></article>')
        sections.append(f'<section><h2>{e(title)}</h2>{"".join(cards) or "<p>当前没有待办。</p>"}</section>')
    pending = [c for c in cs if c["decision_state"] == "awaiting_user"]
    decisions = "".join(f'<li><a href="../{e(c["dossier"], quote=True)}" target="_blank" rel="noopener noreferrer">{e(c["company"])} · {e(c["role"])}</a> — {e(c["key_tradeoff"])}</li>' for c in pending)
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>推进求职</title>
<style>:root{{color-scheme:dark;--bg:#101820;--fg:#edf3f8;--card:#192632;--line:#354755;--muted:#b1c1cf;--link:#8dccff}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.75 system-ui,sans-serif}}main{{max-width:960px;margin:auto;padding:36px 22px}}h1{{font-size:36px}}h2{{margin-top:40px}}h3{{margin:8px 0}}article{{background:var(--card);border:1px solid var(--line);padding:22px;border-radius:14px;margin:16px 0}}a{{color:var(--link);overflow-wrap:anywhere}}.tag{{color:var(--muted);font-size:13px}}summary{{cursor:pointer}}details p{{overflow-wrap:anywhere}}.intro{{font-size:19px}}@media(prefers-color-scheme:light){{:root{{color-scheme:light;--bg:#f4f7f9;--fg:#172631;--card:#fff;--line:#cad7e0;--muted:#516777;--link:#16588e}}}}</style>
<main><p class="tag">状态更新于 {e(current.get('updated_at', ''))} · 页面是状态快照</p><h1>推进求职</h1><p class="intro">先处理已有回复，再准备已批准岗位；未决定的岗位独立等待。</p><p>累计已验证投递 {verified_progress(current['metrics'])} · 待审核草稿 {p.get('counts', {}).get('drafts_pending', 0)} · 待决定岗位 {len(pending)}</p><p>当前方向：真上海外企优先，iOS / Mobile 为主。岗位批准后可以开始准备；发送文字、附件与最终投递仍按具体授权执行。</p><p><a href="推进求职-使用说明.html">怎么使用</a> · <a href="../求职看板.html">查看全部投递</a></p><h2>最近检索到的岗位</h2>{jobflow_catalog.cards(repo.repo_root, lambda path: '../' + path, latest_only=True)}<p><a href="../05-检索报告/岗位目录.html" target="_blank" rel="noopener noreferrer">查看全部检索岗位 ↗</a></p>{''.join(sections)}<h2>仍未决定的具体岗位</h2><ul>{decisions or '<li>没有待决定岗位。</li>'}</ul><p class="tag">没有新平台证据时不会自动写成已回复、已投递或已完成。</p></main></html>'''
