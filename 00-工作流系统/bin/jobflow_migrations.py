"""Ordered, backed-up workspace migrations. No profile or network access."""
from datetime import datetime, timezone
import shutil

from jobflow_update import version, semver
from jobflow_writes import locked, assert_owner


def to_110(repo):
    from jobflow import _atomic_write_json
    current = repo.load('current.json')
    # v1.0.0 and v1.1 seeds otherwise share exactly the same state structure.
    # Preserve explicit targets (including v1.0 demo's 15), all user data and leases.
    current['workspace_version'] = '1.1.0'
    _atomic_write_json(repo.state_dir / 'current.json', current)


MIGRATIONS = [('1.0.0', '1.1.0', to_110)]
BACKUP_NAMES = ('state', 'events', 'evidence', 'approvals', 'DECIDER_BRIEF.md')


def migrate(repo, *, dry_run=False):
    with locked(repo):
        current = repo.load('current.json').get('workspace_version', '1.0.0')
        target = version(repo.repo_root)
        if semver(current) > semver(target):
            raise ValueError('工作区版本高于引擎；不支持自动降级，请恢复匹配版本的备份。')
        steps = []
        cursor = current
        while cursor != target:
            step = next((s for s in MIGRATIONS if s[0] == cursor), None)
            if step is None or semver(step[1]) <= semver(cursor) or semver(step[1]) > semver(target):
                raise ValueError(f'没有迁移路径：{cursor} → {target}')
            steps.append(step)
            cursor = step[1]
        if not steps:
            return {'status': 'up_to_date', 'workspace_version': current, 'steps': [], 'backup': None}
        result = {'status': 'dry_run', 'workspace_version': target,
                  'steps': [f'{a} → {b}' for a, b, _ in steps], 'backup': None}
        if dry_run:
            return result
        assert_owner(repo)
        backup = repo.system_dir / ('.migrate-backup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ'))
        backup.mkdir(mode=0o700)
        # Refuse symlinks so backup/restore cannot traverse private external paths.
        for name in BACKUP_NAMES:
            source = repo.system_dir / name
            if source.is_symlink() or (source.is_dir() and any(p.is_symlink() for p in source.rglob('*'))):
                raise ValueError(f'迁移停止：{name} 中有符号链接，数据未改动。')
            if source.is_dir():
                shutil.copytree(source, backup / name)
            elif source.exists():
                shutil.copy2(source, backup / name)
        result['backup'] = str(backup)
        try:
            for _, _, function in steps:
                function(repo)
            validation = repo.validate()
            if not validation.ok:
                raise ValueError('; '.join(validation.errors))
        except Exception as exc:
            for name in BACKUP_NAMES:
                destination = repo.system_dir / name
                if destination.is_symlink() or destination.is_file():
                    destination.unlink()
                elif destination.exists():
                    shutil.rmtree(destination)
                source = backup / name
                if source.is_dir():
                    shutil.copytree(source, destination)
                elif source.exists():
                    shutil.copy2(source, destination)
            raise ValueError(f'迁移失败，数据已恢复；备份：{backup}；{exc}') from exc
        result['status'] = 'migrated'
        return result
