import importlib.util
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


SCRIPT = Path(__file__).with_name("runtime_store.py")
SPEC = importlib.util.spec_from_file_location("jobflow_runtime_store", SCRIPT)
assert SPEC and SPEC.loader
runtime_store = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime_store)


class RuntimeStoreTests(unittest.TestCase):
    def make_store(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "runtime.sqlite3"
        return runtime_store.RuntimeStore(path), path

    def test_wal_schema_and_busy_timeout(self):
        store, path = self.make_store()
        store.create_run("run-root", mode="primary", role="decider", backend="codex")

        connection = sqlite3.connect(path)
        try:
            self.assertEqual("wal", connection.execute("PRAGMA journal_mode").fetchone()[0])
            self.assertEqual(
                {"runs", "run_events"},
                {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type = 'table' AND name IN ('runs', 'run_events')"
                    )
                },
            )
        finally:
            connection.close()

        with store._connection() as operation_connection:
            self.assertEqual(5_000, operation_connection.execute("PRAGMA busy_timeout").fetchone()[0])

    def test_create_get_update_and_parent_child_listing(self):
        store, _ = self.make_store()
        root = store.create_run(
            "run-root",
            mode="primary",
            role="decider",
            backend="codex",
            status="running",
            prompt="Evaluate staged jobs",
            task_id="task-review",
            model="gpt-test",
            effort="high",
            metadata={"source": "local-ui"},
        )
        child = store.create_run(
            "run-search",
            parent_run_id=root["run_id"],
            mode="subagent",
            role="searcher",
            backend="claude",
            prompt="Search one source",
        )

        self.assertEqual("run-root", child["parent_run_id"])
        self.assertEqual(["run-search"], [run["run_id"] for run in store.list_runs(parent_run_id="run-root")])
        self.assertEqual(["run-root"], [run["run_id"] for run in store.list_runs(roots_only=True)])
        self.assertEqual({"source": "local-ui"}, store.get_run("run-root")["metadata"])

        before = child["updated_at"]
        updated = store.update_run(
            "run-search",
            status="completed",
            final_text="One verified candidate",
            session_id="provider-session-1",
            metadata={"candidate_count": 1},
        )
        self.assertEqual("completed", updated["status"])
        self.assertEqual("One verified candidate", updated["final_text"])
        self.assertEqual({"candidate_count": 1}, updated["metadata"])
        self.assertGreaterEqual(updated["updated_at"], before)

    def test_missing_parent_and_missing_update_are_loud(self):
        store, _ = self.make_store()
        with self.assertRaises(runtime_store.RunNotFoundError):
            store.create_run("child", parent_run_id="missing")
        with self.assertRaises(runtime_store.RunNotFoundError):
            store.update_run("missing", status="failed")
        self.assertIsNone(store.get_run("missing"))

    def test_event_stream_is_ordered_and_updates_run(self):
        store, _ = self.make_store()
        run = store.create_run("run-events", status="running")
        first = store.append_event(
            run["run_id"],
            "agent.started",
            message="Agent started",
            payload={"provider": "codex"},
        )
        second = store.append_event(
            run["run_id"],
            "agent.delta",
            payload={"text": "candidate"},
        )

        self.assertEqual(1, first["sequence"])
        self.assertEqual(2, second["sequence"])
        self.assertEqual(
            ["agent.started", "agent.delta"],
            [event["event_type"] for event in store.list_events(run["run_id"])],
        )
        self.assertEqual([2], [event["sequence"] for event in store.list_events(run["run_id"], after_sequence=1)])
        self.assertGreaterEqual(store.get_run(run["run_id"])["updated_at"], run["updated_at"])
        with self.assertRaises(runtime_store.RunNotFoundError):
            store.append_event("missing", "agent.started")
        with self.assertRaises(runtime_store.RunNotFoundError):
            store.list_events("missing")

    def test_concurrent_event_appends_have_unique_monotonic_sequences(self):
        store, _ = self.make_store()
        store.create_run("run-concurrent", status="running")

        count = 80
        with ThreadPoolExecutor(max_workers=8) as executor:
            events = list(
                executor.map(
                    lambda number: store.append_event(
                        "run-concurrent", "agent.delta", payload={"number": number}
                    ),
                    range(count),
                )
            )

        self.assertEqual(count, len(events))
        persisted = store.list_events("run-concurrent")
        self.assertEqual(list(range(1, count + 1)), [event["sequence"] for event in persisted])
        self.assertEqual(set(range(count)), {event["payload"]["number"] for event in persisted})

    def test_secret_values_are_rejected_but_secret_references_are_allowed(self):
        store, _ = self.make_store()
        with self.assertRaises(runtime_store.SecretValueError):
            store.create_run("bad-prompt", prompt="Authorization: Bearer abcdef")
        with self.assertRaises(runtime_store.SecretValueError):
            store.create_run("bad-metadata", metadata={"api_key": "plaintext-key"})
        with self.assertRaises(runtime_store.SecretValueError):
            store.create_run("bad-generic-secret", metadata={"secret": "plaintext"})
        with self.assertRaises(runtime_store.SecretValueError):
            store.create_run("bad-camel-token", metadata={"accessToken": "plaintext"})
        with self.assertRaises(runtime_store.SecretValueError):
            store.create_run("bad-prefixed-key", metadata={"openai_api_key": "plaintext"})

        run = store.create_run(
            "safe-reference",
            metadata={"api_key": "secret://openai/jobflow"},
        )
        self.assertEqual("secret://openai/jobflow", run["metadata"]["api_key"])
        with self.assertRaises(runtime_store.SecretValueError):
            store.update_run(run["run_id"], final_text="password=plaintext")
        with self.assertRaises(runtime_store.SecretValueError):
            store.append_event(
                run["run_id"], "unsafe", payload={"cookie": "session=plaintext"}
            )

    def test_non_json_payload_is_rejected(self):
        store, _ = self.make_store()
        store.create_run("run-json")
        with self.assertRaisesRegex(ValueError, "JSON serializable"):
            store.append_event("run-json", "bad", payload={"values": {1, 2}})

    def test_deleted_database_is_rebuilt_without_canonical_state(self):
        store, path = self.make_store()
        store.create_run("old-run")
        path.unlink()
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{path}{suffix}")
            if sidecar.exists():
                sidecar.unlink()

        rebuilt = store.create_run("new-run")
        self.assertEqual("new-run", rebuilt["run_id"])
        self.assertIsNone(store.get_run("old-run"))
        self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
