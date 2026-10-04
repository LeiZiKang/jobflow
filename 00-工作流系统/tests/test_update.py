"""No network: HTTP and updater subprocesses are injected."""
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

BIN = Path(__file__).resolve().parents[1] / 'bin'
sys.path.insert(0, str(BIN))
import jobflow_update as update
import jobflow_migrations as migrations
from jobflow import JobflowRepo


class TempCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'repo'
        self.root.mkdir()
        (self.root / 'VERSION').write_text('1.1.0\n')
        self.env = patch.dict(os.environ, {'JOBFLOW_PROFILE_DIR': str(self.base / 'profile'),
            'JOBFLOW_RUNTIME_DIR': str(self.base / 'runtime'), 'JOBFLOW_UPDATE_CHECK': '1',
            'JOBFLOW_UPDATE_REPO': 'LeiZiKang/jobflow'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.calls = []


class UpdateTests(TempCase):
    def http(self, request, timeout):
        self.calls.append((request, timeout))
        return io.StringIO(json.dumps({'tag_name': 'v1.2.0', 'body': 'one\ntwo', 'html_url': 'https://untrusted.invalid'}))

    def test_cache_force_expiry_disabled_and_privacy(self):
        result = update.check(self.root, opener=self.http, now=100)
        self.assertTrue(result['update_available'])
        request, timeout = self.calls[0]
        self.assertEqual(timeout, 5)
        self.assertEqual(request.full_url, 'https://api.github.com/repos/LeiZiKang/jobflow/releases/latest')
        self.assertEqual(request.get_header('User-agent'), 'jobflow/1.1.0')
        self.assertIsNone(request.data)
        self.assertIsNone(request.get_header('Authorization'))
        self.assertEqual(result['release_url'], 'https://github.com/LeiZiKang/jobflow/releases/tag/v1.2.0')
        update.check(self.root, opener=self.http, now=101)
        self.assertEqual(len(self.calls), 1)
        update.check(self.root, opener=self.http, now=102, force=True)
        self.assertEqual(len(self.calls), 2)
        update.check(self.root, opener=self.http, now=102 + update.CACHE_SECONDS)
        self.assertEqual(len(self.calls), 3)
        with patch.dict(os.environ, JOBFLOW_UPDATE_CHECK='0'):
            self.assertEqual(update.check(self.root, opener=self.http, force=True)['status'], 'disabled')
            self.assertEqual(len(self.calls), 3)

    def test_concurrent_checks_share_one_request(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: update.check(self.root, opener=self.http, now=100), range(4)))
        self.assertTrue(all(r['status'] == 'ok' for r in results))
        self.assertEqual(len(self.calls), 1)

    def test_failure_is_cached_no_retry_and_bad_cache_is_safe(self):
        calls = []
        def fail(*args, **kwargs):
            calls.append(1)
            raise OSError('private proxy error')
        self.assertEqual(update.check(self.root, opener=fail, now=100)['status'], 'failed')
        self.assertEqual(update.check(self.root, opener=fail, now=101)['status'], 'failed')
        self.assertEqual(calls, [1])
        path = self.base / 'runtime/update-check.json'
        path.write_text('broken')
        self.assertTrue(update.cached_status(self.root)['stale'])
        path.write_text('[]')
        self.assertTrue(update.cached_status(self.root)['stale'])

    def test_fork_and_current_version_recalculated(self):
        update.check(self.root, opener=self.http, now=100)
        (self.root / 'VERSION').write_text('1.2.0')
        self.assertFalse(update.cached_status(self.root, now=101)['update_available'])
        with patch.dict(os.environ, JOBFLOW_UPDATE_REPO='someone/fork'):
            self.assertTrue(update.cached_status(self.root, now=101)['stale'])
            update.check(self.root, opener=self.http, now=101)
            self.assertIn('/someone/fork/', self.calls[-1][0].full_url)

    def test_semver(self):
        self.assertGreater(update.semver('1.10.0'), update.semver('1.9.0'))
        self.assertGreater(update.semver('1.0.0'), update.semver('1.0.0-rc.2'))
        self.assertGreater(update.semver('1.0.0-rc.10'), update.semver('1.0.0-rc.2'))
        self.assertEqual(update.semver('1.0.0+build'), update.semver('1.0.0'))
        for value in ('1.0', '../x', '01.0.0', '1.0.0-01', '1.0.0-a..b'):
            with self.assertRaises(ValueError): update.semver(value)

    def runner(self, args, **kwargs):
        self.calls.append(args)
        out = ''
        if args[1:3] == ['rev-parse', '--show-toplevel']: out = str(self.root)
        elif args[1:3] == ['branch', '--show-current']: out = 'main'
        elif args[1:2] == ['show']: out = '1.2.0'
        elif args[1:2] == ['merge']: (self.root / 'VERSION').write_text('1.2.0')
        elif args[-1] == 'migrate': out = json.dumps({'status': 'migrated', 'backup': '/tmp/fixture-backup'})
        return SimpleNamespace(returncode=0, stdout=out, stderr='')

    def release(self, *args, **kwargs):
        return dict(status='ok', current_version='1.1.0', latest_version='1.2.0',
                    update_available=True, release_url='https://github.com/LeiZiKang/jobflow/releases/tag/v1.2.0', notes=[])

    def test_update_consent_sequence_and_dirty_block(self):
        self.assertEqual(update.perform_update(self.root, checker=self.release, runner=self.runner, ask=lambda _: 'n'), 0)
        self.assertFalse(any('fetch' in c for c in self.calls))
        self.calls.clear()
        self.assertEqual(update.perform_update(self.root, yes=True, checker=self.release, runner=self.runner), 0)
        commands = [c[1] for c in self.calls if c[0] == 'git']
        self.assertLess(commands.index('fetch'), commands.index('merge'))
        self.assertIn(['git', 'merge', '--ff-only', 'refs/tags/v1.2.0'], self.calls)
        self.assertEqual([c[-1] for c in self.calls[-3:]], ['migrate', 'doctor', '00-工作流系统/scripts/check-all.sh'])
        self.calls.clear()
        def dirty(args, **kwargs):
            result = self.runner(args, **kwargs)
            if args[1] == 'status': result.stdout = ' M README.md\n?? local.py'
            return result
        self.assertEqual(update.perform_update(self.root, yes=True, checker=self.release, runner=dirty), 1)
        self.assertFalse(any('fetch' in c for c in self.calls))

    def test_failures_stop_later_steps(self):
        for fail_at in ('fetch', 'merge', 'migrate', 'doctor'):
            self.calls.clear()
            def fail(args, **kwargs):
                result = self.runner(args, **kwargs)
                if fail_at in args: result.returncode = 1
                return result
            self.assertEqual(update.perform_update(self.root, yes=True, checker=self.release, runner=fail), 1)
            self.assertFalse(any(c[-1] == '00-工作流系统/scripts/check-all.sh' for c in self.calls))


class MigrationTests(TempCase):
    def setUp(self):
        super().setUp()
        shutil.copytree(BIN.parent, self.root / BIN.parent.name,
            ignore=shutil.ignore_patterns('state', 'events', 'evidence', 'approvals', '.init-backup-*', '.migrate-backup-*', '__pycache__'))
        self.repo = JobflowRepo(self.root / BIN.parent.name)
        self.repo.init_workspace()
        current = self.repo.load('current.json')
        del current['workspace_version']
        (self.repo.state_dir / 'current.json').write_text(json.dumps(current))

    def snapshot(self):
        return {str(p.relative_to(self.repo.system_dir)): p.read_bytes()
                for name in migrations.BACKUP_NAMES for p in [self.repo.system_dir / name, *(self.repo.system_dir / name).rglob('*')]
                if p.is_file()}

    def test_dry_run_migration_idempotence(self):
        before = self.snapshot()
        self.assertEqual(migrations.migrate(self.repo, dry_run=True)['status'], 'dry_run')
        self.assertEqual(before, self.snapshot())
        self.assertFalse(list(self.repo.system_dir.glob('.migrate-backup-*')))
        result = migrations.migrate(self.repo)
        self.assertEqual(result['status'], 'migrated')
        self.assertTrue(self.repo.validate().ok)
        after = self.snapshot()
        self.assertEqual(migrations.migrate(self.repo)['status'], 'up_to_date')
        self.assertEqual(after, self.snapshot())
        self.assertEqual(len(list(self.repo.system_dir.glob('.migrate-backup-*'))), 1)

    def test_validation_failure_restores_all_bytes(self):
        before = self.snapshot()
        def broken(repo):
            migrations.to_110(repo)
            (repo.system_dir / 'evidence/new-file').write_text('new')
            (repo.system_dir / 'events/events.jsonl').write_text('broken')
            (repo.system_dir / 'DECIDER_BRIEF.md').write_text('broken')
        with patch.object(migrations, 'MIGRATIONS', [('1.0.0', '1.1.0', broken)]):
            with self.assertRaisesRegex(ValueError, '数据已恢复'):
                migrations.migrate(self.repo)
        self.assertEqual(before, self.snapshot())
        self.assertTrue(self.repo.validate().ok)

class LegacyMigrationTests(TempCase):
    def test_real_v100_init_empty_and_demo(self):
        import subprocess
        source = BIN.parents[1]
        files = subprocess.run(['git', 'ls-tree', '-rz', '--name-only', 'v1.0.0', '00-工作流系统/bin'],
                               cwd=source, capture_output=True, text=True)
        if files.returncode or not files.stdout.strip():
            self.skipTest('v1.0.0 tag unavailable in this source archive; run in full git checkout')
        for demo in (False, True):
            with self.subTest(demo=demo):
                old = self.base / ('old-demo' if demo else 'old-empty')
                shutil.copytree(BIN.parent, old / BIN.parent.name,
                    ignore=shutil.ignore_patterns('state', 'events', 'evidence', 'approvals', '.init-backup-*', '.migrate-backup-*', '__pycache__'))
                shutil.rmtree(old / BIN.parent.name / 'bin')
                for name in files.stdout.strip('\0').split('\0'):
                    path = old / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(subprocess.check_output(['git', 'show', f'v1.0.0:{name}'], cwd=source))
                command = [sys.executable, str(old / BIN.parent.name / 'bin/jobflow.py'), 'init']
                result = subprocess.run(command + (['--demo'] if demo else []), capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                repo = JobflowRepo(old / BIN.parent.name)
                before = repo.load('current.json')
                self.assertNotIn('workspace_version', before)
                # Compare the full state shape from old init with current init.
                new = self.base / ('new-demo' if demo else 'new-empty')
                shutil.copytree(BIN.parent, new / BIN.parent.name,
                    ignore=shutil.ignore_patterns('state', 'events', 'evidence', 'approvals', '.init-backup-*', '.migrate-backup-*', '__pycache__'))
                (new / 'VERSION').write_text('1.1.0')
                fresh = JobflowRepo(new / BIN.parent.name)
                fresh.init_workspace(demo=demo)
                def shape(value):
                    if isinstance(value, dict):
                        return {k: shape(v) for k, v in value.items() if k != 'workspace_version'}
                    if isinstance(value, list):
                        return [shape(v) for v in value]
                    return type(value).__name__
                self.assertEqual({p.name: shape(json.loads(p.read_text())) for p in repo.state_dir.glob('*.json')},
                                 {p.name: shape(json.loads(p.read_text())) for p in fresh.state_dir.glob('*.json')})
                (old / 'VERSION').write_text('1.1.0')
                result = migrations.migrate(repo)
                self.assertEqual(result['status'], 'migrated')
                after = repo.load('current.json')
                self.assertEqual(after.pop('workspace_version'), '1.1.0')
                self.assertEqual(after, before)
                self.assertTrue(repo.validate().ok)
                self.assertEqual(migrations.migrate(repo)['status'], 'up_to_date')
