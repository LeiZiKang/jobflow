import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location("jobflowd", HERE / "jobflowd.py")
assert SPEC and SPEC.loader
jobflowd = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(jobflowd)


class JobflowdTests(unittest.TestCase):
    def test_today_and_evidence_view_are_scoped_and_escaped(self):
        controller = self.make_controller()
        app = {"application_id": "app-test", "company": "<script>bad</script>", "role": "iOS", "status": "application_prepared", "evidence_refs": []}
        (controller.repo_root / "00-工作流系统/state/applications.json").write_text(json.dumps({"applications": [app]}))
        self.assertEqual(0, controller.today()["verified_count"])
        evidence = controller.submission_evidence("app-test").decode()
        self.assertIn("&lt;script&gt;", evidence)
        self.assertNotIn("<script>", evidence)
        with self.assertRaises(ValueError):
            controller.submission_evidence("../arbitrary")

    def test_materials_only_exposes_registered_safe_pdfs(self):
        controller = self.make_controller()
        self.assertEqual({"resumes": []}, controller.materials())
        root = controller.repo_root
        (root / "03-简历").mkdir()
        (root / "03-简历/registered.pdf").write_bytes(b"%PDF-1.4 fixture")
        (root / "03-简历/unregistered.pdf").write_bytes(b"%PDF-1.4 fixture")
        (root / "03-简历/source.md").write_text("fixture")
        (root / "03-简历/link.pdf").symlink_to(root / "03-简历/registered.pdf")
        records = [dict(id="safe", label="通用中文", language="zh", path="03-简历/registered.pdf", source_path="03-简历/source.md")]
        for index, path in enumerate(["03-简历/missing.pdf", "../outside.pdf", str(root / "03-简历/registered.pdf"), "03-简历/link.pdf", "03-简历/source.md"]):
            records.append(dict(id=str(index), label="不可用", language="en", path=path))
        (root / "00-工作流系统/state/personal_materials.json").write_text(json.dumps({"schema_version": 1, "resumes": records}))
        result = controller.materials()["resumes"]
        self.assertEqual(len(records), len(result))
        self.assertTrue(result[0]["available"])
        self.assertIn("/api/document?path=", result[0]["view_url"])
        self.assertIsNotNone(result[0]["source_url"])
        self.assertTrue(all(not row["available"] and row["view_url"] is None for row in result[1:]))
        self.assertNotIn("unregistered", json.dumps(result))

    def test_application_phone_prep_requires_ready_safe_matching_file(self):
        controller = self.make_controller()
        root = controller.repo_root
        directory = root / "04-面试/电话准备"
        directory.mkdir(parents=True)
        path = "04-面试/电话准备/app-test.html"
        app = dict(application_id="app-test", company="Fixture", role="iOS", status="application_prepared",
                   phone_prep={"status": "ready", "path": path})
        state = root / "00-工作流系统/state/applications.json"
        state.write_text(json.dumps({"applications": [app]}))
        self.assertFalse(controller.applications()[0]["phone_prep_available"])
        (root / path).write_text("<h1>fixture</h1>")
        self.assertTrue(controller.applications()[0]["phone_prep_available"])
        self.assertIsNotNone(controller.applications()[0]["phone_prep_url"])
        for prep in ({"status": "draft", "path": path}, {"status": "ready", "path": "04-面试/电话准备/../电话准备/app-test.html"}):
            app["phone_prep"] = prep
            state.write_text(json.dumps({"applications": [app]}))
            self.assertIsNone(controller.applications()[0]["phone_prep_url"])

    def make_controller(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "repo"
        (root / "00-工作流系统/state").mkdir(parents=True)
        (root / "00-工作流系统/CONSTITUTION.md").write_text("rules", encoding="utf-8")
        (root / "00-工作流系统/DECIDER_BRIEF.md").write_text("brief", encoding="utf-8")
        (root / "00-工作流系统/state/memory.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "revision": 0,
                    "updated_at": "2026-09-02T00:00:00Z",
                    "items": [],
                }
            ),
            encoding="utf-8",
        )
        controller = jobflowd.LocalController(root, Path(temp.name) / "runs.sqlite3", max_workers=6)
        self.addCleanup(controller.close)
        return controller

    def test_memory_endpoint_reads_canonical_repo_state(self):
        controller = self.make_controller()
        memory = controller.memory()
        self.assertEqual(0, memory["revision"])
        self.assertEqual(0, memory["counts"]["accepted"])
        self.assertIn("ACCEPTED LONG-TERM MEMORY", memory["context_preview"])

    @staticmethod
    def wait_terminal(controller, run_id, timeout=5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            run = controller.get_run(run_id)
            if run["status"] in jobflowd.TERMINAL_RUN_STATES:
                return run
            time.sleep(0.02)
        raise AssertionError(f"run did not finish: {run_id}")

    def test_single_run_stages_result_without_canonical_write(self):
        controller = self.make_controller()

        def fake_run(backend, prompt, repo_root, role, effort, on_event=None, **kwargs):
            if on_event:
                on_event({"type": "assistant_message", "message": "working", "backend": backend})
            return {
                "backend": backend,
                "status": "completed",
                "exit_code": 0,
                "final_text": "staged result",
                "session_id": "provider-session",
                "events": [],
                "error": None,
            }

        with patch.object(jobflowd, "run_agent", fake_run):
            created = controller.create_single("read only task", "codex", "max")
            run = self.wait_terminal(controller, created["run_id"])
        self.assertEqual("completed", run["status"])
        self.assertEqual("staged result", run["final_text"])
        self.assertFalse(run["metadata"]["canonical_write_allowed"])
        self.assertTrue(any(item["event_type"] == "assistant_message" for item in run["events"]))

    def test_ensemble_runs_parallel_children_then_primary_evaluator(self):
        controller = self.make_controller()
        call_roles = []

        def fake_probe():
            return {"codex": {"available": True}, "claude": {"available": True}}

        def fake_run(backend, prompt, repo_root, role, effort, on_event=None, **kwargs):
            call_roles.append(role)
            return {
                "backend": backend,
                "status": "completed",
                "exit_code": 0,
                "final_text": "final evaluation" if role == "primary_evaluator" else f"{backend} findings",
                "session_id": None,
                "events": [],
                "error": None,
            }

        with patch.object(jobflowd, "probe_backends", fake_probe), patch.object(
            jobflowd, "run_agent", fake_run
        ):
            created = controller.create_ensemble("find jobs")
            run = self.wait_terminal(controller, created["run_id"])
        self.assertEqual("completed", run["status"])
        self.assertEqual("final evaluation", run["final_text"])
        self.assertEqual(3, len(run["children"]))
        self.assertEqual(2, call_roles.count("search"))
        self.assertEqual(1, call_roles.count("primary_evaluator"))

    def test_restart_marks_unfinished_run_interrupted(self):
        controller = self.make_controller()
        queued = controller.store.create_run(
            mode="single", role="search", backend="codex", status="running", prompt="x"
        )
        replacement = jobflowd.LocalController(
            controller.repo_root, controller.store.db_path, max_workers=2
        )
        self.addCleanup(replacement.close)
        run = replacement.get_run(queued["run_id"])
        self.assertEqual("interrupted", run["status"])
        self.assertIn("no external action", run["events"][-1]["message"])

    def test_token_file_is_owner_only(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "control-token"
            jobflowd.write_token(path, "secret-value")
            self.assertEqual(0o600, os.stat(path).st_mode & 0o777)
            self.assertEqual("secret-value", path.read_text(encoding="utf-8").strip())

    def test_backend_health_is_derived_from_latest_persisted_run(self):
        controller = self.make_controller()
        controller.store.create_run(
            mode="single",
            role="primary",
            backend="codex",
            status="completed",
            prompt="x",
            final_text="ok",
        )
        controller.store.create_run(
            mode="single",
            role="primary",
            backend="claude",
            status="failed",
            prompt="x",
            error="Your session has expired. Please reauthenticate.",
        )
        with patch.object(
            jobflowd,
            "probe_backends",
            return_value={
                "codex": {"available": True, "version": "test"},
                "claude": {"available": True, "version": "test"},
            },
        ):
            replacement = jobflowd.LocalController(
                controller.repo_root, controller.store.db_path, max_workers=2
            )
            self.addCleanup(replacement.close)
            statuses = {item["backend"]: item["status"] for item in replacement.agents()}
        self.assertEqual("ready", statuses["codex"])
        self.assertEqual("auth_required", statuses["claude"])

    def test_multiple_ensembles_do_not_deadlock_agent_pool(self):
        controller = self.make_controller()

        def fake_run(backend, prompt, repo_root, role, effort, on_event=None, **kwargs):
            return {
                "backend": backend,
                "status": "completed",
                "exit_code": 0,
                "final_text": f"{role} ok",
                "session_id": None,
                "events": [],
                "error": None,
            }

        with patch.object(jobflowd, "run_agent", fake_run):
            parents = [controller.create_ensemble(f"request {index}") for index in range(4)]
            completed = [self.wait_terminal(controller, run["run_id"]) for run in parents]
        self.assertTrue(all(run["status"] == "completed" for run in completed))
        self.assertTrue(all(len(run["children"]) == 3 for run in completed))

    def test_shutdown_interrupts_ensemble_before_evaluator(self):
        controller = self.make_controller()

        def waiting_run(backend, prompt, repo_root, role, effort, on_event=None, **kwargs):
            deadline = time.time() + 2
            while not controller._closing.is_set() and time.time() < deadline:
                time.sleep(0.01)
            return {
                "backend": backend,
                "status": "failed",
                "exit_code": -15,
                "final_text": "",
                "session_id": None,
                "events": [],
                "error": "terminated",
            }

        with patch.object(jobflowd, "run_agent", waiting_run):
            parent = controller.create_ensemble("long search")
            deadline = time.time() + 2
            while controller.get_run(parent["run_id"])["status"] != "running" and time.time() < deadline:
                time.sleep(0.01)
            controller.begin_shutdown()
            controller.close()
        result = controller.get_run(parent["run_id"])
        self.assertEqual("interrupted", result["status"])
        self.assertFalse(any(child["role"] == "primary_evaluator" for child in result["children"]))


if __name__ == "__main__":
    unittest.main()
