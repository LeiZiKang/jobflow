import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'bin' / 'inbound_digest.py'
spec = importlib.util.spec_from_file_location('inbound_digest', MODULE)
digest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(digest)


def fixture():
    return {
        'date': '2026-09-22',
        'window': {'start': '2026-09-21T09:00:00+08:00', 'end': '2026-09-22T09:00:00+08:00'},
        'required_sources': ['liepin'],
        'sources': [{'source_id': 'liepin', 'status': 'ok',
                     'observed_at': '2026-09-22T09:00:00+08:00', 'evidence_ref': 'evidence/readback.txt'}],
        'items': [{'id': 'message-1', 'source_id': 'liepin', 'sender_role': 'recruiter',
                   'company': 'Example', 'contact': '某招聘人', 'role': 'iOS',
                   'received_at': '2026-09-22T08:00:00+08:00', 'summary': '邀请了解岗位',
                   'kind': 'new_contact', 'source_ref': 'https://example.com/message/1'}],
    }


class InboundDigestTests(unittest.TestCase):
    def test_complete(self):
        data = digest.normalize(fixture())
        self.assertTrue(data['complete'])
        self.assertEqual(data['counts']['new_contact'], 1)

    def test_missing_channel_is_incomplete(self):
        raw = fixture()
        raw['required_sources'].append('email')
        data = digest.normalize(raw)
        self.assertFalse(data['complete'])
        self.assertEqual(data['sources'][-1]['status'], 'not_checked')
        self.assertIn('至少 1', digest.render_daily(data))
        self.assertIn('—（未查全）', digest.render_daily(data))

    def test_coverage_cannot_be_omitted(self):
        raw = fixture()
        del raw['required_sources']
        with self.assertRaises(ValueError):
            digest.normalize(raw)

    def test_self_unknown_and_promotion_are_not_new_contacts(self):
        raw = fixture()
        for n, (sender, kind) in enumerate([('self', 'new_contact'), ('unknown', 'new_contact'),
                                          ('system', 'promotion'), ('employer', 'application_reply'),
                                          ('system', 'automatic_confirmation')]):
            item = dict(raw['items'][0], id=str(n), sender_role=sender, kind=kind)
            raw['items'].append(item)
        data = digest.normalize(raw)
        self.assertEqual(data['counts'], {'new_contact': 1, 'excluded': 2, 'unknown': 1,
                                          'application_reply': 1, 'automatic_confirmation': 1})
        self.assertFalse(data['complete'])

    def test_duplicate_ids_and_fingerprints(self):
        for with_id in (True, False):
            raw = fixture()
            if not with_id:
                del raw['items'][0]['id']
            raw['items'].append(copy.deepcopy(raw['items'][0]))
            data = digest.normalize(raw)
            self.assertEqual(data['duplicates_removed'], 1)
            self.assertEqual(data['counts']['new_contact'], 1)

    def test_conflicting_same_id_is_not_silently_discarded(self):
        raw = fixture()
        raw['items'].append(dict(raw['items'][0], summary='相同 ID，内容矛盾'))
        with self.assertRaises(ValueError):
            digest.normalize(raw)

    def test_incomplete_source_cannot_claim_zero(self):
        for status in set(digest.STATUSES) - digest.COMPLETE:
            raw = fixture()
            raw['sources'][0].update(status=status, reason='受阻', counts={'new_contact': 0})
            with self.assertRaises(ValueError):
                digest.normalize(raw)
            del raw['sources'][0]['counts']
            rendered = digest.render_daily(digest.normalize(raw))
            self.assertIn('至少 1', rendered)
            self.assertIn('—（未查全）', rendered)

    def test_empty_rejects_inbound_and_counts_must_match(self):
        raw = fixture()
        raw['sources'][0]['status'] = 'empty'
        with self.assertRaises(ValueError):
            digest.normalize(raw)
        raw['sources'][0].update(status='ok', counts={'new_contact': 9})
        with self.assertRaises(ValueError):
            digest.normalize(raw)

    def test_bad_dates_and_time_window(self):
        for day in ('../2026-09-22', '2026-02-30', '2026-9-22', '2026-09-22/../../x'):
            raw = fixture()
            raw['date'] = day
            with self.assertRaises(ValueError):
                digest.normalize(raw)
        for received in ('2026-09-22T08:00:00', '2026-09-20T08:00:00+08:00'):
            raw = fixture()
            raw['items'][0]['received_at'] = received
            with self.assertRaises(ValueError):
                digest.normalize(raw)

    def test_xss_escaped_and_no_active_content(self):
        raw = fixture()
        raw['items'][0]['summary'] = '<script>alert(1)</script><img src=x onerror=alert(2)>'
        raw['items'][0]['company'] = '\" onclick=\"alert(3)'
        rendered = digest.render_daily(digest.normalize(raw))
        self.assertNotIn('<script>', rendered)
        self.assertNotIn('<img', rendered)
        self.assertIn('&lt;script&gt;', rendered)
        self.assertIn('Content-Security-Policy', rendered)
        self.assertIn(':root{color-scheme:dark', rendered)
        self.assertIn('@media print', rendered)

    def test_unsafe_links_rejected(self):
        for reference in ('javascript:alert(1)', 'data:text/html,<script>x</script>', '//evil.com',
                          '../private.txt', '%2e%2e/private.txt', 'https://user:password@example.com',
                          'http:', 'https://x\n.com', '/%2fexample.com', 'a\\b', '%6aavascript:alert(1)'):
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                digest.safe_ref(reference)
        self.assertEqual(digest.safe_ref('evidence/某公司.txt'), 'evidence/%E6%9F%90%E5%85%AC%E5%8F%B8.txt')

    def test_history_preserved_private_files_no_legacy_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / '汇总.html'
            legacy.write_text('existing', encoding='utf-8')
            first = fixture()
            digest.generate(first, tmp)
            second = fixture()
            second['date'] = '2026-09-23'
            digest.generate(second, tmp)
            index = (Path(tmp) / 'index.html').read_text(encoding='utf-8')
            self.assertIn('2026-09-22.html', index)
            self.assertIn('2026-09-23.html', index)
            self.assertEqual(legacy.read_text(), 'existing')
            self.assertEqual((Path(tmp) / '2026-09-22.html').stat().st_mode & 0o777, 0o600)
            (Path(tmp) / '2026-09-23.html').write_text('human file')
            with self.assertRaises(ValueError):
                digest.generate(second, tmp)

    def test_symlink_refused_and_validation_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'target.txt'
            target.write_text('private')
            (Path(tmp) / 'index.html').symlink_to(target)
            with self.assertRaises(ValueError):
                digest.generate(fixture(), tmp)
            self.assertFalse((Path(tmp) / '2026-09-22.html').exists())
            source = Path(tmp) / 'input.json'
            source.write_text(json.dumps(fixture()))
            result = subprocess.run([sys.executable, str(MODULE), '--input', str(source), '--validate'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)['valid'])


if __name__ == '__main__':
    unittest.main()
