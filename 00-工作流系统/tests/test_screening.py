"""Screening invariants using fictional inputs only."""

import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / "00-工作流系统/bin"
EXAMPLES = ROOT / "00-工作流系统/examples/screening"
sys.path.insert(0, str(BIN))

from jobflow_profile import ProfileError, load_goals, profile_directory
from jobflow_screening import ScreeningError, goal_config_sha256, profile_summary, score_assessment


class ScreeningTests(unittest.TestCase):
    def setUp(self):
        self.goals = json.loads((EXAMPLES / "goals.example.json").read_text())
        self.assessment = json.loads((EXAMPLES / "assessment.example.json").read_text())

    def score(self):
        return score_assessment(self.assessment, self.goals, now=datetime(2026, 9, 22, 4, tzinfo=timezone.utc))

    def test_canonical_hash_key_order_independent_and_policy_present(self):
        reordered = dict(reversed(list(self.goals.items())))
        self.assertEqual(goal_config_sha256(self.goals), goal_config_sha256(reordered))
        result = self.score()
        self.assertEqual(result["goal_config_sha256"], goal_config_sha256(self.goals))
        self.assertEqual(result["policy_version"], "screening-v1")
        self.goals["dimensions"]["salary"]["rubric"] += " changed"
        self.assertNotEqual(result["goal_config_sha256"], goal_config_sha256(self.goals))

    def test_future_timestamp_tolerance_and_timezone(self):
        self.assessment["evidence"]["jd"]["observed_at"] = "2026-09-22T12:05:00+08:00"
        self.score()
        self.assessment["evidence"]["jd"]["observed_at"] = "2026-09-22T04:05:01+00:00"
        with self.assertRaisesRegex(ScreeningError, "future"):
            self.score()
        with self.assertRaisesRegex(ScreeningError, "timezone-aware"):
            score_assessment(self.assessment, self.goals, now=datetime(2026, 9, 22))

    def test_unknown_ownership_tag(self):
        self.assessment["ownership"] = {"status": "unknown"}
        self.assertIn("所有制待核实", self.score()["tags"])

    def test_profile_summary_omits_private_prose(self):
        self.goals["hard_rules"]["location"] = "PRIVATE_RULE"
        self.goals["dimensions"]["salary"]["rubric"] = "PRIVATE_RUBRIC"
        self.goals["dimensions"]["salary"]["label"] = "PRIVATE_LABEL"
        summary = profile_summary(self.goals)
        self.assertNotIn("PRIVATE_", json.dumps(summary))
        self.assertEqual(summary["dimension_weights"]["salary"], 15)
        self.assertEqual(summary["total_weight"], 100)

    def test_supported_lower_upper_and_coverage(self):
        result = self.score()
        self.assertEqual((result["score_lower"], result["score_upper"], result["evidence_coverage_percent"]), (90, 100, 90))
        self.assertEqual(result["decision"], "推荐")
        self.assertEqual(result["tags"], ["真外企", "外包·交付"])

    def test_missing_evidence_never_renormalizes(self):
        self.assessment["dimensions"] = {"salary": {"value": 1, "reason": "虚构薪资已查", "evidence_refs": ["jd"]}}
        result = self.score()
        self.assertEqual((result["score_lower"], result["score_upper"], result["evidence_coverage_percent"]), (15, 100, 15))
        self.assertEqual(result["decision"], "待核实")

    def test_unsupported_claims_are_unknown(self):
        self.assessment["dimensions"]["technical_fit"]["evidence_refs"] = []
        self.assessment["hard_rules"]["hours"]["evidence_refs"] = []
        result = self.score()
        self.assertEqual(result["score_lower"], 60)
        self.assertEqual(result["gate"], "unknown")
        self.assertIsNone(result["dimensions"]["technical_fit"]["value"])
        self.assertEqual(result["decision"], "待核实")

    def test_high_salary_and_foreign_tag_cannot_override_fail(self):
        self.assessment["hard_rules"]["hours"]["status"] = "fail"
        result = self.score()
        self.assertEqual(result["score_lower"], 90)
        self.assertEqual(result["gate"], "fail")
        self.assertEqual(result["decision"], "不推荐")
        self.assertEqual(result["sort_key"][0], 2)

    def test_missing_hard_rule_blocks_recommendation(self):
        del self.assessment["hard_rules"]["hours"]
        self.assertEqual(self.score()["gate"], "unknown")

    def test_total_absence_is_zero_to_hundred(self):
        self.assessment["dimensions"] = {}
        self.assessment["hard_rules"] = {}
        result = self.score()
        self.assertEqual((result["score_lower"], result["score_upper"], result["evidence_coverage_percent"]), (0, 100, 0))
        self.assertEqual(result["decision"], "待核实")

    def test_known_bad_zero_not_missing(self):
        for item in self.assessment["dimensions"].values():
            item.update(value=0, evidence_refs=["jd"])
        result = self.score()
        self.assertEqual((result["score_lower"], result["score_upper"], result["evidence_coverage_percent"]), (0, 0, 100))
        self.assertEqual(result["decision"], "不推荐")

    def test_recommend_threshold_inclusive(self):
        for item in self.assessment["dimensions"].values():
            item.update(value=0.75, evidence_refs=["jd"])
        self.assertEqual(self.score()["decision"], "推荐")
        self.assessment["dimensions"]["salary"]["value"] = 0.74
        self.assertEqual(self.score()["decision"], "待核实")

    def test_reject_uses_upper_not_lower(self):
        self.assessment["dimensions"] = {"technical_fit": {"value": 0, "reason": "已确认不匹配", "evidence_refs": ["jd"]}}
        self.assertEqual(self.score()["decision"], "待核实")

    def test_reject_threshold_exclusive(self):
        for item in self.assessment["dimensions"].values():
            item.update(value=0.5, evidence_refs=["jd"])
        self.assertEqual(self.score()["decision"], "待核实")
        self.assessment["dimensions"]["salary"]["value"] = 0.49
        self.assertEqual(self.score()["decision"], "不推荐")

    def test_invalid_values_and_weights_rejected(self):
        for value in [-0.1, 1.1, True, float("nan"), float("inf"), "1"]:
            with self.subTest(value=value):
                self.assessment["dimensions"]["technical_fit"]["value"] = value
                with self.assertRaises(ScreeningError): self.score()
        self.setUp()
        self.goals["dimensions"]["salary"]["weight"] = 16
        with self.assertRaises(ScreeningError): self.score()

    def test_unknown_dimension_and_dangling_ref_rejected(self):
        self.assessment["dimensions"]["typo"] = copy.deepcopy(self.assessment["dimensions"]["salary"])
        with self.assertRaises(ScreeningError): self.score()
        del self.assessment["dimensions"]["typo"]
        self.assessment["dimensions"]["salary"]["evidence_refs"] = ["nonexistent"]
        with self.assertRaises(ScreeningError): self.score()

    def test_source_timestamp_requires_timezone(self):
        self.assessment["evidence"]["jd"]["observed_at"] = "2026-09-22T12:00:00"
        with self.assertRaises(ScreeningError): self.score()

    def test_missing_control_edge_or_source_removes_foreign_tag(self):
        for change in ("no_chain", "no_refs", "broken_chain", "cycle", "wrong_parent"):
            with self.subTest(change=change):
                self.setUp()
                owner = self.assessment["ownership"]
                if change == "no_chain": owner["control_chain"] = []
                elif change == "no_refs": owner["control_chain"][0]["evidence_refs"] = []
                elif change == "broken_chain": owner["control_chain"][0]["entity"] = "different entity"
                elif change == "cycle": owner["control_chain"][0]["controller"] = owner["legal_entity"]
                else: owner["ultimate_parent"] = "different parent"
                self.assertNotIn("真外企", self.score()["tags"])

    def test_foreign_first_within_decision_class(self):
        foreign = self.score()
        self.assessment["ownership"]["status"] = "unknown"
        self.assessment["dimensions"]["culture_leave"].update(value=1, evidence_refs=["team"])
        other = self.score()
        self.assertLess(foreign["sort_key"], other["sort_key"])
        self.goals["foreign_first"] = False
        other = self.score()
        self.assessment["ownership"]["status"] = "verified_foreign"
        self.assessment["dimensions"]["culture_leave"]["value"] = None
        self.assertLess(other["sort_key"], self.score()["sort_key"])

    def test_inputs_unchanged_and_output_has_no_identity(self):
        previous = copy.deepcopy((self.assessment, self.goals))
        result = self.score()
        self.assertEqual(previous, (self.assessment, self.goals))
        self.assertNotIn("identity", result)
        self.assertNotIn("goals", result)

    def test_cli_fixture(self):
        run = subprocess.run([sys.executable, str(BIN / "jobflow_screening.py"), str(EXAMPLES / "assessment.example.json"), "--goals", str(EXAMPLES / "goals.example.json")], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["score_lower"], 90)

    def test_cli_requires_assessment_for_scoring(self):
        run = subprocess.run([sys.executable, str(BIN / "jobflow_screening.py"), "--goals", str(EXAMPLES / "goals.example.json")], capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertEqual(run.stdout, "")

    def test_cli_validate_profile_never_reads_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp)
            (profile / "goals.json").write_text(json.dumps(self.goals))
            # Broken symlink would cause an error if identity was opened.
            (profile / "identity.json").symlink_to(profile / "must-not-read.json")
            env = {**os.environ, "JOBFLOW_PROFILE_DIR": str(profile)}
            run = subprocess.run([sys.executable, str(BIN / "jobflow_screening.py"), "--validate-profile"], env=env, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            summary = json.loads(run.stdout)
            self.assertTrue(summary["valid"])
            self.assertEqual(summary["goal_config_sha256"], goal_config_sha256(self.goals))
            self.assertNotIn("identity", summary)


class ProfileTests(unittest.TestCase):
    def test_default_path(self):
        with patch.dict(os.environ, {}, clear=True), patch("pathlib.Path.home", return_value=Path("/tmp/fictional-home")):
            self.assertEqual(profile_directory(), Path("/tmp/fictional-home/.config/jobflow/profile").resolve())

    def test_refuses_repository_and_symlink_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            alias = Path(tmp) / "alias"
            alias.symlink_to(root, target_is_directory=True)
            for path in (root, root / "private", alias / "private"):
                with patch.dict(os.environ, {"JOBFLOW_PROFILE_DIR": str(path)}):
                    with self.assertRaises(ProfileError): profile_directory(repo_root=root)

    def test_goals_read_does_not_open_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            profile = Path(tmp) / "profile"
            root.mkdir(); profile.mkdir()
            (profile / "goals.json").write_text('{"schema_version":1}')
            (profile / "identity.json").write_text('invalid JSON, must not open')
            with patch.dict(os.environ, {"JOBFLOW_PROFILE_DIR": str(profile)}):
                self.assertEqual(load_goals(repo_root=root), {"schema_version": 1})

    def test_goals_symlink_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            profile = Path(tmp) / "profile"
            root.mkdir(); profile.mkdir()
            target = Path(tmp) / "outside.json"
            target.write_text('{}')
            (profile / "goals.json").symlink_to(target)
            with patch.dict(os.environ, {"JOBFLOW_PROFILE_DIR": str(profile)}):
                with self.assertRaises(ProfileError): load_goals(repo_root=root)


if __name__ == "__main__":
    unittest.main()
