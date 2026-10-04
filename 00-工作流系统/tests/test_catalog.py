import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from html.parser import HTMLParser

SYSTEM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SYSTEM / "bin"))
import jobflow_catalog as catalog


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.append(dict(attrs))


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / "00-工作流系统/state"
        self.state.mkdir(parents=True)
        report = self.root / "05-检索报告/岗位档案/role.html"
        report.parent.mkdir(parents=True)
        report.write_text("<h1>Reviewed role</h1>")
        self.write("candidates.json", {"candidates": [{"candidate_id":"cand-20260901-one","company":"One","role":"iOS","decision_state":"approved","dossier":"05-检索报告/岗位档案/role.html","url":"https://www.liepin.com/job/123.shtml","salary":"20-30K"}]})
        self.write("applications.json", {"applications": []})
        self.write("progress.json", {"drafts": []})
        source = self.root / "05-检索报告/每日岗位检索/2026-09-09.candidates.json"
        source.parent.mkdir()
        source.write_text(json.dumps({"fetched_at":"2026-09-09T09:30:00+08:00","candidates":[
            {"candidate_id":"draft-20260909-one","company":"One","role":"iOS","url":"https://www.liepin.com/job/123.shtml"},
            {"candidate_id":"draft-20260909-two","company":"Two <script>bad</script>","role":"Mobile","url":"https://www.liepin.com/job/456.shtml","why_kept":"Original observation"}
        ]}))

    def write(self, name, data):
        (self.state / name).write_text(json.dumps(data))

    def test_same_platform_job_is_not_duplicated_and_recent_date_is_preserved(self):
        data = catalog.catalog(self.root)
        self.assertEqual(2, len(data["opportunities"]))
        one = next(r for r in data["opportunities"] if r["company"] == "One")
        self.assertEqual("2026-09-09", one["found_at"])
        self.assertEqual("岗位档案", one["report_kind"])
        self.assertEqual("approved", one["stage"])

    def test_draft_report_does_not_claim_completed_diligence(self):
        row = next(r for r in catalog.catalog(self.root)["opportunities"] if r["job_id"].endswith("two"))
        text = catalog.detail(row)
        self.assertIn("尚未形成完整独立背调", text)
        self.assertEqual(7, text.count('class="detail"'))
        self.assertNotIn("<script>bad</script>", text)
        self.assertIn("&lt;script&gt;", text)

    def test_every_catalog_report_opens_a_separate_tab(self):
        text = catalog.cards(self.root, lambda p: "/report?f=" + p)
        links = Links(); links.feed(text)
        self.assertEqual(2, len(links.links))
        for link in links.links:
            self.assertEqual("_blank", link["target"])
            self.assertIn("noopener", link["rel"])

    def test_missing_dossier_does_not_become_a_fake_full_report(self):
        (self.root / "05-检索报告/岗位档案/role.html").unlink()
        data = catalog.catalog(self.root)
        one = next(r for r in data["opportunities"] if r["company"] == "One")
        self.assertIsNone(one["report_url"])
        self.assertIn(self.root / catalog.CATALOG_PATH, catalog.views(self.root))

    def test_evidence_score_is_added_without_changing_user_decision(self):
        goals = json.loads((SYSTEM / 'examples/screening/goals.example.json').read_text())
        assessment = {'schema_version': 1, 'candidate_id': 'cand-20260901-one', 'evidence': {}, 'dimensions': {}, 'hard_rules': {}}
        self.write('screening.json', {'assessments': [assessment]})
        with patch('jobflow_profile.load_goals', return_value=goals):
            row = next(r for r in catalog.catalog(self.root)['opportunities'] if r['job_id'] == assessment['candidate_id'])
        self.assertEqual('approved', row['stage'])
        self.assertEqual('待核实', row['screening']['decision'])
        self.assertEqual(0, row['screening']['score_lower'])
        self.assertNotIn('真外企', row['tags'])

    def test_missing_private_profile_does_not_invent_scores(self):
        from jobflow_profile import ProfileError
        self.write('screening.json', {'assessments': [{'candidate_id': 'cand-20260901-one'}]})
        with patch('jobflow_profile.load_goals', side_effect=ProfileError('missing')):
            row = catalog.catalog(self.root)['opportunities'][0]
        self.assertNotIn('screening', row)

    def test_old_dashboard_report_links_preserve_the_dashboard(self):
        spec = importlib.util.spec_from_file_location("catalog_dashboard_test", SYSTEM / "dashboard/server.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        body = module.page("test", "/reports", '<a href="/report?f=test.html">report</a><a href="/application/app-example">case</a>')
        links = Links(); links.feed(body.decode())
        targets = [a for a in links.links if a["href"].startswith(("/report?", "/application/"))]
        self.assertEqual(2, len(targets))
        self.assertTrue(all(a.get("target") == "_blank" for a in targets))


if __name__ == "__main__":
    unittest.main()
