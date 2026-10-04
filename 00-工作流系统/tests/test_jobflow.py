import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "jobflow.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("jobflow", SCRIPT)
assert SPEC and SPEC.loader
jobflow = importlib.util.module_from_spec(SPEC)
sys.modules["jobflow"] = jobflow
SPEC.loader.exec_module(jobflow)
import check_job_reports


class JobflowOpenInitTests(unittest.TestCase):
    def make_workspace(self, *, demo=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "repo"
        system = root / "00-工作流系统"
        shutil.copytree(
            Path(__file__).resolve().parents[1],
            system,
            ignore=shutil.ignore_patterns("state", "events", "evidence", "approvals", ".init-backup-*", "__pycache__"),
        )
        profile = Path(temporary.name) / "profile"
        repo = jobflow.JobflowRepo(system)
        with patch.dict(os.environ, {"JOBFLOW_PROFILE_DIR": str(profile)}, clear=False):
            repo.init_workspace(demo=demo)
        return repo, profile

    def test_empty_init_creates_valid_workspace_and_profile_template(self):
        repo, profile = self.make_workspace()
        self.assertTrue((repo.state_dir / "current.json").is_file())
        self.assertTrue((repo.events_path).is_file())
        self.assertTrue((repo.repo_root / "01-现在在做/状态总览.md").is_file())
        report_template = repo.repo_root / "05-检索报告/岗位档案/_模板-岗位档案.html"
        self.assertTrue(report_template.is_file())
        template_text = report_template.read_text(encoding="utf-8")
        self.assertIn("📍 工作地址", template_text)
        self.assertIn('class="jdlink"', template_text)
        self.assertEqual([], check_job_reports.problems(report_template))
        self.assertTrue((profile / "goals.json").is_file())
        result = repo.validate()
        self.assertEqual([], result.errors, "\n".join(result.errors))
        self.assertTrue(any("no application records" in warning for warning in result.warnings))
        self.assertEqual([], repo.memory_store.validate())
        self.assertTrue(all(ok for _, ok, _ in repo.cold_start_check()))
        self.assertEqual([], [detail for _, ok, detail in repo.golden_check() if not ok])
        self.assertEqual([], repo.evidence_manifests())

    def test_init_refuses_existing_state_unless_forced_and_never_overwrites_profile(self):
        repo, profile = self.make_workspace()
        goals = profile / "goals.json"
        goals.write_text('{"schema_version": 1, "custom": true}\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "state already exists"):
            repo.init_workspace()
        with patch.dict(os.environ, {"JOBFLOW_PROFILE_DIR": str(profile)}, clear=False):
            repo.init_workspace(force=True)
        self.assertEqual('{"schema_version": 1, "custom": true}\n', goals.read_text(encoding="utf-8"))

    def test_force_from_demo_removes_only_demo_manifest_files(self):
        repo, profile = self.make_workspace(demo=True)
        manifest = repo.state_dir / "demo-manifest.json"
        demo_evidence = repo.repo_root / "00-工作流系统/evidence/app-demo-pixel-harbor-ios/ev-demo-submit/manifest.json"
        self.assertTrue(manifest.is_file())
        self.assertTrue(demo_evidence.is_file())
        keep = repo.repo_root / "05-检索报告/岗位报告/user-note.html"
        keep.parent.mkdir(parents=True, exist_ok=True)
        keep.write_text("user-owned file\n", encoding="utf-8")
        with patch.dict(os.environ, {"JOBFLOW_PROFILE_DIR": str(profile)}, clear=False):
            repo.init_workspace(force=True)
        self.assertFalse(manifest.exists())
        self.assertFalse(demo_evidence.exists())
        self.assertEqual("user-owned file\n", keep.read_text(encoding="utf-8"))
        self.assertEqual([], repo.evidence_manifests())
        result = repo.validate()
        self.assertEqual([], result.errors, "\n".join(result.errors))

    def test_force_from_empty_to_demo_records_new_demo_manifest(self):
        repo, profile = self.make_workspace()
        with patch.dict(os.environ, {"JOBFLOW_PROFILE_DIR": str(profile)}, clear=False):
            repo.init_workspace(demo=True, force=True)
        manifest = repo.state_dir / "demo-manifest.json"
        self.assertTrue(manifest.is_file())
        manifest_doc = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertIn("00-工作流系统/state/demo-manifest.json", manifest_doc["files"])
        self.assertIn("05-检索报告/岗位报告/cand-demo-acme-robotics-ios.html", manifest_doc["files"])
        result = repo.validate()
        self.assertEqual([], result.errors, "\n".join(result.errors))
        self.assertTrue(repo.evidence_manifests())
        for evidence in repo.evidence_manifests():
            self.assertEqual([], repo.verify_evidence_manifest(evidence, strict=True))

    def test_force_from_real_workspace_backs_up_system_state_without_deleting_user_data(self):
        repo, profile = self.make_workspace()
        evidence = repo.system_dir / "evidence/user-real-note/source.txt"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("real user evidence\n", encoding="utf-8")
        user_report = repo.repo_root / "05-检索报告/岗位报告/user-report.html"
        user_report.parent.mkdir(parents=True, exist_ok=True)
        user_report.write_text("real user report\n", encoding="utf-8")
        with patch.dict(os.environ, {"JOBFLOW_PROFILE_DIR": str(profile)}, clear=False):
            repo.init_workspace(force=True)
        backups = sorted(repo.system_dir.glob(".init-backup-*"))
        self.assertEqual(1, len(backups))
        backup = backups[0]
        self.assertEqual("real user evidence\n", (backup / "evidence/user-real-note/source.txt").read_text(encoding="utf-8"))
        self.assertTrue((backup / "state/current.json").is_file())
        self.assertTrue((backup / "DECIDER_BRIEF.md").is_file())
        self.assertFalse(evidence.exists())
        self.assertEqual("real user report\n", user_report.read_text(encoding="utf-8"))
        result = repo.validate()
        self.assertEqual([], result.errors, "\n".join(result.errors))

    def test_render_views_writes_user_data_not_root_readme(self):
        repo, _ = self.make_workspace()
        root_readme = repo.repo_root / "README.md"
        root_readme.write_text("human open source readme\n", encoding="utf-8")
        repo.write_views()
        self.assertEqual("human open source readme\n", root_readme.read_text(encoding="utf-8"))
        rendered = repo.render_views()
        self.assertIn(repo.repo_root / "01-现在在做" / "状态总览.md", rendered)
        self.assertNotIn(root_readme, rendered)

    def test_demo_init_has_fictional_content_status_next_and_evidence(self):
        repo, _ = self.make_workspace(demo=True)
        result = repo.validate()
        self.assertEqual([], result.errors, "\n".join(result.errors))
        apps = repo.load("applications.json")["applications"]
        self.assertEqual(3, len(apps))
        self.assertTrue(any(app["company"] == "Acme Robotics" for app in repo.load("candidates.json")["candidates"]))
        self.assertTrue(repo.evidence_manifests())
        for manifest in repo.evidence_manifests():
            self.assertEqual([], repo.verify_evidence_manifest(manifest, strict=True))
        self.assertIn("Acme Robotics", repo.render_brief())
        self.assertTrue(any(task["status"] == "waiting_user" for task in repo.load("task_queue.json")["tasks"]))
        self.assertIn("公司明确反馈", repo.render_application_case(apps[-1], repo.load("task_queue.json")["tasks"]))

    def test_case_view_path_is_id_bound_and_safe(self):
        repo, _ = self.make_workspace(demo=True)
        path = repo.state_dir / "applications.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        app = next(item for item in doc["applications"] if item.get("case"))
        app["case"]["view_path"] = "../../outside.html"
        path.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Case view_path must be"):
            repo.write_views()

    def test_secret_scanner_and_generated_block_contracts(self):
        errors = []
        jobflow._scan_secrets({"password": "not-allowed"}, "fixture", errors)
        self.assertTrue(errors)
        errors = []
        jobflow._scan_secrets({"password_ref": "secret://service/account"}, "fixture", errors)
        self.assertEqual([], errors)
        with self.assertRaisesRegex(ValueError, "markers missing"):
            jobflow._replace_generated_block("A START B START C END", "START", "END", "X")

    def test_claim_decider_requires_session_ref(self):
        repo, _ = self.make_workspace()
        with self.assertRaisesRegex(ValueError, "session_ref"):
            repo.claim_decider("agent", "backend", None, 120)

    def test_job_envelope_contains_required_guards(self):
        repo, _ = self.make_workspace()
        envelope = repo.job_envelope("job-daily-position-search")
        self.assertIn("job-daily-position-search", envelope)
        self.assertIn("send_message", envelope)
        self.assertIn("enter_verification_code", envelope)
        self.assertIn("output_path", envelope)


if __name__ == "__main__":
    unittest.main()
