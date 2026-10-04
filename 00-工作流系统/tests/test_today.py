import copy
from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))
from jobflow_today import build_today, local_day


class TodayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "00-工作流系统/state").mkdir(parents=True)
        self.now = datetime.fromisoformat("2026-09-22T18:00:00+08:00")

    def app(self, aid="app-test", status="submitted_verified", when="2026-09-22T03:00:00Z", operation="application_submit"):
        ref = f"00-工作流系统/evidence/{aid}/ev-test/manifest.json"
        path = self.root / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"application_id": aid, "operation_type": operation,
                                   "occurred_at": when, "result": {"status": "verified_success", "platform_readback": "fixture", "proof_artifacts": [{"kind": "screenshot_success"}]},
                                   "audit": {"outcome": "pass"}}))
        return {"application_id": aid, "company": "Example", "role": "iOS", "channel": "fixture", "status": status,
                "submitted_at": when, "evidence_manifests": [ref]}

    def today(self, apps):
        return build_today(apps, self.root, self.now)

    def test_shanghai_midnight_utc_boundaries(self):
        self.assertEqual("2026-09-21", local_day("2026-09-21T15:59:59Z"))
        self.assertEqual("2026-09-22", local_day("2026-09-21T16:00:00Z"))
        self.assertEqual("2026-09-23", local_day("2026-09-22T16:00:00Z"))
        apps = [self.app("app-before", when="2026-09-21T15:59:59Z"), self.app("app-today", when="2026-09-21T16:00:00Z"), self.app("app-after", when="2026-09-22T16:00:00Z")]
        self.assertEqual(["app-today"], [r["application_id"] for r in self.today(apps)["groups"]["verified"]])

    def test_duplicate_and_company_counts(self):
        app = self.app()
        result = self.today([app, copy.deepcopy(app), self.app("app-other")])
        self.assertEqual(2, result["verified_count"])
        self.assertEqual(1, result["company_count"])

    def test_unverified_preparation_message_do_not_inflate_submission(self):
        prepared = self.app("app-prep", "application_prepared")
        unverified = self.app("app-unverified", "submitted_unverified")
        message = self.app("app-message", "application_prepared", operation="external_send")
        result = self.today([prepared, unverified, message])
        self.assertEqual(0, result["verified_count"])
        self.assertEqual(1, len(result["groups"]["unverified"]))
        self.assertEqual(2, len(result["groups"]["prepared"]))
        self.assertEqual(1, len(result["groups"]["message_only"]))

    def test_closed_requires_real_submission_proof(self):
        closed = self.app("app-closed", "closed")
        not_submitted = self.app("app-never", "closed", operation="external_send")
        no_proof = self.app("app-no-proof", "submitted_verified")
        no_proof.pop("evidence_manifests")
        result = self.today([closed, not_submitted, no_proof])
        self.assertEqual(1, result["verified_count"])
        self.assertEqual("app-closed", result["groups"]["verified"][0]["application_id"])

    def test_legacy_requires_policy_and_explicit_day(self):
        legacy = self.app("app-legacy", "closed", when="2026-09-22")
        legacy.update(legacy_evidence=True, evidence_refs=["historical-screenshot"])
        legacy.pop("evidence_manifests")
        self.assertEqual(0, self.today([legacy])["verified_count"])
        (self.root / "00-工作流系统/state/evidence_policy.json").write_text(json.dumps({"legacy_application_ids": ["app-legacy"]}))
        self.assertEqual(1, self.today([legacy])["verified_count"])
        legacy.pop("submitted_at")
        result = self.today([legacy])
        self.assertEqual(0, result["verified_count"])
        self.assertEqual(1, len(result["groups"]["undated"]))

    def test_ambiguous_dates_conflicts_and_traversal_fail_closed(self):
        self.assertIsNone(local_day("2026-09-22T03:00:00"))
        app = self.app()
        bad = dict(app, status="submitted_unverified")
        self.assertEqual(0, self.today([app, bad])["verified_count"])
        app["evidence_manifests"] = ["../outside/manifest.json"]
        self.assertEqual(0, self.today([app])["verified_count"])


if __name__ == "__main__":
    unittest.main()
