"""Read-only, generated opportunity catalog shared by all UI entry points."""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
import re
from urllib.parse import quote

from jobflow_progress import identity

CATALOG_PATH = "05-检索报告/岗位目录.json"
INDEX_PATH = "05-检索报告/岗位目录.html"
DETAIL_DIR = "05-检索报告/岗位速览"
# 每个岗位的完整报告（runbooks/岗位报告撰写.md）。存在时优先于自动生成的速览页。
REPORT_DIR = "05-检索报告/岗位报告"


def load(root, name, default):
    path = root / "00-工作流系统/state" / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def safe_report(root, relative):
    if not isinstance(relative, str) or not relative.endswith(".html"):
        return None
    path = root / relative
    try:
        resolved = path.resolve()
        resolved.relative_to((root / "05-检索报告").resolve())
    except ValueError:
        return None
    return relative if resolved.is_file() and not path.is_symlink() else None


def day(value):
    match = re.search(r"(20\d{2})-?(\d{2})-?(\d{2})", str(value or ""))
    return "-".join(match.groups()) if match else None


def catalog(root):
    root = Path(root)
    candidates = load(root, "candidates.json", {"candidates": []})
    applications = load(root, "applications.json", {"applications": []})["applications"]
    dispositions = {d["draft_id"]: d for d in load(root, "progress.json", {"drafts": []})["drafts"]}
    rows = []
    by_key = {}
    for c in candidates["candidates"]:
        full_report = safe_report(root, f"{REPORT_DIR}/{c['candidate_id']}.html")
        report = full_report or safe_report(root, c.get("dossier"))
        row = dict(job_id=c["candidate_id"], company=c["company"], role=c["role"], salary=c.get("salary") or "待核实",
                   location=c.get("location") or "见岗位报告", channel=c.get("channel") or "待核实",
                   found_at=day(c.get("fetched_at") or c.get("candidate_id")), stage=c.get("decision_state"),
                   summary=c.get("key_tradeoff") or "待审核", risks=[], url=c.get("url"),
                   report_path=report, report_kind="岗位报告" if full_report else "岗位档案" if report else "检索详情", source_ref=c.get("dossier"),
                   employment_nature=c.get("employment_nature") or "用工性质见报告", candidate_id=c["candidate_id"])
        rows.append(row)
        if identity(c):
            by_key[identity(c)] = row
        if c.get("source_draft_id"):
            by_key[c["source_draft_id"]] = row

    base = root / "05-检索报告/每日岗位检索"
    for source in sorted(base.glob("*.candidates.json")) if base.exists() else []:
        document = json.loads(source.read_text(encoding="utf-8"))
        for draft in document.get("candidates", []):
            did = draft["candidate_id"]
            if not re.fullmatch(r"[a-zA-Z0-9-]+", did):
                raise ValueError("unsafe draft ID in report catalog")
            existing = by_key.get(did) or by_key.get(identity(draft))
            found = day(draft.get("fetched_at") or document.get("fetched_at") or source.name)
            if existing:
                if found and found > (existing.get("found_at") or ""):
                    existing["found_at"] = found
                continue
            full_report = safe_report(root, f"{REPORT_DIR}/{did}.html")
            disposition = dispositions.get(did, {})
            app = next((a for a in applications if a["application_id"] == disposition.get("linked_id") or (identity(a) and identity(a) == identity(draft))), None)
            stage = "applied" if app else disposition.get("status", "pending_review")
            row = dict(job_id=did, company=draft["company"], role=draft["role"], salary=draft.get("salary") or "待核实",
                       location=draft.get("location") or "待核实", channel=draft.get("channel") or "待核实", found_at=found,
                       stage=stage, summary=draft.get("why_kept") or draft.get("recommendation") or "待审核",
                       risks=draft.get("risks") or [], url=draft.get("url"), report_path=full_report or f"{DETAIL_DIR}/{did}.html",
                       report_kind="岗位报告" if full_report else "检索详情", source_ref=source.relative_to(root).as_posix(), employment_nature="用工性质未核实",
                       experience=draft.get("experience"), freshness_evidence=draft.get("freshness_evidence"), application_id=app.get("application_id") if app else None)
            if app:
                row["latest_update"] = app.get("platform_readback") or app.get("last_note")
                row["latest_update_at"] = day(app.get("updated_at"))
            rows.append(row)
            if identity(draft):
                by_key[identity(draft)] = row
    labels = {"approved": "已批准", "awaiting_user": "待决定", "declined": "已放弃", "not_approved": "不投",
              "pending_review": "待审核", "applied": "已投递", "rejected": "不推荐", "stale": "需重新核实", "promoted": "已入候选池"}
    assessments = load(root, "screening.json", {"assessments": []}).get("assessments", [])
    scores = {}
    if assessments:
        from jobflow_profile import load_goals, ProfileError
        from jobflow_screening import score_assessment
        try:
            goals = load_goals()
        except ProfileError:
            goals = None
        if goals is not None:
            scores = {a["candidate_id"]: score_assessment(a, goals) for a in assessments}
    for row in rows:
        if row["job_id"] in scores:
            result = scores[row["job_id"]]
            row["screening"] = result
            row["tags"] = result["tags"]
        row["stage_label"] = labels.get(row["stage"], "待核实")
        row["report_url"] = f"/api/document?path={quote(row['report_path'], safe='')}" if row.get("report_path") else None
        row["revision"] = hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
    rows.sort(key=lambda r: (r.get("found_at") or "", r["job_id"]), reverse=True)
    schedules = []
    for job in load(root, "recurring_jobs.json", {"jobs": []})["jobs"]:
        if job.get("job_id") not in {"job-daily-position-search", "job-daily-ontrace-check", "job-inbound-sweep"}:
            continue
        last = job.get("last_run") or {}
        schedules.append(dict(job_id=job["job_id"], title=job["title"], enabled=job.get("enabled", False),
                              local_time=(job.get("schedule") or {}).get("local_time"), next_due=job.get("next_due"), start_date=job.get("not_before"),
                              runtime_status=(job.get("trigger") or {}).get("runtime_status"), last_run_status=last.get("status"),
                              last_run_at=last.get("recorded_at"), blocker=last.get("blocker")))
    return {"schema_version": 1, "latest_search_date": max((r.get("found_at") or "" for r in rows), default=None), "opportunities": rows, "schedules": schedules}


STYLE = """:root{color-scheme:dark;--bg:#111820;--panel:#1b2632;--ink:#eaf0f5;--muted:#abbccd;--line:#354655;--accent:#a2cfff}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.8 system-ui,-apple-system,sans-serif}main{max-width:960px;margin:auto;padding:38px 22px 80px}h1{font-size:32px;line-height:1.3}h2{font-size:22px;margin:32px 0 16px}h3{font-size:20px;line-height:1.45;margin:8px 0}.muted{color:var(--muted)}a{color:var(--accent);overflow-wrap:anywhere}.tags{display:flex;gap:8px;flex-wrap:wrap}.tag{border:1px solid var(--line);border-radius:24px;padding:2px 10px;font-size:13px}.job-card,section.detail{padding:24px;margin:16px 0;background:var(--panel);border:1px solid var(--line);border-radius:14px}.job-meta{color:var(--muted);font-size:14px}.job-link{display:inline-block;margin-top:12px;padding:7px 14px;border:1px solid var(--line);border-radius:8px;text-decoration:none}.job-link:hover{border-color:var(--accent)}.job-summary{margin:8px 0}.job-card h3{max-width:100%}.job-groups{margin-top:24px}summary{cursor:pointer}li{margin:8px 0}@media(prefers-color-scheme:light){:root{color-scheme:light;--bg:#f3f6f9;--panel:#fff;--ink:#182634;--muted:#506477;--line:#ccdae5;--accent:#155e9f}}@media(max-width:600px){main{padding:24px 16px}.job-card,section.detail{padding:18px}h1{font-size:28px}}"""

LIST_STYLE = """.job-card{padding:22px;margin:16px 0;background:var(--paper-raised,var(--card,#1b2632));border:1px solid var(--line);border-radius:14px}.job-card h3{margin:8px 0;font-size:19px;line-height:1.5}.job-card .tags{display:flex;gap:8px;flex-wrap:wrap}.job-card .tag{border:1px solid var(--line);border-radius:20px;padding:2px 10px;font-size:12px}.job-meta{color:var(--ink-soft,var(--sub,#abbccd));font-size:13px}.job-link{display:inline-block;margin-top:10px;padding:6px 14px;border:1px solid var(--line);border-radius:8px;text-decoration:none}.job-link:hover{border-color:var(--accent)}.job-summary{margin:8px 0;line-height:1.8}.job-card a{overflow-wrap:anywhere}@media(max-width:600px){.job-card{padding:16px}}"""


def card(row, url):
    e = html.escape
    label = "阅读岗位报告" if row["report_kind"] in ("岗位档案", "岗位报告") else "阅读检索详情（未写完整报告）"
    link = f'<a class="job-link" href="{e(url, quote=True)}" target="_blank" rel="noopener noreferrer">{label} ↗</a>' if url else '<span class="muted">报告待补齐</span>'
    return f'''<article class="job-card"><div class="tags"><span class="tag">{e(row['stage_label'])}</span><span class="tag">{e(row['report_kind'])}</span></div><h3>{e(row['company'])} · {e(row['role'])}</h3><p class="job-meta">{e(row['salary'])} · {e(row['location'])} · {e(row['channel'])} · 检索于 {e(row.get('found_at') or '日期未记录')}</p><p class="job-summary">{e(row['summary'])}</p>{link}</article>'''


def cards(root, href, latest_only=False):
    data = catalog(root)
    groups = {}
    for row in data["opportunities"]:
        if latest_only and row["found_at"] != data["latest_search_date"]:
            continue
        groups.setdefault(row.get("found_at") or "日期未记录", []).append(row)
    return "".join(f'<h2>{html.escape(date)} <small class="muted">· {len(items)} 个岗位</small></h2>' + "".join(card(r, href(r["report_path"]) if r.get("report_path") else None) for r in items) for date, items in groups.items()) or '<p class="muted">尚未登记检索结果。</p>'


def detail(row):
    e = html.escape
    risks = "".join(f"<li>{e(str(v))}</li>" for v in row.get("risks", [])) or "<li>团队、用工关系和工时仍需核实。</li>"
    url = row.get("url") or ""
    jd = f'<a href="{e(url, quote=True)}" target="_blank" rel="noopener noreferrer">打开原始 JD ↗</a>' if url.startswith(("https://", "http://")) else '原始 JD 链接未记录'
    update = f'<aside class="job-card"><h3>后续投递记录 · {e(row.get("latest_update_at") or "日期未记录")}</h3><p>{e(row["latest_update"])}</p></aside>' if row.get("latest_update") else ''
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(row['company'])} · {e(row['role'])}</title><style>{STYLE}</style><main><p class="muted">单岗位检索详情 · {e(row.get('found_at') or '日期未知')} 的记录</p><h1>{e(row['company'])}<br>{e(row['role'])}</h1><div class="tags"><span class="tag">{e(row['stage_label'])}</span><span class="tag">{e(row['employment_nature'])}</span></div><p>{jd}</p><p class="muted">这里整理的是当次检索记录，尚未形成完整独立背调；岗位当前是否仍招聘需重新核实。</p>
{update}<section class="detail"><h2>01 · 岗位信息</h2><p>{e(row['location'])} · {e(row['channel'])} · {e(row.get('experience') or '经验要求待核实')}</p><p>{e(row.get('freshness_evidence') or '未记录平台更新时间')}</p></section>
<section class="detail"><h2>02 · 入职后做什么</h2><p>现有材料未完整记录产品、职责边界和典型工作日，需阅读原始 JD 并核实。</p></section>
<section class="detail"><h2>03 · 为什么被保留</h2><p>{e(row['summary'])}</p><p class="muted">这是检索时的判断，不代表已通过审核或已批准投递。</p></section>
<section class="detail"><h2>04 · 公司与团队</h2><p>团队规模、代码库成熟度、汇报关系与工时尚待独立核实。</p></section>
<section class="detail"><h2>05 · 薪资与用工性质</h2><p>检索记录薪资：{e(row['salary'])}。</p><p>{e(row['employment_nature'])}；平台薪资不等于已确认的 offer。</p></section>
<section class="detail"><h2>06 · 风险与待确认事项</h2><ul>{risks}</ul></section>
<section class="detail"><h2>07 · 当前状态与下一步</h2><p>{e(row['stage_label'])}。{'关联已有投递，继续核实当前回复，避免重复申请。' if row.get('application_id') else '审核 JD 时效和关键风险，完成岗位档案后交由用户决定。'}</p><p class="muted">来源：{e(row['source_ref'])}</p></section></main></html>'''


def views(root):
    root = Path(root)
    data = catalog(root)
    output = {root / CATALOG_PATH: json.dumps(data, ensure_ascii=False, indent=2) + "\n"}
    for row in data["opportunities"]:
        if (row.get("report_path") or "").startswith(DETAIL_DIR + "/"):
            output[root / row["report_path"]] = detail(row)
    output[root / INDEX_PATH] = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>检索到的岗位</title><style>{STYLE}</style><main><h1>检索到的岗位</h1><p class="muted">按检索日期排列，每个岗位单独阅读。报告在新标签页打开，岗位列表会保留。</p>{cards(root, lambda p: '../' + p)}</main></html>'''
    return output
