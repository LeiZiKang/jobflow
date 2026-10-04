#!/usr/bin/env python3
"""Render private, read-only inbound reports from explicit local observations.

No connector, credential access, sending, scheduling or canonical-state writes.
See examples/inbound/README.md for the input contract.
"""
import argparse
from collections import Counter
from datetime import date, datetime
import hashlib
import html
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from urllib.parse import quote, unquote, urlsplit

MARKER = '<!-- generated: jobflow-inbound-digest-v1 -->'
STATUSES = {
    'ok': '已核查', 'empty': '已核查，无入站消息',
    'login_required': '需要登录', 'captcha_blocked': '验证码阻塞',
    'approval_blocked': '审批阻塞', 'unavailable': '暂不可用',
    'not_supported': '不支持消息巡检', 'not_checked': '未检查',
}
COMPLETE = {'ok', 'empty'}
SENDERS = {'self', 'recruiter', 'employer', 'unknown', 'system'}
KINDS = {'new_contact', 'application_reply', 'automatic_confirmation', 'promotion'}
LABELS = {'new_contact': '新主动联系', 'application_reply': '已投递后的回复',
          'automatic_confirmation': '自动确认', 'unknown': '发送方待确认',
          'excluded': '我方消息 / 推广（不计入）'}
SOURCE_NAMES = {'boss': 'BOSS 直聘', 'liepin': '猎聘', 'linkedin': 'LinkedIn',
                'indeed': 'Indeed', '51job': '前程无忧', 'official_ats': '官网 / ATS',
                'email': '邮箱', 'slack': 'Slack'}
STYLE = '''
:root{color-scheme:dark;--bg:#191b20;--panel:#24272e;--fg:#eeeff2;--muted:#b9bdc8;--line:#454a56;--accent:#98c5ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.7 system-ui,sans-serif}
main{max-width:1000px;margin:auto;padding:28px 22px 64px}h1{font-size:clamp(25px,5vw,38px);line-height:1.3}
h2{margin-top:32px;font-size:22px}a{color:var(--accent);overflow-wrap:anywhere}p,dd,td{overflow-wrap:anywhere}
.muted,dt{color:var(--muted)}.notice,article{border:1px solid var(--line);background:var(--panel);padding:18px;border-radius:12px;margin:14px 0}
.metrics{display:flex;gap:12px;flex-wrap:wrap}.metrics p{flex:1;min-width:140px;border:1px solid var(--line);padding:12px;border-radius:10px}
.table{overflow-x:auto}table{width:100%;border-collapse:collapse;text-align:left}th,td{padding:10px;border-bottom:1px solid var(--line);vertical-align:top}
dl{display:grid;grid-template-columns:110px 1fr;gap:7px 12px}dd{margin:0;white-space:pre-wrap}h3{margin-top:0}
@media(max-width:600px){main{padding:20px 14px}dl{grid-template-columns:1fr;gap:2px}dd{margin-bottom:10px}th,td{padding:7px;font-size:14px}}
@media(prefers-color-scheme:light){:root{color-scheme:light;--bg:#faf9f7;--panel:#fff;--fg:#252932;--muted:#545c6c;--line:#ccd1d9;--accent:#155da8}}
@media print{:root{color-scheme:light;--bg:#fff;--panel:#fff;--fg:#000;--muted:#333;--line:#aaa;--accent:#000}main{max-width:none;padding:0}article{break-inside:avoid}.table{overflow:visible}a{text-decoration:underline}}
'''


def text(value, name, required=True):
    if not isinstance(value, str) or (required and not value.strip()):
        raise ValueError(f'{name}: expected nonempty string')
    return value


def timestamp(value, name):
    text(value, name)
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError(f'{name}: invalid ISO timestamp') from exc
    if result.tzinfo is None:
        raise ValueError(f'{name}: timezone required')
    return result


def safe_ref(value):
    """Allow only HTTP(S) or local paths without traversal, URL tricks or controls."""
    text(value, 'reference')
    decoded = unquote(value)
    if any(ord(c) < 32 or ord(c) == 127 for c in decoded) or '\\' in decoded:
        raise ValueError('reference: control character or backslash')
    parsed = urlsplit(value)
    if parsed.scheme:
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('reference: only HTTP(S) without credentials permitted')
        return value
    if decoded.startswith('//') or ':' in decoded or '?' in decoded or '#' in decoded:
        raise ValueError('reference: unsafe local path')
    if '..' in PurePosixPath(decoded).parts:
        raise ValueError('reference: path traversal')
    return quote(decoded, safe='/.-_~')


def category(item):
    if item['sender_role'] == 'self' or item['kind'] == 'promotion':
        return 'excluded'
    if item['sender_role'] == 'unknown':
        return 'unknown'
    return item['kind']


def normalize(raw):
    if not isinstance(raw, dict):
        raise ValueError('input must be an object')
    day = text(raw.get('date'), 'date')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
        raise ValueError('date: expected YYYY-MM-DD')
    date.fromisoformat(day)
    window = raw.get('window')
    if not isinstance(window, dict):
        raise ValueError('window: expected {start, end}')
    start, end = (timestamp(window.get(k), f'window.{k}') for k in ('start', 'end'))
    if end <= start:
        raise ValueError('window.end must be after start')
    required = raw.get('required_sources')
    if not isinstance(required, list) or not required:
        raise ValueError('required_sources: nonempty list required; coverage must be explicit')
    for sid in required:
        text(sid, 'required_sources entry')
    if len(required) != len(set(required)):
        raise ValueError('required_sources: duplicate source')
    sources = {}
    if not isinstance(raw.get('sources'), list) or not isinstance(raw.get('items'), list):
        raise ValueError('sources and items must be lists')
    for source in raw['sources']:
        if not isinstance(source, dict):
            raise ValueError('source must be an object')
        sid = text(source.get('source_id'), 'source_id')
        if sid in sources:
            raise ValueError(f'duplicate source_id: {sid}')
        status = source.get('status')
        if status not in STATUSES:
            raise ValueError(f'{sid}: invalid status')
        source = dict(source)
        if source.get('observed_at'):
            timestamp(source['observed_at'], f'{sid}.observed_at')
        if source.get('evidence_ref'):
            safe_ref(source['evidence_ref'])
        if status in COMPLETE:
            timestamp(source.get('observed_at'), f'{sid}.observed_at')
            safe_ref(source.get('evidence_ref'))
        else:
            text(source.get('reason'), f'{sid}.reason')
            if source.get('counts') is not None:
                raise ValueError(f'{sid}: incomplete source must not supply counts (unknown is not zero)')
        if source.get('reason') is not None:
            text(source['reason'], f'{sid}.reason', required=False)
        sources[sid] = source
    for sid in required:
        sources.setdefault(sid, {'source_id': sid, 'status': 'not_checked', 'reason': '输入缺少该必查渠道的观察记录'})
    items, seen, duplicates = [], {}, 0
    for original in raw['items']:
        if not isinstance(original, dict):
            raise ValueError('item must be an object')
        item = dict(original)
        sid = text(item.get('source_id'), 'item.source_id')
        if sid not in sources:
            raise ValueError(f'{sid}: item has no source observation')
        if item.get('sender_role') not in SENDERS or item.get('kind') not in KINDS:
            raise ValueError('item: invalid sender_role or kind')
        if item['sender_role'] == 'system' and item['kind'] not in {'automatic_confirmation', 'promotion'}:
            raise ValueError('system sender cannot be counted as a human contact')
        received = timestamp(item.get('received_at'), 'received_at')
        if not start <= received <= end:
            raise ValueError('received_at outside report window')
        text(item.get('summary'), 'summary')
        safe_ref(item.get('source_ref'))
        for field in ('company', 'contact', 'role', 'recommendation', 'action_needed', 'application_id'):
            item[field] = text(item.get(field, ''), field, required=False)
        if item.get('id') is not None:
            text(item['id'], 'id')
        # Fingerprints include all provided content: similar-looking contacts are not merged.
        payload = json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        key = (sid, item.get('id') or hashlib.sha256(payload.encode()).hexdigest())
        if key in seen:
            if seen[key] != payload:
                raise ValueError(f'{sid}: conflicting observations for message id {item.get("id")}')
            duplicates += 1
            continue
        seen[key] = payload
        items.append(item)
    counts = Counter(category(item) for item in items)
    for sid, source in sources.items():
        actual = Counter(category(item) for item in items if item['source_id'] == sid)
        if source['status'] == 'empty' and any(actual[k] for k in ('new_contact', 'application_reply', 'automatic_confirmation', 'unknown')):
            raise ValueError(f'{sid}: empty conflicts with inbound items')
        supplied = source.get('counts')
        if supplied is not None:
            if not isinstance(supplied, dict):
                raise ValueError(f'{sid}.counts must be an object')
            for key, value in supplied.items():
                if key not in LABELS or type(value) is not int or value < 0 or value != actual[key]:
                    raise ValueError(f'{sid}.counts must match deduplicated item categories')
    incomplete = any(s['status'] not in COMPLETE for s in sources.values()) or bool(counts['unknown'])
    return {'date': day, 'window': dict(window), 'required_sources': required,
            'sources': list(sources.values()), 'items': sorted(items, key=lambda i: timestamp(i['received_at'], 'received_at'), reverse=True),
            'counts': dict(counts), 'duplicates_removed': duplicates, 'complete': not incomplete}


def link(ref, label=None):
    return f'<a href="{html.escape(safe_ref(ref), quote=True)}" rel="noreferrer noopener">{html.escape(label or ref)}</a>'


def page(title, body):
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>{html.escape(title)}</title><style>{STYLE}</style></head><body>{MARKER}<main>{body}</main></body></html>'''


def render_daily(data):
    e = html.escape
    count = data['counts'].get('new_contact', 0)
    total = ('' if data['complete'] else '至少 ') + str(count)
    coverage = '完整' if data['complete'] else '未完成'
    body = f'<p class="muted">私人求职资料 · 只读报告 · 不自动回复</p><h1>{e(data["date"])} 主动联系巡检</h1>'
    body += f'<p>观察窗口：{e(data["window"]["start"])} 至 {e(data["window"]["end"])}</p>'
    body += f'<div class="metrics"><p>新主动联系<br><strong>{total} 条消息</strong></p><p>巡检覆盖<br><strong>{coverage}</strong></p><p>去重移除<br><strong>{data["duplicates_removed"]} 条</strong></p></div>'
    body += '<p class="notice">未检查、受阻和不支持均不等于零条。计数按去重后的消息，不代表独立人数；未知发送方单列，不算已确认的新联系。建议仅供审核，未发送任何消息。</p>'
    body += '<h2>渠道覆盖</h2><div class="table"><table><thead><tr><th>渠道</th><th>状态 / 新联系</th><th>观察与证据</th></tr></thead><tbody>'
    for source in data['sources']:
        sid = source['source_id']
        n = sum(category(item) == 'new_contact' for item in data['items'] if item['source_id'] == sid)
        amount = str(n) if source['status'] in COMPLETE else '—（未查全）'
        evidence = link(source['evidence_ref'], '观察证据') if source.get('evidence_ref') else '暂无观察证据'
        body += f'<tr><td>{e(SOURCE_NAMES.get(sid, sid))}</td><td>{STATUSES[source["status"]]}<br>{amount}</td><td>{e(source.get("observed_at") or "未取得观察时间")}<br>{e(source.get("reason", ""))}<br>{evidence}</td></tr>'
    body += '</tbody></table></div>'
    for kind, label in LABELS.items():
        group = [i for i in data['items'] if category(i) == kind]
        body += f'<h2>{label} · {len(group)}</h2>'
        if not group:
            body += '<p class="muted">当前证据未记录此类消息。</p>'
        for item in group:
            body += f'<article><h3>{e(item["company"] or "公司未核实")} · {e(item["role"] or "岗位未核实")}</h3><dl>'
            fields = [('联系人', item['contact'] or '未核实'), ('渠道', SOURCE_NAMES.get(item['source_id'], item['source_id'])),
                      ('收到时间', item['received_at']), ('消息要点', item['summary']),
                      ('建议', item['recommendation'] or '待审核'), ('待办', item['action_needed'] or '未指定')]
            body += ''.join(f'<dt>{label}</dt><dd>{e(value)}</dd>' for label, value in fields)
            body += f'<dt>原始证据</dt><dd>{link(item["source_ref"])}</dd></dl></article>'
    body += '<p>' + link('index.html', '历史日报') + '</p>'
    return page(data['date'] + ' 主动联系巡检', body)


def _atomic_write(path, content):
    if path.is_symlink():
        raise ValueError(f'refusing symlink output: {path.name}')
    if path.exists() and MARKER not in path.read_text(encoding='utf-8'):
        raise ValueError(f'refusing to overwrite non-generated file: {path.name}')
    fd, temporary = tempfile.mkstemp(prefix='.inbound-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def generate(raw, output_dir):
    data = normalize(raw)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    daily = destination / (data['date'] + '.html')
    index = destination / 'index.html'
    # Check both destinations before writing either one.
    for path in (daily, index):
        if path.is_symlink() or (path.exists() and MARKER not in path.read_text(encoding='utf-8')):
            raise ValueError(f'refusing to overwrite existing non-generated output: {path.name}')
    _atomic_write(daily, render_daily(data))
    history = []
    for path in sorted(destination.glob('????-??-??.html'), reverse=True):
        if path.is_symlink() or not re.fullmatch(r'\d{4}-\d{2}-\d{2}\.html', path.name):
            continue
        try:
            date.fromisoformat(path.stem)
        except ValueError:
            continue
        if MARKER in path.read_text(encoding='utf-8'):
            history.append('<li>' + link(path.name, path.stem + ' 主动联系巡检报告') + '</li>')
    body = '<p class="muted">私人求职资料 · 只读报告</p><h1>主动联系巡检日报</h1><p>逐日查看渠道覆盖、消息证据和待办。未完成巡检不代表没有新联系。</p><ul>' + ''.join(history) + '</ul>'
    _atomic_write(index, page('主动联系巡检日报', body))
    return {'date': data['date'], 'complete': data['complete'], 'counts': data['counts'],
            'duplicates_removed': data['duplicates_removed'], 'report': str(daily), 'index': str(index)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--validate', action='store_true', help='validate without writing')
    args = parser.parse_args(argv)
    if not args.validate and args.output_dir is None:
        parser.error('--output-dir is required unless --validate')
    try:
        raw = json.loads(args.input.read_text(encoding='utf-8'))
        if args.validate:
            data = normalize(raw)
            result = {'valid': True, 'complete': data['complete'], 'counts': data['counts'], 'duplicates_removed': data['duplicates_removed']}
        else:
            result = generate(raw, args.output_dir)
    except (ValueError, OSError, TypeError) as exc:
        parser.exit(2, f'inbound_digest: {exc}\n')
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
