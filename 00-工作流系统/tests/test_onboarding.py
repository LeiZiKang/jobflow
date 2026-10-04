"""Onboarding and channel precedence, isolated from all real personal files."""

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

BIN = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN))
import jobflow
import jobflow_doctor as doctor
from jobflow_profile import CHANNEL_CONFIGS, ProfileError, load_channel_config, resolve_channel_config


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / "repo"
        self.system = self.root / "00-工作流系统"
        self.profile = self.base / "profile"
        self.profile.mkdir()
        for name in ("examples/screening", "config"):
            shutil.copytree(BIN.parent / name, self.system / name)
        env = patch.dict(os.environ, {"JOBFLOW_PROFILE_DIR": str(self.profile),
                                      "JOBFLOW_RUNTIME_DIR": str(self.base / "runtime")})
        env.start()
        self.addCleanup(env.stop)
        node = patch.object(doctor.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "v20.9.0\n", ""))
        node.start()
        self.addCleanup(node.stop)
        self.goals = json.loads((self.system / "examples/screening/goals.example.json").read_text())

    def write(self, name, value):
        (self.profile / name).write_text(json.dumps(value), encoding="utf-8")

    def ready(self):
        (self.system / "state").mkdir(exist_ok=True)
        (self.system / "state/current.json").write_text("{}")
        self.goals["dimensions"]["salary"]["rubric"] = "PRIVATE_GOAL_MARKER"
        self.write("goals.json", self.goals)
        self.write("search_channels.json", {"required_daily": ["official_ats"]})
        (self.root / "03-简历").mkdir(exist_ok=True)
        (self.root / "03-简历/resume.md").write_text("Fictional resume")

    def checks(self):
        return {c["id"]: c for c in doctor.check_readiness(self.root)["checks"]}

    def cli(self, args):
        output = io.StringIO()
        with patch.object(jobflow, "JobflowRepo", return_value=jobflow.JobflowRepo(self.system)), contextlib.redirect_stdout(output):
            code = jobflow.main(args)
        return code, output.getvalue()

    def test_fresh_missing_requirements_and_semantic_example_equality(self):
        self.write("goals.json", dict(reversed(list(self.goals.items()))))
        checks = self.checks()
        for key in ("workspace", "goals", "resume", "search_channels"):
            self.assertEqual(checks[key]["status"], "missing")
        self.assertIn("还没按你的目标改", checks["goals"]["fix"])
        code, output = self.cli(["doctor", "--json"])
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(output)["ready"])

    def test_ready_with_warnings_and_no_private_output_or_identity_read(self):
        self.ready()
        self.write("identity.json", {"name": "PRIVATE_IDENTITY_MARKER"})
        original = Path.read_text

        def guarded(path, *args, **kwargs):
            self.assertNotEqual(path.name, "identity.json")
            return original(path, *args, **kwargs)

        with patch.object(Path, "read_text", guarded), patch.object(doctor.shutil, "which", return_value=None):
            for args in (["doctor"], ["doctor", "--json"]):
                code, output = self.cli(args)
                self.assertEqual(code, 0)
                self.assertNotIn("PRIVATE_", output)
                self.assertIn("warn", output)
        (self.profile / "identity.json").unlink()
        self.assertEqual(self.checks()["identity"]["status"], "warn")
        self.assertTrue(doctor.check_readiness(self.root)["ready"])

    def test_invalid_goals_fail_without_echoing_values(self):
        self.ready()
        for value in ("{PRIVATE_BROKEN", '[]', '{"PRIVATE_INVALID": true}'):
            (self.profile / "goals.json").write_text(value)
            code, output = self.cli(["doctor", "--json"])
            self.assertEqual(code, 1)
            self.assertNotIn("PRIVATE_", output)

    def test_invalid_weights_fail(self):
        self.ready()
        self.goals["dimensions"]["salary"]["weight"] = 1
        self.write("goals.json", self.goals)
        self.assertEqual(self.checks()["goals"]["status"], "missing")

    def test_doctor_is_read_only_and_checks_are_independent(self):
        self.ready()
        self.write("identity.json", {"name": "PRIVATE_IDENTITY_MARKER"})
        (self.profile / "search_channels.json").write_text("{")
        before = {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        checks = self.checks()
        self.assertEqual(checks["search_channels"]["status"], "missing")
        self.assertEqual(checks["identity"]["status"], "ok")
        after = {p: p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_resume_extensions_nested_files_and_readme_exclusion(self):
        self.ready()
        resume = self.root / "03-简历"
        (resume / "resume.md").unlink()
        (resume / "README.MD").write_text("Instructions")
        (resume / "notes.html").write_text("Not a resume format")
        (resume / "folder.pdf").mkdir()
        self.assertEqual(self.checks()["resume"]["status"], "missing")
        nested = resume / "versions"
        nested.mkdir()
        for suffix in ("PDF", "md", "json", "docx", "txt"):
            path = nested / ("resume." + suffix)
            path.write_text("Fictional")
            self.assertEqual(self.checks()["resume"]["status"], "ok")
            path.unlink()

    def test_python_and_node_versions_and_unavailable_node(self):
        self.ready()
        with patch.object(doctor.sys, "version_info", (3, 8, 9)):
            self.assertEqual(self.checks()["python"]["status"], "missing")
        for version, expected in (("v20.8.9", "warn"), ("v20.9.0", "ok"), ("v22.0.0", "ok"), ("broken", "warn")):
            with patch.object(doctor.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, version)):
                self.assertEqual(self.checks()["node"]["status"], expected)
        for error in (FileNotFoundError(), subprocess.TimeoutExpired("node", 5)):
            with patch.object(doctor.subprocess, "run", side_effect=error):
                self.assertTrue(doctor.check_readiness(self.root)["ready"])
                self.assertEqual(self.checks()["node"]["status"], "warn")

    def test_channel_defaults_overrides_and_cli(self):
        for name in CHANNEL_CONFIGS:
            default = self.system / "config" / name
            before = default.read_bytes()
            self.assertEqual(resolve_channel_config(name, repo_root=self.root), default)
            self.assertEqual(load_channel_config(name, repo_root=self.root), json.loads(before))
            self.write(name, {"selected": ["fictional_channel"]})
            self.assertEqual(resolve_channel_config(name, repo_root=self.root), self.profile / name)
            code, output = self.cli(["config", name])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output), {"selected": ["fictional_channel"]})
            self.assertEqual(default.read_bytes(), before)

    def test_broken_overrides_do_not_fall_back(self):
        for name in CHANNEL_CONFIGS:
            for invalid in ("{", "[]"):
                (self.profile / name).write_text(invalid)
                with self.assertRaises(ProfileError):
                    load_channel_config(name, repo_root=self.root)
            (self.profile / name).unlink()
            (self.profile / name).symlink_to(self.base / "missing.json")
            with self.assertRaises(ProfileError):
                load_channel_config(name, repo_root=self.root)

    def test_unsafe_profile_locations_and_links(self):
        with patch.dict(os.environ, {"JOBFLOW_PROFILE_DIR": str(self.root / "personal")}):
            self.assertEqual(self.checks()["goals"]["status"], "missing")
            with self.assertRaises(ProfileError):
                resolve_channel_config("search_channels.json", repo_root=self.root)
        (self.profile / "search_channels.json").symlink_to(self.system / "config/search_channels.json")
        with self.assertRaises(ProfileError):
            load_channel_config("search_channels.json", repo_root=self.root)
        with self.assertRaises(ProfileError):
            resolve_channel_config("../identity.json", repo_root=self.root)

    def test_existing_envelope_routes_channel_inputs_through_resolver(self):
        repo = jobflow.JobflowRepo(self.system)
        job = {"job_id": "fictional-job", "envelope": {"inputs": [
            "00-工作流系统/config/" + name for name in CHANNEL_CONFIGS]}}
        with patch.object(repo, "find_job", return_value=job):
            rendered = repo.job_envelope("fictional-job")
        for name in CHANNEL_CONFIGS:
            self.assertIn("jobflow.py config " + name, rendered)
            self.assertNotIn("00-工作流系统/config/" + name, rendered)


if __name__ == "__main__":
    unittest.main()
