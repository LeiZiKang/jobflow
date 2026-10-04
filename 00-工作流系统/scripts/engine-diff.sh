#!/bin/bash
# 只读比较引擎白名单。A 是本脚本所在仓库，B 是参数指定的仓库。
# 符号链接一律跳过，避免通过引擎路径读到仓库外或用户数据。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
exec python3 - "$ROOT" "$@" <<'PY'
import difflib
import os
from pathlib import Path
import stat
import sys

ENGINE = '00-工作流系统'
SCOPES = ('bin', 'local-control', 'dashboard', 'runbooks', 'adapters',
          'schemas', 'config', 'examples', 'golden-cases', 'tests',
          'templates', 'menubar-app', 'scripts')
EXCLUDED = {'state', 'events', 'evidence', 'approvals', 'assets', '.agent-memory',
            'node_modules', '.next', '.git', '__pycache__'}


def excluded(name):
    return name in EXCLUDED or any(name.startswith(f'{n:02}-') for n in range(1, 6))


def regular(path):
    return stat.S_ISREG(path.lstat().st_mode)


def inventory(root):
    result = {}

    def walk(directory):
        # scandir does not follow directory symlinks; never traverse excluded names.
        with os.scandir(directory) as entries:
            for entry in entries:
                if excluded(entry.name) or entry.is_symlink():
                    continue
                path = Path(entry.path)
                if entry.is_dir(follow_symlinks=False):
                    walk(path)
                elif entry.is_file(follow_symlinks=False):
                    result[path.relative_to(root).as_posix()] = path

    for path in root.iterdir():
        if (path.name.startswith('README') or path.name in {'CLAUDE.md', 'AGENTS.md'}) and regular(path):
            result[path.name] = path
    engine = root / ENGINE
    if engine.is_dir() and not engine.is_symlink():
        for path in engine.iterdir():
            if path.suffix == '.md' and path.name != 'DECIDER_BRIEF.md' and regular(path):
                result[path.relative_to(root).as_posix()] = path
        for name in SCOPES:
            directory = engine / name
            if directory.is_dir() and not directory.is_symlink():
                walk(directory)
    console = root / 'console'
    if console.is_dir() and not console.is_symlink():
        walk(console)
    return result


def read(path):
    # O_NOFOLLOW also protects a file replaced with a symlink after inventory.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as source:
        return source.read()


def main():
    args = sys.argv[2:]
    if len(args) not in (1, 3) or (len(args) == 3 and args[1] != '--diff'):
        print('Usage: engine-diff.sh <other-repo> [--diff <relative-path>]', file=sys.stderr)
        return 2
    a, b = Path(sys.argv[1]), Path(args[0]).absolute()
    if not b.is_dir():
        print('ERROR: B must be an existing repository directory.', file=sys.stderr)
        return 2
    left, right = inventory(a), inventory(b)
    if len(args) == 3:
        name = args[2]
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or name != path.as_posix() or name not in left.keys() | right.keys():
            print('ERROR: --diff requires an allowed engine file, using its relative path.', file=sys.stderr)
            return 2
        x = read(left[name]) if name in left else b''
        y = read(right[name]) if name in right else b''
        if x == y:
            return 0
        if b'\0' in x or b'\0' in y:
            print(f'BINARY_DIFFERENT\t{name}')
            return 0
        try:
            x, y = x.decode('utf-8'), y.decode('utf-8')
        except UnicodeDecodeError:
            print(f'BINARY_DIFFERENT\t{name}')
            return 0
        for line in difflib.unified_diff(x.splitlines(keepends=True), y.splitlines(keepends=True),
                                        fromfile=f'A/{name}', tofile=f'B/{name}'):
            sys.stdout.write(line)
            if not line.endswith('\n'):
                sys.stdout.write('\n\\ No newline at end of file\n')
        return 0
    for name in sorted(left.keys() | right.keys()):
        if name not in right:
            print(f'ONLY_A\t{name}')
        elif name not in left:
            print(f'ONLY_B\t{name}')
        elif read(left[name]) != read(right[name]):
            print(f'DIFFERENT\t{name}')
    return 0


try:
    sys.exit(main())
except OSError:
    # Do not leak absolute paths or exception details from the other repository.
    print('ERROR: cannot read engine files safely; check permissions and retry.', file=sys.stderr)
    sys.exit(2)
PY
