import base64
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch


SYSTEM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SYSTEM / "bin"))
SPEC = importlib.util.spec_from_file_location("jobflow", SYSTEM / "bin" / "jobflow.py")
assert SPEC and SPEC.loader
jobflow = importlib.util.module_from_spec(SPEC)
sys.modules["jobflow"] = jobflow
SPEC.loader.exec_module(jobflow)


class ProgressOpenWorkspaceTests(unittest.TestCase):
    def make_repo(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "repo"
        system = root / "00-工作流系统"
        shutil.copytree(
            SYSTEM,
            system,
            ignore=shutil.ignore_patterns("state", "events", "evidence", "approvals", "__pycache__"),
        )
        repo = jobflow.JobflowRepo(system)
        with patch.dict(os.environ, {"JOBFLOW_PROFILE_DIR": str(Path(temporary.name) / "profile")}, clear=False):
            repo.init_workspace(demo=True)
        (root / "fixture-message.md").write_text("Synthetic message for a test; never sent.", encoding="utf-8")
        (root / "fixture-observation.md").write_text("Synthetic platform observation.", encoding="utf-8")
        (root / "fixture.png").write_bytes(
            base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jBz8AAAAASUVORK5CYII=")
        )
        return repo

    def test_sync_progress_is_idempotent_on_demo_workspace(self):
        repo = self.make_repo()
        repo.sync_progress("test")
        paths = [repo.state_dir / name for name in ["progress.json", "task_queue.json", "current.json"]] + [repo.events_path]
        before = [path.read_bytes() for path in paths]
        repo.sync_progress("test")
        self.assertEqual(before, [path.read_bytes() for path in paths])
        self.assertEqual([], repo.validate().errors)

    def test_prepare_approved_candidate_creates_scoped_final_approval_task(self):
        repo = self.make_repo()
        candidate = next(c for c in repo.load("candidates.json")["candidates"] if c["decision_state"] == "approved")
        app = repo.prepare_candidate(candidate["candidate_id"], "fixture-message.md", "fixture-observation.md", candidate["url"], "test-preparer")
        self.assertEqual("application_prepared", app["status"])
        task = next(t for t in repo.load("task_queue.json")["tasks"] if t["task_id"] == "task-submit-" + app["application_id"])
        self.assertTrue(task["approval_required"])
        self.assertIn("submit_without_final_approval", task["forbidden_actions"])
        self.assertEqual([], repo.validate().errors)

    def test_full_preparation_approval_submission_and_followup_flow(self):
        repo = self.make_repo()
        candidate = next(c for c in repo.load("candidates.json")["candidates"] if c["decision_state"] == "approved")
        app = repo.prepare_candidate(candidate["candidate_id"], "fixture-message.md", "fixture-observation.md", candidate["url"], "test-preparer")
        task_id = "task-submit-" + app["application_id"]
        approval = repo.request_approval(
            task_id,
            ["only the synthetic packet"],
            "test-decider",
            "test:channel",
            120,
            "fixture-message.md",
            app["application_id"],
            "application_submit",
            "BOSS",
        )
        repo.decide_approval(approval["approval_id"], "approved", "user-fixture", "test:channel")
        repo.claim_approval(
            approval["approval_id"],
            app["application_id"],
            task_id,
            "application_submit",
            "BOSS",
            "test-executor",
            ["message=fixture-message.md"],
        )
        repo.set_application_status(
            app["application_id"],
            "submitted_unverified",
            "synthetic click only",
            "test",
            [],
            datetime.now().date().isoformat(),
            None,
            None,
            None,
        )
        manifest = repo.record_evidence(
            app["application_id"],
            task_id,
            "application_submit",
            "verified_success",
            "test-executor",
            "fixture",
            "test-auditor",
            "BOSS",
            approval["approval_id"],
            "synthetic confirmed success",
            ["message=fixture-message.md"],
            ["screenshot_success_page=fixture.png"],
            "test only",
        )
        self.assertEqual([], repo.verify_evidence_manifest(manifest, strict=True))
        repo.set_application_status(app["application_id"], "submitted_verified", "synthetic verified", "test", [], None, None, None, None)
        observed = datetime.now(timezone.utc) - timedelta(minutes=1)
        due = (observed.date() + timedelta(days=3)).isoformat()
        repo.record_followup(app["application_id"], "no_reply", observed.isoformat(), "fixture-observation.md", "Synthetic: no new reply observed", due, "test")
        stored = next(a for a in repo.load("applications.json")["applications"] if a["application_id"] == app["application_id"])
        self.assertEqual(due, stored["follow_up_due"])
        self.assertEqual([], repo.validate().errors)


if __name__ == "__main__":
    unittest.main()
