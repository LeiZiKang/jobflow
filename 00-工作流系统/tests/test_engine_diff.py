"""Exercise the shipped shell entrypoint against two isolated repositories."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'engine-diff.sh'
ENGINE = '00-工作流系统'


class EngineDiffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.a = Path(self.temp.name) / 'A repo'
        self.b = Path(self.temp.name) / 'B repo'
        for root in (self.a, self.b):
            dest = root / ENGINE / 'scripts' / 'engine-diff.sh'
            dest.parent.mkdir(parents=True)
            shutil.copy2(SCRIPT, dest)
        self.script = self.a / ENGINE / 'scripts' / 'engine-diff.sh'

    def put(self, root, name, content):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def run_diff(self, *args):
        return subprocess.run(['bash', str(self.script), str(self.b), *args],
                              capture_output=True, text=True)

    def test_three_kinds_and_relative_paths(self):
        self.put(self.a, f'{ENGINE}/bin/a.py', 'a')
        self.put(self.b, 'console/b.ts', 'b')
        for root, content in ((self.a, 'old'), (self.b, 'new')):
            self.put(root, 'README.md', content)
            self.put(root, 'AGENTS.md', 'same')
        result = self.run_diff()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [f'ONLY_A\t{ENGINE}/bin/a.py',
                         'DIFFERENT\tREADME.md', 'ONLY_B\tconsole/b.ts'])
        self.assertNotIn(str(self.temp.name), result.stdout + result.stderr)

    def test_private_and_generated_directories_not_read_or_listed(self):
        names = ['state', 'events', 'evidence', 'approvals', 'assets', '.agent-memory',
                 '01-private', '02-private', '03-private', '04-private', '05-private']
        paths = [f'{prefix}{name}/private.txt' for prefix in ('', f'{ENGINE}/', 'console/') for name in names]
        paths += [f'{ENGINE}/DECIDER_BRIEF.md', 'console/node_modules/a', 'console/.next/a']
        for name in paths:
            for root in (self.a, self.b):
                file = self.put(root, name, 'private-A' if root == self.a else 'private-B')
                file.chmod(0)  # An accidental content read should fail on non-root runners.
                self.addCleanup(file.chmod, 0o600)
        result = self.run_diff()
        self.assertEqual((result.returncode, result.stdout), (0, ''), result.stderr)
        for name in paths:
            self.assertEqual(self.run_diff('--diff', name).returncode, 2)

    def test_symlinks_cannot_expose_data(self):
        private = self.put(self.a, 'state/private.txt', 'secret')
        (self.a / ENGINE / 'scripts' / 'linked.py').symlink_to(private)
        (self.b / ENGINE / 'bin').symlink_to(private.parent, target_is_directory=True)
        self.assertEqual(self.run_diff().stdout, '')
        self.assertEqual(self.run_diff('--diff', f'{ENGINE}/scripts/linked.py').returncode, 2)

    def test_unified_diff_and_missing_newline(self):
        self.put(self.a, 'README.md', 'old')
        self.put(self.b, 'README.md', 'new\n')
        result = self.run_diff('--diff', 'README.md')
        self.assertEqual(result.returncode, 0)
        self.assertIn('--- A/README.md\n+++ B/README.md', result.stdout)
        self.assertIn('-old\n\\ No newline at end of file\n+new\n', result.stdout)
        self.assertNotIn(str(self.a), result.stdout)

    def test_one_sided_diff_and_binary(self):
        self.put(self.b, 'README.md', 'new\n')
        self.assertIn('+new', self.run_diff('--diff', 'README.md').stdout)
        self.put(self.a, 'README.md', '\0old')
        self.assertEqual(self.run_diff('--diff', 'README.md').stdout, 'BINARY_DIFFERENT\tREADME.md\n')

    def test_reject_traversal_absolute_and_unknown(self):
        for name in ('../README.md', str(self.a / 'README.md'), 'state/private.txt', 'missing.md'):
            result = self.run_diff('--diff', name)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(str(self.temp.name), result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
