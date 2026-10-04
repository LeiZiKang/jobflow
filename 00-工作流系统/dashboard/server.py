#!/usr/bin/env python3
"""Local dashboard for the user's job search.

Reads canonical jobflow state and renders a read-only view.
Zero dependencies, localhost only. This is a VIEW — it never writes state.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))
import jobflow_catalog

DEFAULT_REPO = Path(__file__).resolve().parents[2]
SYSTEM_DIR = "00-工作流系统"
REPORTS_DIR = "05-检索报告"

POST_SUBMISSION = {
    "submitted_verified",
    "follow_up_due",
    "interviewing",
    "offer",
    "rejected",
    "withdrawn",
    "closed",
}
LIVE_STATES = {"submitted_verified", "follow_up_due", "interviewing", "offer"}
STATUS_LABEL = {
    "submitted_verified": ("已投递", "low"),
    "follow_up_due": ("待跟进", "mid"),
    "interviewing": ("面试中", "accent"),
    "offer": ("Offer", "low"),
    "rejected": ("已拒", "high"),
    "withdrawn": ("已撤回", "unknown"),
    "closed": ("已关闭", "unknown"),
}
RECOMMENDATION_LABEL = {
    "recommend_apply": ("建议投", "low"),
    "optional_volume": ("可冲量", "mid"),
    "needs_user_decision": ("等你拍板", "accent"),
    "recommend_reject": ("不建议", "high"),
    "declined_by_user": ("你已否", "unknown"),
}
APPLICATION_ID_PATTERN = re.compile(r"app-[a-z0-9]+(?:-[a-z0-9]+)*")
DOCUMENT_MIME = {
    ".html": "text/html; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class Repo:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.state_dir = root / SYSTEM_DIR / "state"

    def load(self, name: str) -> dict:
        path = self.state_dir / name
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise RuntimeError(f"无法读取状态文件 {path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"状态文件 JSON 损坏 {path}:{exc.lineno}:{exc.colno}: {exc.msg}"
            ) from exc

    def events(self, limit: int = 40) -> list[dict]:
        path = self.root / SYSTEM_DIR / "events" / "events.jsonl"
        out: list[dict] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return []
        return out[-limit:][::-1]

    def reports(self) -> list[tuple[str, str, float]]:
        base = self.root / REPORTS_DIR
        found: list[tuple[str, str, float]] = []
        if not base.is_dir():
            return found
        for path in base.rglob("*.html"):
            try:
                rel = path.relative_to(self.root).as_posix()
                found.append((rel, path.stem, path.stat().st_mtime))
            except OSError:
                continue
        found.sort(key=lambda item: item[2], reverse=True)
        return found


def esc(value) -> str:
    return html.escape("" if value is None else str(value))


def chip(text: str, tone: str) -> str:
    return f'<span class="chip chip--{tone}">{esc(text)}</span>'


CSS = """
:root{
  --paper:#eef0ec; --paper-raised:#fff; --paper-sunken:#e4e7e1;
  --ink:#1c231f; --ink-soft:#4d5750; --ink-faint:#7c857d; --line:#c9cec4;
  --accent:#2c4a72; --accent-soft:#dde5ef;
  --high:#a13a2c; --high-bg:#f4e2dd; --mid:#93691f; --mid-bg:#f1e6cd;
  --low:#2f6b49; --low-bg:#dfe9e0; --unknown:#5b6167; --unknown-bg:#e4e5e2;
  --shadow:0 1px 2px rgba(28,35,31,.06),0 6px 20px rgba(28,35,31,.05);
  --display:"Noto Serif SC","Songti SC",serif;
  --body:"Noto Sans SC","PingFang SC",sans-serif;
  --mono:"JetBrains Mono","SF Mono",Consolas,monospace;
}
@media (prefers-color-scheme:dark){:root{
  --paper:#14181a; --paper-raised:#1b2124; --paper-sunken:#101415;
  --ink:#e7e9e2; --ink-soft:#aab3a9; --ink-faint:#7c857d; --line:#313a35;
  --accent:#7fa4d1; --accent-soft:#24344a;
  --high:#e2897a; --high-bg:#3b2420; --mid:#dcb567; --mid-bg:#382e19;
  --low:#7fbf98; --low-bg:#1e2f24; --unknown:#a2a9a4; --unknown-bg:#262a27;
  --shadow:0 1px 2px rgba(0,0,0,.3),0 6px 24px rgba(0,0,0,.35);
}}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--body);line-height:1.7;-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-underline-offset:2px}
.wrap{max-width:1080px;margin:0 auto;padding:0 24px 80px}
header.top{border-bottom:1px solid var(--line);padding:36px 0 24px;margin-bottom:8px}
.eyebrow{font-family:var(--mono);font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink-faint);display:flex;align-items:center;gap:9px}
.eyebrow .dot{width:6px;height:6px;border-radius:50%;background:var(--low)}
h1{font-family:var(--display);font-weight:700;font-size:clamp(26px,4.5vw,36px);margin:14px 0 6px}
.sub{color:var(--ink-soft);font-size:15px;margin:0}
nav.tabs{display:flex;gap:8px;margin-top:20px;flex-wrap:wrap}
nav.tabs a{font-size:13px;font-weight:600;color:var(--ink-soft);text-decoration:none;padding:6px 14px;border-radius:999px;border:1px solid transparent}
nav.tabs a:hover{border-color:var(--line);color:var(--ink)}
nav.tabs a.on{background:var(--accent-soft);color:var(--accent);border-color:var(--accent)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:14px;margin:28px 0}
.card{background:var(--paper-raised);border:1px solid var(--line);border-radius:12px;padding:16px 18px;box-shadow:var(--shadow)}
.card .k{font-family:var(--mono);font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:var(--ink-faint)}
.card .v{font-family:var(--display);font-weight:700;font-size:30px;line-height:1.2;margin-top:6px}
.card .n{font-size:12.5px;color:var(--ink-faint);margin-top:2px}
.bar{height:7px;border-radius:999px;background:var(--paper-sunken);overflow:hidden;margin-top:10px}
.bar i{display:block;height:100%;background:var(--accent);border-radius:999px}
h2{font-family:var(--display);font-size:21px;margin:38px 0 6px}
h2 + .hint{color:var(--ink-soft);font-size:14px;margin:0 0 16px}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--paper-raised);box-shadow:var(--shadow)}
table{width:100%;border-collapse:collapse;font-size:13.5px;min-width:640px}
th,td{text-align:left;padding:12px 15px;border-bottom:1px solid var(--line);vertical-align:top}
thead th{font-family:var(--mono);font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-faint);font-weight:500;background:var(--paper-sunken)}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover{background:var(--paper-sunken)}
td.name{font-family:var(--display);font-weight:700;font-size:14.5px}
td .s{display:block;font-family:var(--body);font-weight:400;font-size:12px;color:var(--ink-faint);margin-top:2px}
.chip{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;padding:3px 10px;border-radius:999px;white-space:nowrap}
.chip::before{content:"";width:6px;height:6px;border-radius:50%}
.chip--high{background:var(--high-bg);color:var(--high)}.chip--high::before{background:var(--high)}
.chip--mid{background:var(--mid-bg);color:var(--mid)}.chip--mid::before{background:var(--mid)}
.chip--low{background:var(--low-bg);color:var(--low)}.chip--low::before{background:var(--low)}
.chip--unknown{background:var(--unknown-bg);color:var(--unknown)}.chip--unknown::before{background:var(--unknown)}
.chip--accent{background:var(--accent-soft);color:var(--accent)}.chip--accent::before{background:var(--accent)}
.note{background:var(--mid-bg);border:1px solid var(--mid);border-radius:10px;padding:13px 16px;font-size:14px;margin:0 0 16px;color:var(--ink)}
.note.bad{background:var(--high-bg);border-color:var(--high)}
.note b{font-family:var(--mono);font-size:12px;letter-spacing:.05em;text-transform:uppercase;margin-right:8px}
ul.plain{list-style:none;margin:0;padding:0;display:grid;gap:9px}
ul.plain li{background:var(--paper-raised);border:1px solid var(--line);border-radius:10px;padding:12px 15px;font-size:14px}
ul.plain li .m{font-family:var(--mono);font-size:11.5px;color:var(--ink-faint);display:block;margin-top:3px}
.rep{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.rep a{display:block;background:var(--paper-raised);border:1px solid var(--line);border-radius:10px;padding:14px 16px;text-decoration:none;color:var(--ink);box-shadow:var(--shadow)}
.rep a:hover{border-color:var(--accent)}
.rep .t{font-family:var(--display);font-weight:700;font-size:14.5px;line-height:1.35}
.rep .d{font-family:var(--mono);font-size:11.5px;color:var(--ink-faint);margin-top:6px}
footer{margin-top:48px;padding-top:20px;border-top:1px solid var(--line);font-size:12.5px;color:var(--ink-faint)}
.empty{padding:26px;text-align:center;color:var(--ink-faint);font-size:14px;border:1px dashed var(--line);border-radius:12px}
"""


def page(title: str, active: str, body: str) -> bytes:
    tabs = [("/", "总览"), ("/reports", "报告"), ("/events", "操作记录")]
    nav = "".join(
        f'<a href="{href}" class="{"on" if href == active else ""}">{esc(label)}</a>'
        for href, label in tabs
    )
    doc = f"""<!DOCTYPE html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<style>{CSS}{jobflow_catalog.LIST_STYLE}</style>
<div class="wrap">
<header class="top">
  <div class="eyebrow"><span class="dot"></span><span>求职看板 · 本地只读视图</span></div>
  <h1>{esc(title)}</h1>
  <p class="sub">数据直接来自 <code>00-工作流系统/state/</code>，刷新即最新。这是视图，不是第二份真相。</p>
  <nav class="tabs">{nav}</nav>
</header>
{body}
<footer>jobflow-dashboard · 读取 {esc(str(REPO.root))} · 渲染于 {datetime.now().strftime('%Y-%m-%d %H:%M')}</footer>
</div></html>"""
    # Report/Case destinations must leave the dashboard tab intact.
    doc = re.sub(r"<a\b([^>]*href=['\"]/(?:report\?|document\?|application/)[^>]*)>",
                 lambda match: '<a' + match.group(1) + ' target="_blank" rel="noopener noreferrer">' if 'target=' not in match.group(1) else match.group(0), doc)
    return doc.encode("utf-8")


def render_overview() -> bytes:
    current = REPO.load("current.json")
    apps = REPO.load("applications.json").get("applications", [])
    cands = REPO.load("candidates.json").get("candidates", [])
    tasks = REPO.load("task_queue.json").get("tasks", [])
    jobs = REPO.load("recurring_jobs.json").get("jobs", [])
    active = REPO.load("active_decider.json")
    metrics = current.get("metrics", {})

    submitted = [a for a in apps if a.get("status") in POST_SUBMISSION]
    target = metrics.get("diagnostic_sample_target")
    verified = metrics.get("submitted_verified", len(submitted))
    interviewing = [a for a in apps if a.get("status") in {"interviewing", "offer"}]
    today = date.today().isoformat()
    today_apps = [a for a in apps if str(a.get("submitted_at", "")) == today]
    awaiting = [c for c in cands if c.get("decision_state") == "awaiting_user"]
    pct = min(100, round(verified / target * 100)) if target else 0
    denominator = f'<span style="font-size:17px;color:var(--ink-faint)">/ {target}</span>' if target is not None else ""
    goal_detail = (f'<div class="bar"><i style="width:{pct}%"></i></div><div class="n">还差 {max(0, target - verified)} 家达到数量目标</div>'
                   if target is not None else "")

    cards = f"""<div class="cards">
  <div class="card"><div class="k">已验证投递</div><div class="v">{verified} {denominator}</div>
    {goal_detail}</div>
  <div class="card"><div class="k">面试中</div><div class="v">{len(interviewing)}</div><div class="n">进入面试或 offer 阶段</div></div>
  <div class="card"><div class="k">今日投递</div><div class="v">{len(today_apps)}</div><div class="n">{esc(today)}</div></div>
  <div class="card"><div class="k">候选待决</div><div class="v">{len(awaiting)}</div><div class="n">等你划投递范围</div></div>
</div>"""

    body = [cards]

    if interviewing:
        rows = "".join(
            f"<li><b><a href='/application/{esc(quote(str(a.get('application_id')), safe=''))}'>{esc(a.get('company'))}</a></b> — {esc(a.get('role'))}"
            f"<span class='m'>{esc(((a.get('case') or {}).get('current_stage') or {}).get('label') or a.get('status'))}"
            + (
                f" · {esc(((a.get('case') or {}).get('current_stage') or {}).get('updated_at'))}"
                if ((a.get("case") or {}).get("current_stage") or {}).get("updated_at")
                else ""
            )
            + "</span></li>"
            for a in interviewing
        )
        body.append(f'<h2>正在推进</h2><p class="hint">已经不只是投出去了。</p><ul class="plain">{rows}</ul>')

    # applications
    rows = []
    for a in sorted(apps, key=lambda x: str(x.get("submitted_at", "")), reverse=True):
        label, tone = STATUS_LABEL.get(str(a.get("status")), (str(a.get("status")), "unknown"))
        application_id = quote(str(a.get("application_id") or ""), safe="")
        company = esc(a.get("company"))
        if (a.get("case") or {}).get("view_path"):
            company = f"<a href='/application/{esc(application_id)}'>{company}</a>"
        rows.append(
            f"<tr><td class='name'>{company}<span class='s'>{esc(a.get('role'))}</span></td>"
            f"<td>{esc(a.get('channel'))}</td><td>{chip(label, tone)}</td>"
            f"<td>{esc(a.get('submitted_at') or '—')}</td><td>{esc(a.get('follow_up_due') or '—')}</td></tr>"
        )
    body.append(
        "<h2>投递记录</h2><p class='hint'>状态推进到面试/offer 的仍然计入已投递。</p>"
        "<div class='scroll'><table><thead><tr><th>公司 / 岗位</th><th>渠道</th><th>状态</th><th>投递日</th><th>跟进日</th></tr></thead><tbody>"
        + ("".join(rows) or "<tr><td colspan=5>暂无</td></tr>")
        + "</tbody></table></div>"
    )

    # next actions
    items = []
    statuses = {t.get("task_id"): t.get("status") for t in tasks}
    for t in sorted(tasks, key=lambda x: x.get("priority", 99)):
        if t.get("status") in {"done", "cancelled"}:
            continue
        blocked = ""
        if t.get("status") == "blocked":
            pending = [d for d in t.get("depends_on", []) if statuses.get(d) != "done"]
            if pending:
                blocked = " · 被 " + "、".join(pending) + " 阻塞"
        gate = " · 需你审批" if t.get("approval_required") else ""
        items.append(
            f"<li><b>P{esc(t.get('priority'))}</b> {esc(t.get('title'))}"
            f"<span class='m'>{esc(t.get('task_id'))} · {esc(t.get('status'))}{esc(blocked)}{esc(gate)}</span></li>"
        )
    body.append(f"<h2>下一步</h2><ul class='plain'>{''.join(items) or '<li>无</li>'}</ul>")

    # candidates awaiting
    if awaiting:
        rows = []
        for c in awaiting:
            label, tone = RECOMMENDATION_LABEL.get(
                str(c.get("recommendation")), (str(c.get("recommendation")), "unknown")
            )
            rows.append(
                f"<tr><td class='name'>{esc(c.get('company'))}<span class='s'>{esc(c.get('role'))}</span></td>"
                f"<td>{esc(c.get('salary'))}</td><td>{chip(label, tone)}</td><td>{esc(c.get('key_tradeoff'))}</td></tr>"
            )
        body.append(
            "<h2>等你拍板的候选</h2><p class='hint'>这批不定，投递任务就一直卡着。</p>"
            "<div class='scroll'><table><thead><tr><th>公司 / 岗位</th><th>薪资</th><th>建议</th><th>关键权衡</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table></div>"
        )

    # recurring jobs
    if jobs:
        items = []
        for j in jobs:
            lr = j.get("last_run") or {}
            enabled = j.get("enabled") is True
            runtime = (j.get("trigger") or {}).get("runtime_status", "unknown")
            schedule_config = j.get("schedule") or {}
            schedule_prefix = ""
            if schedule_config.get("local_time"):
                schedule_prefix = (
                    f"每天 {schedule_config.get('local_time')} "
                    f"{schedule_config.get('timezone', '')} · "
                )
            if enabled and runtime == "enabled_confirmed":
                state_label, tone = "已开启", "low"
                schedule = schedule_prefix + f"下次日期 {j.get('next_due') or '—'}"
            elif not enabled and runtime == "disabled_confirmed":
                state_label, tone = "已关闭", "unknown"
                schedule = "外部触发器已确认停用"
            elif enabled:
                state_label, tone = "开启待同步", "mid"
                schedule = f"运行时 {runtime}"
            else:
                state_label, tone = "关闭待同步", "mid"
                schedule = f"运行时 {runtime}"
            fail = j.get("consecutive_failures", 0)
            warn = f" · ⚠️ 连续失败 {fail} 次" if isinstance(fail, int) and fail >= 2 else ""
            items.append(
                f"<li><b>{esc(j.get('title'))}</b> {chip(state_label, tone)}"
                f"<span class='m'>{esc(schedule)}{esc(warn)}</span>"
                + (f"<span class='m'>关闭原因：{esc(j.get('disabled_reason'))}</span>" if j.get("disabled_reason") else "")
                + (f"<span class='m'>上一轮：{esc(lr.get('status'))}</span>" if lr.get("status") else "")
                + (f"<span class='m'>指标：{esc(json.dumps(lr.get('metrics'), ensure_ascii=False))}</span>" if lr.get("metrics") else "")
                + (f"<span class='m'>阻塞：{esc(lr.get('blocker'))}</span>" if lr.get("blocker") else "")
                + "</li>"
            )
        body.append(f"<h2>定时任务</h2><ul class='plain'>{''.join(items)}</ul>")

    # blockers
    blockers = current.get("known_blockers", [])
    if blockers:
        body.append(
            "<h2>阻塞</h2>"
            + "".join(
                f"<div class='note{' bad' if b.get('status') != 'waiting_user' else ''}'>"
                f"<b>{esc(b.get('status'))}</b>{esc(b.get('summary'))}</div>"
                for b in blockers
            )
        )

    lease = active.get("lease_expires_at")
    decider_status = str(active.get("status") or "unclaimed")
    if decider_status == "claimed" and lease:
        try:
            expiry = datetime.fromisoformat(str(lease).replace("Z", "+00:00"))
            if expiry <= datetime.now(timezone.utc):
                decider_status = "expired · 可接管"
        except ValueError:
            decider_status = "invalid lease"
    body.append(
        f"<h2>当前 Decider</h2><ul class='plain'><li><b>{esc(active.get('agent') or '未领取')}</b>"
        f"<span class='m'>{esc(active.get('backend') or '—')} · 状态 {esc(decider_status)}"
        + (f" · 租约到 {esc(lease)}" if lease else "")
        + "</span></li></ul>"
    )
    recent = '<h2>最近检索到的岗位</h2><p>每个岗位单独阅读，报告在新标签页打开。</p>' + jobflow_catalog.cards(REPO.root, lambda p: '/report?f=' + quote(p), latest_only=True)
    recent += '<p><a href="/reports">查看全部岗位与报告</a></p>'
    return page("求职看板", "/", recent + "".join(body))


def render_reports() -> bytes:
    data = jobflow_catalog.catalog(REPO.root)
    linked = {r.get("report_path") for r in data["opportunities"]}
    jobs = jobflow_catalog.cards(REPO.root, lambda p: "/report?f=" + quote(p))
    grouped = {}
    for rel, name, mtime in REPO.reports():
        if rel in linked or name.startswith("_") or "岗位速览/" in rel or name == "岗位目录":
            continue
        kind = "批次汇总" if any(word in name for word in ("汇总", "批次", "对比")) else "巡检与补充记录"
        grouped.setdefault(kind, []).append(f'<p><a href="/report?f={esc(quote(rel))}" target="_blank" rel="noopener noreferrer">{esc(name)} ↗</a></p>')
    other = "".join(f'<details><summary>{esc(kind)} · {len(rows)} 份</summary>{"".join(rows)}</details>' for kind, rows in grouped.items())
    return page("岗位与报告", "/reports", '<p>按检索日期逐个看岗位。批次汇总与巡检记录单独收纳在底部。</p>' + jobs + '<h2>其他报告</h2>' + other)


def render_events() -> bytes:
    events = REPO.events(60)
    if not events:
        return page("操作记录", "/events", "<div class='empty'>事件日志为空。</div>")
    rows = "".join(
        f"<tr><td>{esc(str(e.get('occurred_at', ''))[:19].replace('T', ' '))}</td>"
        f"<td class='name'>{esc(e.get('event_type'))}</td>"
        f"<td>{esc((e.get('actor') or {}).get('id'))}</td>"
        f"<td>{esc(e.get('summary'))}</td></tr>"
        for e in events
    )
    return page(
        "操作记录", "/events",
        "<p class='hint' style='margin-top:20px'>append-only，最近 60 条，新的在上。</p>"
        f"<div class='scroll'><table><thead><tr><th>时间</th><th>类型</th><th>执行者</th><th>摘要</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>",
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "jobflow-dashboard"

    def log_message(self, fmt, *args):  # quieter console
        return

    def _send(self, body: bytes, ctype="text/html; charset=utf-8", code=200, report=False):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if report:
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; "
                "font-src 'self' data:; script-src 'none'; connect-src 'none'; "
                "frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            )
        else:
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
                "font-src data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            )
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        route = parsed.path
        try:
            if route == "/":
                return self._send(render_overview())
            if route == "/reports":
                return self._send(render_reports())
            if route == "/events":
                return self._send(render_events())
            if route.startswith("/application/"):
                return self._serve_application(unquote(route.removeprefix("/application/")))
            if route == "/document":
                return self._serve_document(parsed.query)
            if route == "/report":
                return self._serve_report(parsed.query)
            if route == "/api/state.json":
                payload = {
                    name.replace(".json", ""): REPO.load(name)
                    for name in (
                        "current.json",
                        "applications.json",
                        "candidates.json",
                        "task_queue.json",
                        "recurring_jobs.json",
                    )
                }
                return self._send(
                    json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
                    "application/json; charset=utf-8",
                )
            self._send(page("404", "/", "<div class='empty'>没有这个页面。</div>"), code=404)
        except Exception as exc:  # keep the dashboard alive on bad state
            self._send(
                page("出错了", "/", f"<div class='note bad'><b>error</b>{esc(exc)}</div>"),
                code=500,
            )

    def _serve_report(self, query: str):
        match = re.match(r"f=(.+)$", query or "")
        if not match:
            return self._send(b"missing file", "text/plain; charset=utf-8", 400)
        # http.server decodes the request line as latin-1, so a raw UTF-8 path arrives
        # mangled. Hrefs are percent-encoded, but repair the raw case too.
        raw = match.group(1)
        try:
            raw = raw.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        rel = unquote(raw, encoding="utf-8", errors="replace")
        try:
            target = resolve_report_path(REPO.root, rel)
        except (OSError, ValueError):
            return self._send(b"bad path", "text/plain; charset=utf-8", 400)
        self._send(target.read_bytes(), report=True)

    def _serve_application(self, application_id: str):
        apps = REPO.load("applications.json").get("applications", [])
        app = next((item for item in apps if item.get("application_id") == application_id), None)
        if app is None:
            return self._send(page("404", "/", "<div class='empty'>没有这个 application。</div>"), code=404)
        view_path = (app.get("case") or {}).get("view_path")
        if not view_path:
            return self._send(page("未建立 Case", "/", "<div class='empty'>这个申请还没有面试 Case。</div>"), code=404)
        try:
            target = resolve_case_path(REPO.root, str(view_path), application_id)
        except (OSError, ValueError):
            return self._send(page("Case 路径错误", "/", "<div class='note bad'>Case 视图路径无效。</div>"), code=500)
        return self._send(target.read_bytes(), report=True)

    def _serve_document(self, query: str):
        match = re.match(r"f=(.+)$", query or "")
        if not match:
            return self._send(b"missing file", "text/plain; charset=utf-8", 400)
        relative = unquote(match.group(1), encoding="utf-8", errors="replace")
        try:
            target = resolve_document_path(REPO.root, relative)
        except (OSError, ValueError):
            return self._send(b"forbidden", "text/plain; charset=utf-8", 403)
        ctype = DOCUMENT_MIME[target.suffix.lower()]
        return self._send(target.read_bytes(), ctype=ctype, report=target.suffix.lower() == ".html")


def resolve_report_path(repo_root: Path, rel: str) -> Path:
    """Return a report HTML path, rejecting traversal and all other files."""
    base = (repo_root / REPORTS_DIR).resolve()
    target = (repo_root / rel).resolve()
    if base not in target.parents or target.suffix.lower() != ".html" or not target.is_file():
        raise ValueError("report path is outside the allowed HTML directory")
    return target


def resolve_case_path(repo_root: Path, rel: str, application_id: str) -> Path:
    if not APPLICATION_ID_PATTERN.fullmatch(application_id):
        raise ValueError("unsafe application ID")
    case_root = (repo_root / "04-面试" / "公司").resolve()
    expected = case_root / application_id / "index.html"
    target = (repo_root / rel).resolve()
    if case_root not in expected.parents or target != expected or not target.is_file():
        raise ValueError("case path does not match canonical application ID")
    return target


def resolve_document_path(repo_root: Path, rel: str) -> Path:
    allowed_roots = [
        (repo_root / "02-策略").resolve(),
        (repo_root / "03-简历").resolve(),
        (repo_root / "04-面试").resolve(),
        (repo_root / "05-检索报告").resolve(),
        (repo_root / "06-证据").resolve(),
    ]
    raw = repo_root / rel
    target = raw.resolve()
    allowed_suffixes = set(DOCUMENT_MIME)
    if raw.is_symlink() or not target.is_file() or target.suffix.lower() not in allowed_suffixes:
        raise ValueError("document is not an allowed file")
    if not any(root == target.parent or root in target.parents for root in allowed_roots):
        raise ValueError("document is outside allowed roots")
    return target


def browser_open_command(browser: str, url: str) -> list[str] | None:
    if browser == "none":
        return None
    if browser == "chrome":
        return ["open", "-a", "Google Chrome", url]
    if browser == "default":
        return ["open", url]
    raise ValueError(f"unknown browser: {browser}")


REPO = Repo(DEFAULT_REPO)


def main() -> int:
    parser = argparse.ArgumentParser(description="Local job-search dashboard (read-only)")
    parser.add_argument("--repo", default=os.environ.get("JOBFLOW_REPO", str(DEFAULT_REPO)))
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--open", action="store_true", help="open the browser")
    parser.add_argument(
        "--browser",
        choices=["chrome", "default", "none"],
        default="chrome",
        help="browser used with --open; defaults to Google Chrome",
    )
    args = parser.parse_args()

    global REPO
    REPO = Repo(Path(args.repo).expanduser().resolve())
    if not REPO.state_dir.is_dir():
        print(f"找不到状态目录：{REPO.state_dir}")
        return 1

    url = f"http://127.0.0.1:{args.port}/"
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"求职看板已启动：{url}\n读取仓库：{REPO.root}\n按 Ctrl+C 停止。")
    if args.open:
        command = browser_open_command(args.browser, url)
        if command:
            try:
                subprocess.run(command, check=True)
            except (OSError, subprocess.CalledProcessError) as exc:
                print(
                    f"无法用 {args.browser} 打开浏览器：{exc}\n"
                    f"请确认 Google Chrome 已安装，或手动打开：{url}"
                )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
