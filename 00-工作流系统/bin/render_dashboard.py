#!/usr/bin/env python3
"""从 canonical state 生成本地求职看板 HTML。

只读 state/，不修改任何状态。输出到仓库根目录的 求职看板.html。

暗色是基色：部分应用内嵌预览会强制按 light 渲染静态 HTML，只写
@media dark 的页面在实际阅读场景里等于没做。

用法：python3 00-工作流系统/bin/render_dashboard.py [--out PATH]
"""
import argparse
import jobflow_catalog
import datetime as dt
import html
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
STATE = REPO / "00-工作流系统" / "state"

# 投递状态 → (显示名, 色档)
APP_STATUS = {
    "draft": ("草稿", "n"),
    "application_prepared": ("表单已备", "w"),
    "submitted_unverified": ("已提交·未验证", "w"),
    "submitted_verified": ("已投·已验证", "g"),
    "interviewing": ("面试中", "g"),
    "offer": ("Offer", "g"),
    "rejected": ("被拒", "b"),
    "closed": ("已关闭", "n"),
    "withdrawn": ("已撤回", "n"),
}

# on trace = 已投递且尚未关闭。
ON_TRACE_STATUSES = {
    "application_prepared", "awaiting_final_submit", "submitted_unverified",
    "submitted_verified", "screened", "interviewing", "follow_up_due", "offer",
}
CLOSED_STATUSES = {"closed", "rejected", "withdrawn"}

CAND_STATE = {
    "awaiting_user": ("等你拍板", "w"),
    "approved": ("已批准", "g"),
    "declined": ("你已否决", "b"),
    "not_approved": ("未批准", "n"),
    "applied": ("已投递", "g"),
}


def load(name):
    p = STATE / name
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def esc(v):
    return html.escape(str(v)) if v is not None else ""


def chip(text, cls):
    return f'<span class="chip {cls}">{esc(text)}</span>'


def rel_href(path):
    """state 里的路径都是仓库相对路径，看板也放在仓库根，直接用。"""
    return esc(path) if path else ""


def overdue_days(due, today):
    if not due:
        return None
    try:
        d = dt.date.fromisoformat(str(due)[:10])
    except ValueError:
        return None
    return (today - d).days


def days_since(date_str, today):
    if not date_str:
        return None
    try:
        d = dt.date.fromisoformat(str(date_str)[:10])
    except ValueError:
        return None
    return (today - d).days


def build_on_trace(apps, today):
    """On trace = 已投递且未关闭。每行给出进度与投递龄天数。"""
    rows = []
    for a in apps:
        st = a.get("status", "")
        if st not in ON_TRACE_STATUSES:
            continue
        label, cls = APP_STATUS.get(st, (st, "n"))
        case = a.get("case") or {}
        stage = (case.get("current_stage") or {}).get("label")
        readback = a.get("platform_readback") or ""
        # 进度：优先 case stage，其次平台回执
        # 顺序要紧：先判否定式，避免「未回复」被当成「回复」
        if stage:
            progress = esc(stage)
        elif "对方回复" in readback or "可以聊聊" in readback or "已回复" in readback:
            progress = '<span class="chip g">对方已回复</span>'
        elif "已读" in readback and ("未回" in readback or "没回" in readback):
            progress = '<span class="chip w">已读未回</span>'
        elif "已读" in readback:
            progress = '<span class="chip w">已读</span>'
        elif "送达" in readback:
            progress = '<span class="chip n">送达未读</span>'
        else:
            progress = '<span class="dim">无平台回执</span>'

        silent = days_since(a.get("submitted_at"), today)
        if silent is None:
            sil = '<span class="dim">—</span>'
        elif silent >= 14:
            sil = f'<span class="alarm">{silent} 天</span>'
        elif silent >= 7:
            sil = f'<span class="warnnum">{silent} 天</span>'
        else:
            sil = f'{silent} 天'

        due = a.get("follow_up_due")
        od = overdue_days(due, today)
        if a.get("follow_up_state") in {"cancelled", "completed"}:
            fu = '<span class="dim">已取消</span>'
        elif od is None:
            fu = '<span class="dim">未设定</span>'
        elif od > 0:
            fu = f'<span class="alarm">逾期 {od} 天</span>'
        else:
            fu = esc(due)

        view = case.get("view_path")
        case_cell = f'<a href="{rel_href(view)}" target="_blank" rel="noopener noreferrer">Case</a>' if view else '<span class="dim">—</span>'

        rows.append(f"""<tr>
  <td><b>{esc(a.get('company'))}</b><div class="dim">{esc(a.get('role'))}</div></td>
  <td>{esc(a.get('channel'))}</td>
  <td>{esc(a.get('submitted_at') or '—')}</td>
  <td>{chip(label, cls)}</td>
  <td>{progress}</td>
  <td>{sil}</td>
  <td>{fu}</td>
  <td>{case_cell}</td>
</tr>""")
    return "\n".join(rows)


def build_applications(apps, today):
    rows = []
    for a in apps:
        st = a.get("status", "")
        label, cls = APP_STATUS.get(st, (st, "n"))
        case = a.get("case") or {}
        stage = (case.get("current_stage") or {}).get("label") or "—"
        waiting = (case.get("waiting_on") or {}).get("summary") or ""
        view = case.get("view_path")
        case_cell = f'<a href="{rel_href(view)}" target="_blank" rel="noopener noreferrer">打开 Case</a>' if view else '<span class="dim">—</span>'

        due = a.get("follow_up_due")
        od = overdue_days(due, today)
        if a.get("follow_up_state") in {"cancelled", "completed"}:
            fu = '<span class="dim">已取消</span>'
        elif od is None:
            fu = '<span class="dim">未设定</span>'
        elif od > 0:
            fu = f'<span class="alarm">逾期 {od} 天</span><br><span class="dim">{esc(due)}</span>'
        else:
            fu = f'{esc(due)}'

        rows.append(f"""<tr>
  <td><b>{esc(a.get('company'))}</b><div class="dim">{esc(a.get('role'))}</div></td>
  <td>{esc(a.get('channel'))}</td>
  <td>{esc(a.get('submitted_at') or '—')}</td>
  <td>{chip(label, cls)}</td>
  <td>{esc(stage)}<div class="dim">{esc(waiting)}</div></td>
  <td>{fu}</td>
  <td>{case_cell}</td>
</tr>""")
    return "\n".join(rows)


def build_candidates(cands, want, today):
    rows = []
    for c in cands:
        ds = c.get("decision_state") or "awaiting_user"
        if want == "open" and ds not in ("awaiting_user",):
            continue
        if want == "closed" and ds in ("awaiting_user",):
            continue
        label, cls = CAND_STATE.get(ds, (ds, "n"))
        dossier = c.get("dossier")
        dcell = f'<a href="{rel_href(dossier)}" target="_blank" rel="noopener noreferrer">档案</a>' if dossier else '<span class="dim">未建档</span>'
        note = c.get("decision_note") or c.get("key_tradeoff") or ""
        rows.append(f"""<tr>
  <td><b>{esc(c.get('company'))}</b><div class="dim">{esc(c.get('role'))}</div></td>
  <td>{esc(c.get('salary') or '—')}</td>
  <td>{esc(c.get('channel') or '—')}</td>
  <td>{chip(label, cls)}</td>
  <td class="note">{esc(note)}</td>
  <td>{dcell}</td>
</tr>""")
    return "\n".join(rows)


CSS = """
:root{--bg:#15161a;--card:#1e1f25;--card2:#24252d;--ink:#e9e7e4;--sub:#9a97a2;
 --line:#32333c;--accent:#7ca6ff;--good:#5ee08a;--good-bg:#12331f;--warn:#f5c451;
 --warn-bg:#3a2e10;--bad:#f88b8b;--bad-bg:#3b1518;--nb:#2b2c35;--n:#b9b6c0}
@media (prefers-color-scheme: light){
 :root{--bg:#faf9f7;--card:#fff;--card2:#f4f2ee;--ink:#1a1a1a;--sub:#666;
  --line:#e5e1da;--accent:#1d4ed8;--good:#166534;--good-bg:#dcfce7;--warn:#92400e;
  --warn-bg:#fef3c7;--bad:#991b1b;--bad-bg:#fee2e2;--nb:#eeece8;--n:#555}}
*{box-sizing:border-box}
body{font-family:"Noto Sans SC",-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;
 background:var(--bg);color:var(--ink);margin:0;padding:30px 18px;line-height:1.65;font-size:14px}
.wrap{max-width:1180px;margin:0 auto}
h1{font-size:22px;margin:0 0 5px}
.sub{color:var(--sub);font-size:12.5px;margin-bottom:22px}
.kpis{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:26px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:7px;padding:12px 16px;min-width:130px}
.kpi .v{font-size:24px;font-weight:700;line-height:1.2}
.kpi .l{font-size:11.5px;color:var(--sub);margin-top:2px}
.kpi.alarm .v{color:var(--bad)}
h2{font-size:15.5px;margin:30px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--line)}
h2 .cnt{color:var(--sub);font-weight:400;font-size:12.5px;margin-left:6px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);
 border-radius:7px;overflow:hidden;font-size:13px}
th{text-align:left;padding:9px 11px;background:var(--card2);color:var(--sub);
 font-size:11.5px;font-weight:600;white-space:nowrap;border-bottom:1px solid var(--line)}
td{padding:9px 11px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:none}
.dim{color:var(--sub);font-size:12px}
.note{color:var(--sub);font-size:12px;max-width:330px}
.alarm{color:var(--bad);font-weight:600}
.warnnum{color:var(--warn);font-weight:600}
.ontrace{border:1px solid var(--good);border-radius:8px;padding:2px;margin-bottom:6px}
.chip{display:inline-block;padding:2px 9px;border-radius:11px;font-size:11.5px;font-weight:700;white-space:nowrap}
.g{background:var(--good-bg);color:var(--good)}
.w{background:var(--warn-bg);color:var(--warn)}
.b{background:var(--bad-bg);color:var(--bad)}
.n{background:var(--nb);color:var(--n)}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.empty{padding:14px;color:var(--sub);background:var(--card);border:1px solid var(--line);border-radius:7px}
.foot{margin-top:30px;padding-top:14px;border-top:1px solid var(--line);font-size:12px;color:var(--sub)}
"""


def render(repo_root=None):
    root = pathlib.Path(repo_root or REPO)
    def load(name):
        return json.loads((root / "00-工作流系统" / "state" / name).read_text(encoding="utf-8"))
    apps = load("applications.json").get("applications", [])
    cands = load("candidates.json").get("candidates", [])
    cur = load("current.json")
    today = dt.date.fromisoformat(str(cur.get("updated_at"))[:10])

    metrics = cur.get("metrics", {})
    # 以 canonical metrics 为准：关闭记录仍可计入历史已验证投递数。
    # 自行重算会与 state 冲突，按宪章「state 是权威」不自行覆盖。
    verified = metrics.get("submitted_verified",
                           sum(1 for a in apps if a.get("status") == "submitted_verified"))
    on_trace = [a for a in apps if a.get("status") in ON_TRACE_STATUSES]
    live = len(on_trace)
    closed = sum(1 for a in apps if a.get("status") in CLOSED_STATUSES)
    target = metrics.get("diagnostic_sample_target", 15)
    od = sum(1 for a in apps
             if a.get("follow_up_state") != "cancelled"
             and (overdue_days(a.get("follow_up_due"), today) or 0) > 0)
    waiting = sum(1 for c in cands if (c.get("decision_state") or "awaiting_user") == "awaiting_user")

    on_trace_rows = build_on_trace(apps, today)
    open_rows = build_candidates(cands, "open", today)
    closed_rows = build_candidates(cands, "closed", today)

    doc = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>求职看板</title><style>{CSS}{jobflow_catalog.LIST_STYLE}</style></head><body><div class="wrap">
<h1>求职看板</h1>
<div class="sub">生成于 {today.isoformat()} · 数据源 <code>00-工作流系统/state/</code> ·
重新生成：<code>python3 00-工作流系统/bin/render_dashboard.py</code></div>

<h2>最近检索到的岗位</h2>
<p class="dim">按岗位逐个阅读；报告在新标签页打开，当前列表会保留。</p>
{jobflow_catalog.cards(root, lambda p: p, latest_only=True)}
<p><a href="05-检索报告/岗位目录.html" target="_blank" rel="noopener noreferrer">查看全部检索岗位 ↗</a></p>
<div class="kpis">
  <div class="kpi"><div class="v">{verified} / {target}</div><div class="l">已验证投递 / 诊断样本目标</div></div>
  <div class="kpi"><div class="v">{live}</div><div class="l">On trace（已投未关闭）</div></div>
  <div class="kpi"><div class="v">{closed}</div><div class="l">已关闭 / 被拒</div></div>
  <div class="kpi{' alarm' if od else ''}"><div class="v">{od}</div><div class="l">跟进逾期</div></div>
  <div class="kpi"><div class="v">{waiting}</div><div class="l">候选等你拍板</div></div>
</div>

<h2>On trace<span class="cnt">{live} 个岗位仍在跟进</span></h2>
{f'<table><tr><th>公司 / 岗位</th><th>渠道</th><th>投递日</th><th>状态</th><th>进度</th><th>投递龄</th><th>跟进</th><th></th></tr>{on_trace_rows}</table>' if on_trace_rows else '<div class="empty">当前没有在跟进的投递。</div>'}
<div class="dim" style="margin-top:8px">On trace = 已投递且未被标记关闭。「投递龄」是距投递日的天数，不代表距最近回复的时间，≥14 天标红。<b>关闭要显式操作</b>，不会自动消失。</div>

<h2>全部投递记录<span class="cnt">{len(apps)} 条</span></h2>
<table>
<tr><th>公司 / 岗位</th><th>渠道</th><th>投递日</th><th>状态</th><th>当前进展</th><th>跟进</th><th>Case</th></tr>
{build_applications(apps, today)}
</table>

<h2>候选池 · 等你拍板<span class="cnt">{waiting} 个</span></h2>
{f'<table><tr><th>公司 / 岗位</th><th>薪资</th><th>渠道</th><th>状态</th><th>关键权衡</th><th>档案</th></tr>{open_rows}</table>' if open_rows else '<div class="empty">没有等待决定的候选。</div>'}

<h2>候选池 · 已否决 / 已关闭<span class="cnt">{len(cands) - waiting} 个</span></h2>
{f'<table><tr><th>公司 / 岗位</th><th>薪资</th><th>渠道</th><th>状态</th><th>否决理由</th><th>档案</th></tr>{closed_rows}</table>' if closed_rows else '<div class="empty">暂无。</div>'}

<p><a href="00-工作流系统/推进求职.html">打开推进求职：看今天可以做什么</a></p>
<div class="foot">
本页由 state 生成，<b>不要手改</b>——改了下次重新生成就没了。状态变更走
<code>jobflow.py set-application-status</code> 和 <code>decide-candidates</code>。<br>
「已关闭」不等于「被雇主拒绝」：关闭原因以结构化状态和证据记录为准。
</div>
</div></body></html>"""

    return doc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO / "求职看板.html"))
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    out = pathlib.Path(args.out)
    doc = render()
    if args.check:
        if not out.is_file() or out.read_text(encoding="utf-8") != doc:
            print("stale dashboard; run jobflow.py render-views --write")
            return 1
        print("OK: generated dashboard is current")
    else:
        out.write_text(doc, encoding="utf-8")
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
