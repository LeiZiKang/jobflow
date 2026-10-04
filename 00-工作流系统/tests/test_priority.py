from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))
import jobflow_priority as priority


class PriorityTests(unittest.TestCase):
    def snapshot(self, days=0, **overrides):
        base = dict(observed_at="2026-09-13T08:00:00+00:00", waiting_on="employer",
                    waiting_since=(date(2026, 9, 13) - timedelta(days=days)).isoformat(),
                    last_inbound_date=None, response_window_verified=True, source_refs=["source.txt"])
        return {**base, **overrides}

    def test_waiting_thresholds(self):
        for days, level in [(0,2), (6,2), (7,3), (13,3), (14,4), (21,4)]:
            self.assertEqual(level, priority.assess(self.snapshot(days))["level"])

    def test_user_action_takes_precedence_over_old_messages(self):
        result = priority.assess(self.snapshot(30, waiting_on="user", action_needed="确认面试时间"))
        self.assertEqual(1, result["level"])

    def test_unverified_window_does_not_demote(self):
        self.assertIsNone(priority.assess(self.snapshot(30, response_window_verified=False))["level"])

    def test_explicit_future_reply_promise_is_respected(self):
        self.assertEqual(2, priority.assess(self.snapshot(30, expected_reply_date="2026-09-20"))["level"])

    def test_blocked_check_preserves_last_verified_priority(self):
        snapshot = self.snapshot(5)
        app = dict(engagement=snapshot, attention_priority=priority.assess(snapshot))
        before = deepcopy(app["attention_priority"])
        priority.refresh(app, dict(outcome="blocked", observed_at="2026-10-01T08:00:00Z", source_ref="login.txt"))
        self.assertEqual(before["level"], app["attention_priority"]["level"])
        self.assertEqual(before["waiting_days"], app["attention_priority"]["waiting_days"])
        self.assertEqual("blocked", app["attention_priority"]["verification"])

    def test_daily_no_reply_observation_ages_the_existing_wait(self):
        snapshot = self.snapshot(5)
        app = dict(engagement=snapshot, attention_priority=priority.assess(snapshot))
        priority.refresh(app, dict(outcome="no_reply", observed_at="2026-10-01T08:00:00Z", source_ref="new.txt"))
        self.assertEqual(4, app["attention_priority"]["level"])
        self.assertEqual(snapshot["waiting_since"], app["engagement"]["waiting_since"])

    def test_reply_invalidates_old_silence_clock_until_reassessed(self):
        snapshot = self.snapshot(30)
        app = dict(engagement=snapshot, attention_priority=priority.assess(snapshot))
        priority.refresh(app, dict(outcome="replied", observed_at="2026-09-13T08:01:00Z", source_ref="reply.txt"))
        priority.refresh(app, dict(outcome="no_reply", observed_at="2026-09-14T08:01:00Z", source_ref="next.txt"))
        self.assertEqual("unknown", app["engagement"]["waiting_on"])
        self.assertIsNone(app["attention_priority"]["level"])

    def test_another_outgoing_message_cannot_reset_the_clock(self):
        now = datetime.now(timezone.utc) - timedelta(minutes=1)
        old = dict(observed_at=(now-timedelta(minutes=1)).isoformat(), waiting_on="employer", waiting_since=(now.date()-timedelta(days=20)).isoformat(), last_inbound_date=None)
        new = self.snapshot(1, observed_at=now.isoformat(), waiting_since=(now.date()-timedelta(days=1)).isoformat())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "source.txt").write_text("Synthetic test source")
            repo = SimpleNamespace(repo_root=root, load=lambda _: {"applications":[{"application_id":"app-test", "status":"submitted_verified", "engagement":old}]})
            with self.assertRaisesRegex(ValueError, "cannot reset"):
                priority.save(repo, "app-test", new, "test")


if __name__ == "__main__":
    unittest.main()
