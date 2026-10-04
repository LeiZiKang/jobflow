import importlib.util
import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "jobflow_memory.py"
SPEC = importlib.util.spec_from_file_location("jobflow_memory_test", SCRIPT)
assert SPEC and SPEC.loader
memory_module = importlib.util.module_from_spec(SPEC)
sys.modules["jobflow_memory_test"] = memory_module
SPEC.loader.exec_module(memory_module)


class MemoryStoreTests(unittest.TestCase):
    def make_store(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "repo"
        system = root / "00-工作流系统"
        (system / "state").mkdir(parents=True)
        (root / "AGENTS.md").write_text("rules", encoding="utf-8")
        document = {
            "schema_version": 1,
            "revision": 0,
            "updated_at": "2026-09-02T00:00:00Z",
            "items": [],
        }
        (system / "state/memory.json").write_text(
            json.dumps(document, ensure_ascii=False), encoding="utf-8"
        )
        return memory_module.MemoryStore(system, runtime_dir=root / "runtime")

    def propose(self, store, **overrides):
        arguments = {
            "memory_type": "fact",
            "scope": "global",
            "subject": "Fixture",
            "statement": "A source-backed fixture fact.",
            "source_refs": ["AGENTS.md"],
            "author_type": "agent",
            "author_id": "agent-a",
            "evidence_strength": "fixture",
            "tags": ["fixture"],
        }
        arguments.update(overrides)
        return store.propose(**arguments)

    def test_current_repository_memory_validates(self):
        store = memory_module.MemoryStore(Path(__file__).resolve().parents[1])
        self.assertEqual([], store.validate())

    def test_proposed_memory_is_excluded_until_reviewed(self):
        store = self.make_store()
        proposed = self.propose(store)
        self.assertNotIn(proposed["memory_id"], store.context())
        accepted = store.decide(
            proposed["memory_id"],
            "accepted",
            reviewer_type="human",
            reviewer_id="user",
            note="confirmed",
        )
        self.assertEqual("accepted", accepted["status"])
        self.assertIn(proposed["memory_id"], store.context())
        self.assertEqual(2, store.load()["revision"])

    def test_agent_cannot_accept_its_own_memory(self):
        store = self.make_store()
        proposed = self.propose(store)
        with self.assertRaisesRegex(ValueError, "cannot accept its own"):
            store.decide(
                proposed["memory_id"],
                "accepted",
                reviewer_type="agent",
                reviewer_id="agent-a",
                note="self review",
            )
        self.assertEqual("proposed", store.load()["items"][0]["status"])

    def test_preference_requires_human_review(self):
        store = self.make_store()
        proposed = self.propose(
            store,
            memory_type="preference",
            author_type="human",
            author_id="user",
        )
        with self.assertRaisesRegex(ValueError, "require human review"):
            store.decide(
                proposed["memory_id"],
                "accepted",
                reviewer_type="agent",
                reviewer_id="decider-b",
                note="agent review",
            )

    def test_accepting_new_memory_supersedes_old_memory(self):
        store = self.make_store()
        old = self.propose(store, statement="old")
        store.decide(old["memory_id"], "accepted", reviewer_type="human", reviewer_id="user", note="ok")
        new = self.propose(store, statement="new", supersedes=[old["memory_id"]])
        store.decide(new["memory_id"], "accepted", reviewer_type="human", reviewer_id="user", note="updated")
        by_id = {item["memory_id"]: item for item in store.load()["items"]}
        self.assertEqual("superseded", by_id[old["memory_id"]]["status"])
        self.assertEqual(new["memory_id"], by_id[old["memory_id"]]["superseded_by"])
        self.assertNotIn(old["memory_id"], store.context())

    def test_expected_revision_prevents_stale_writer(self):
        store = self.make_store()
        self.propose(store, expected_revision=0)
        with self.assertRaises(memory_module.MemoryConflictError):
            self.propose(store, expected_revision=0)

    def test_concurrent_proposals_do_not_lose_updates(self):
        store = self.make_store()
        with ThreadPoolExecutor(max_workers=8) as pool:
            memories = list(
                pool.map(
                    lambda index: self.propose(store, subject=f"Fixture {index}"),
                    range(24),
                )
            )
        document = store.load()
        self.assertEqual(24, len(document["items"]))
        self.assertEqual(24, document["revision"])
        self.assertEqual(24, len({item["memory_id"] for item in memories}))

    def test_secret_like_memory_is_rejected(self):
        store = self.make_store()
        with self.assertRaisesRegex(ValueError, "secret-like"):
            self.propose(store, statement="api_key=abcdefghijklmnop")

    def test_expired_memory_is_not_in_context(self):
        store = self.make_store()
        proposed = self.propose(store)
        document = store.load()
        document["items"][0]["valid_from"] = "2019-01-01T00:00:00Z"
        document["items"][0]["valid_until"] = "2020-01-01T00:00:00Z"
        store.path.write_text(json.dumps(document), encoding="utf-8")
        store.decide(proposed["memory_id"], "accepted", reviewer_type="human", reviewer_id="user", note="historical")
        self.assertNotIn(proposed["memory_id"], store.context())

    def test_future_memory_is_not_in_context(self):
        store = self.make_store()
        proposed = self.propose(store)
        document = store.load()
        document["items"][0]["valid_from"] = "2099-01-01T00:00:00Z"
        store.path.write_text(json.dumps(document), encoding="utf-8")
        store.decide(proposed["memory_id"], "accepted", reviewer_type="human", reviewer_id="user", note="future")
        self.assertNotIn(proposed["memory_id"], store.context())


if __name__ == "__main__":
    unittest.main()
