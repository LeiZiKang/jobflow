from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

SYSTEM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SYSTEM / "bin"))
import jobflow
import ontrace_check


class OntraceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        shutil.copytree(
            SYSTEM,
            self.root / "00-工作流系统",
            ignore=shutil.ignore_patterns("state", "events", "evidence", "approvals", "__pycache__", "runtime", "node_modules"),
        )
        self.repo = jobflow.JobflowRepo(self.root / "00-工作流系统")
        with patch.dict(os.environ, {"JOBFLOW_PROFILE_DIR": str(Path(self.temp.name) / "profile")}, clear=False):
            self.repo.init_workspace(demo=True)
        self.repo.session_ref = None
        lease = self.repo.load("active_decider.json")
        lease.update(status="unclaimed", agent=None, session_ref=None, lease_expires_at=None)
        jobflow._atomic_write_json(self.repo.state_dir / "active_decider.json", lease)
        jobs = self.repo.load("recurring_jobs.json")
        job = next(j for j in jobs["jobs"] if j["job_id"] == ontrace_check.JOB_ID)
        job.update(not_before="2000-01-01", last_run=None, enabled=True)
        jobflow._atomic_write_json(self.repo.state_dir / "recurring_jobs.json", jobs)
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        local_hour, local_minute = (int(part) for part in job["schedule"]["local_time"].split(":"))
        self.slot = now.replace(hour=local_hour, minute=local_minute, second=0, microsecond=0)
        if self.slot > now - timedelta(minutes=2):
            self.slot -= timedelta(days=1)
        self.observed = now - timedelta(minutes=1)
        (self.root / "observation.txt").write_text("Synthetic test observation, no platform action.")

    def result(self, blocked=False):
        observations = [dict(application_id=a["application_id"], outcome="blocked" if blocked else "no_reply",
                             observed_at=self.observed.isoformat(), source_ref="observation.txt", note="Synthetic observation")
                        for a in ontrace_check.targets(self.repo)]
        return dict(scheduled_for=self.slot.isoformat(), observations=observations)

    def save(self, result):
        (self.root / "result.json").write_text(json.dumps(result))

    def test_closed_applications_are_excluded(self):
        self.assertTrue(ontrace_check.targets(self.repo))
        self.assertFalse(any(a["status"] in {"closed", "rejected", "withdrawn"} for a in ontrace_check.targets(self.repo)))

    def test_missing_application_is_not_a_completed_round(self):
        result = self.result(); result["observations"].pop()
        self.save(result)
        with self.assertRaisesRegex(ValueError, "exactly one observation"):
            ontrace_check.record(self.repo, "result.json", "test")
        self.assertIsNone(self.repo.find_job(ontrace_check.JOB_ID)["last_run"])

    def test_each_application_is_updated_and_duplicate_slot_is_rejected(self):
        result = self.result(); self.save(result)
        job = ontrace_check.record(self.repo, "result.json", "test")
        self.assertEqual("completed", job["last_run"]["status"])
        self.assertEqual(len(result["observations"]), job["last_run"]["metrics"]["checked_applications"])
        for app in ontrace_check.targets(self.repo):
            self.assertEqual(self.observed.isoformat(), app["last_platform_check_at"])
        with self.assertRaisesRegex(ValueError, "already recorded"):
            ontrace_check.record(self.repo, "result.json", "test")

    def test_blocked_round_preserves_existing_platform_records(self):
        before = {a["application_id"]: a.get("platform_readback") for a in ontrace_check.targets(self.repo)}
        self.save(self.result(blocked=True))
        job = ontrace_check.record(self.repo, "result.json", "test")
        self.assertEqual("blocked", job["last_run"]["status"])
        self.assertEqual(before, {a["application_id"]: a.get("platform_readback") for a in ontrace_check.targets(self.repo)})

    def test_round_recorded_after_midnight_schedules_next_check_after_observation(self):
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        job = next(j for j in self.repo.load("recurring_jobs.json")["jobs"] if j["job_id"] == ontrace_check.JOB_ID)
        local_hour, local_minute = (int(part) for part in job["schedule"]["local_time"].split(":"))
        self.slot = now.replace(hour=local_hour, minute=local_minute, second=0, microsecond=0) - timedelta(days=1)
        self.save(self.result())
        ontrace_check.record(self.repo, "result.json", "test")
        for app in ontrace_check.targets(self.repo):
            self.assertGreater(app["follow_up_due"], self.observed.date().isoformat())


if __name__ == "__main__":
    unittest.main()
