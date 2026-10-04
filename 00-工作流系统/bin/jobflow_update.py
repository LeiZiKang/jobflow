"""Anonymous release checks and consent-gated fast-forward updates (stdlib only)."""
from __future__ import annotations

import json
import fcntl
import os
import platform
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen

from jobflow_paths import default_runtime_dir

UPDATE_REPO = 'LeiZiKang/jobflow'
CACHE_SECONDS = 24 * 60 * 60


def version(root):
    path = Path(root) / 'VERSION'
    return path.read_text().strip() if path.exists() else '1.0.0'


def semver(value):
    match = re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?', value)
    if not match:
        raise ValueError('Invalid semantic version')
    major, minor, patch, pre, build = match.groups()
    for part in (pre, build):
        if part is not None and any(not item for item in part.split('.')):
            raise ValueError('Invalid semantic version')
    if pre and any(p.isdigit() and len(p) > 1 and p.startswith('0') for p in pre.split('.')):
        raise ValueError('Invalid semantic version')
    return (int(major), int(minor), int(patch), pre is None,
            tuple((0, int(p)) if p.isdigit() else (1, p) for p in pre.split('.')) if pre else ())


def repository():
    value = os.environ.get('JOBFLOW_UPDATE_REPO', UPDATE_REPO)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', value) or '..' in value:
        raise ValueError('JOBFLOW_UPDATE_REPO must be owner/repo')
    return value


def cached_status(root, runtime=None, now=None):
    result = dict(status='unchecked', current_version=version(root), latest_version=None,
                  update_available=False, release_url=None, notes=[], checked_at=None, stale=True)
    if os.environ.get('JOBFLOW_UPDATE_CHECK') == '0':
        return {**result, 'status': 'disabled', 'stale': False}
    try:
        cache = json.loads(((runtime or default_runtime_dir()) / 'update-check.json').read_text())
        age = (time.time() if now is None else now) - cache['checked_at']
        if cache['repository'] != repository() or not 0 <= age < CACHE_SECONDS:
            return result
        if cache['status'] not in ('ok', 'failed'):
            return result
        if cache['status'] == 'ok':
            expected = f"https://github.com/{repository()}/releases/tag/v{cache['latest_version']}"
            if cache['release_url'] != expected or not isinstance(cache['notes'], list):
                return result
            cache['update_available'] = semver(cache['latest_version']) > semver(version(root))
        return {**cache, 'current_version': version(root), 'stale': False}
    except (OSError, ValueError, TypeError, KeyError):
        return result


def check(root, *, force=False, opener=None, now=None):
    cached = cached_status(root, now=now)
    if cached['status'] == 'disabled' or (not force and not cached['stale']):
        return cached
    try:
        directory = default_runtime_dir()
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / 'update-check.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            # Re-read inside the lock so simultaneous Agent startups share one request.
            return _check(root, force=force, opener=opener, now=now)
    except OSError:
        return {**cached, 'status': 'failed', 'update_available': False}


def _check(root, *, force=False, opener=None, now=None):
    now = time.time() if now is None else now
    cached = cached_status(root, now=now)
    if cached['status'] == 'disabled' or (not force and not cached['stale']):
        return cached
    result = {**cached, 'status': 'failed', 'stale': False, 'checked_at': now,
              'update_available': False, 'latest_version': None, 'release_url': None, 'notes': []}
    try:
        repo = repository()
        result['repository'] = repo
        request = Request(f'https://api.github.com/repos/{repo}/releases/latest',
                          headers={'User-Agent': f'jobflow/{version(root)}', 'Accept': 'application/vnd.github+json'})
        with (opener or urlopen)(request, timeout=5) as response:
            payload = json.load(response)
        tag = payload['tag_name']
        if not isinstance(tag, str) or not tag.startswith('v') or payload.get('draft') or payload.get('prerelease'):
            raise ValueError('Invalid release')
        latest = tag[1:]
        available = semver(latest) > semver(version(root))
        # Construct the public link rather than trusting an arbitrary API URL.
        result.update(status='ok', latest_version=latest, update_available=available,
                      release_url=f'https://github.com/{repo}/releases/tag/{tag}',
                      notes=[''.join(c for c in line if c.isprintable()) for line in (payload.get('body') or '').splitlines()[:5]])
    except Exception:
        # Proxy errors may include private URLs. Never print them or retry.
        pass
    try:
        directory = default_runtime_dir()
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', dir=directory, delete=False) as file:
            temporary = Path(file.name)
            json.dump(result, file, ensure_ascii=False)
        os.replace(temporary, directory / 'update-check.json')
    except OSError:
        pass
    return result


def describe(result):
    labels = {'disabled': '已关闭', 'failed': '检查失败', 'unchecked': '缓存缺失或过期；可运行 update --check', 'ok': '检查完成'}
    lines = [labels[result['status']], f"当前版本：{result['current_version']}",
             f"最新版本：{result['latest_version'] or '未知'}", f"有更新：{'是' if result['update_available'] else '否' if result['status'] == 'ok' else '未知'}"]
    if result['release_url']:
        lines += [result['release_url'], *result['notes']]
    return '\n'.join(lines)


def perform_update(root, *, yes=False, checker=None, runner=None, ask=input):
    root = Path(root)
    old = version(root)
    phase = '前置检查'
    data = '未改动'
    backup = None
    def run(args):
        return (runner or subprocess.run)(args, cwd=root, text=True, capture_output=True)
    def git(*args):
        response = run(['git', *args])
        if response.returncode:
            raise ValueError('无法快进到新版；请让 Agent 检查分叉历史，不会强行覆盖。' if args[0] in ('merge', 'merge-base') else 'git 操作失败；请检查仓库状态。')
        return response.stdout.strip()
    try:
        if platform.system() != 'Darwin':
            raise ValueError('目前只支持 macOS。')
        if Path(git('rev-parse', '--show-toplevel')).resolve() != root.resolve():
            raise ValueError('请在 jobflow git 仓库内更新；ZIP 用户见 README。')
        git('remote', 'get-url', 'origin')
        if git('branch', '--show-current') != 'main':
            raise ValueError('请先切回 main 分支。')
        dirty = git('status', '--porcelain', '--untracked-files=all')
        if dirty:
            print(dirty)
            raise ValueError('引擎有本地改动；可以先 git stash（未跟踪文件用 git stash -u），或交给 Agent 处理。')
        result = (checker or check)(root, force=True)
        print(describe(result))
        if result['status'] != 'ok':
            raise ValueError('未取得可用的 Release，未更新代码或数据。')
        if not result['update_available']:
            return 0
        tag = 'v' + result['latest_version']
        if not yes and ask(f'更新到 {tag}？[y/N] ').strip().lower() not in ('y', 'yes'):
            print('已取消；代码和数据未改动。')
            return 0
        lockfile = root / 'console/package-lock.json'
        lock_before = lockfile.read_bytes() if lockfile.exists() else None
        phase = 'fetch'
        git('fetch', '--tags', 'origin')
        # Refuse a tag/version mismatch before moving HEAD.
        if git('show', f'refs/tags/{tag}:VERSION') != result['latest_version']:
            raise ValueError('Release tag 与 VERSION 不一致。')
        phase = '快进合并'
        git('merge-base', '--is-ancestor', 'HEAD', f'refs/tags/{tag}')
        git('merge', '--ff-only', f'refs/tags/{tag}')
        if (lockfile.read_bytes() if lockfile.exists() else None) != lock_before:
            print('控制台 lockfile 已变化；请在 console/ 运行 npm ci（Agent 须另获依赖安装同意）。')
        # Spawn the newly installed code: never migrate with the old in-memory module.
        phase = '数据迁移'
        data = '迁移已尝试；以迁移输出为准，失败自动恢复；备份见 .migrate-backup-*'
        for command in ([sys.executable, '00-工作流系统/bin/jobflow.py', 'migrate'],
                        [sys.executable, '00-工作流系统/bin/jobflow.py', 'doctor'],
                        ['bash', '00-工作流系统/scripts/check-all.sh']):
            phase = command[-1]
            response = run(command)
            print(response.stdout)
            if response.stderr:
                print(response.stderr, file=sys.stderr)
            if response.returncode:
                if phase == 'migrate':
                    data = '迁移失败，数据已从备份恢复' if '数据已恢复' in response.stderr else '迁移未完成，数据状态须按迁移错误核实'

                raise ValueError(f'{phase} 失败（返回码 {response.returncode}）。')
            if phase == 'migrate':
                details = json.loads(response.stdout)
                backup = details.get('backup')
                data = '迁移成功' if details['status'] == 'migrated' else '未改动（无需迁移）'
        print(f'更新完成：{version(root)}')
        return 0
    except (OSError, ValueError, EOFError, KeyboardInterrupt) as exc:
        print(f'更新停止于 {phase}：{exc}\n当前版本：{version(root)}；数据：{data}。')
        print(f'回退代码：git checkout v{old}；若发生迁移，再从 {backup or "本次 .migrate-backup-*"} 恢复 state/events/evidence/approvals 和 DECIDER_BRIEF.md。')
        return 1
