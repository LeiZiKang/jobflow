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
import jobflow_environment as environment
from jobflow_profile import CHANNEL_CONFIGS, ProfileError, load_channel_config, resolve_channel_config
from jobflow_environment import console_dependencies_ready
from jobflow_screening import profile_summary


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
                                      "JOBFLOW_RUNTIME_DIR": str(self.base / "runtime"),
                                      "JOBFLOW_TOOLS_DIR": str(self.base / "tools"),
                                      "JOBFLOW_APPLICATIONS_DIR": str(self.base / "apps"),
                                      "JOBFLOW_SYSTEM_APPLICATIONS_DIR": str(self.base / "system-apps"),
                                      "JOBFLOW_LANG": "zh",
                                      "JOBFLOW_CONSOLE_DIR": str(self.root / "console")})
        env.start()
        self.addCleanup(env.stop)
        node = patch.object(environment.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "v20.9.0\n", ""))
        node.start()
        self.addCleanup(node.stop)
        for mock in (patch.object(doctor, "xcode_clt_ready", return_value=True),
                     patch.object(doctor.platform, "system", return_value="Darwin")):
            mock.start()
            self.addCleanup(mock.stop)
        node_path = self.base / "path"
        node_path.mkdir()
        for name in ("node", "npm"):
            executable = node_path / name
            executable.write_text("#!/bin/sh\necho v20.9.0\n")
            executable.chmod(0o755)
        path_env = patch.dict(os.environ, {"PATH": str(node_path) + os.pathsep + os.environ.get("PATH", "")})
        path_env.start()
        self.addCleanup(path_env.stop)
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

    def test_language_precedence_and_english_json(self):
        for explicit, configured, locale, expected in (
            ("en", "zh", "zh_CN.UTF-8", "en"),
            ("zh", "en", "en_US.UTF-8", "zh"),
            (None, "en", "zh_CN.UTF-8", "en"),
            (None, "zh", "C", "zh"),
            (None, "", "zh_TW.UTF-8", "zh"),
            (None, "", "en_US.UTF-8", "en"),
            (None, "", "C", "en"),
            (None, "", "", "en"),
        ):
            with self.subTest(explicit=explicit, configured=configured, locale=locale):
                with patch.dict(os.environ, {"JOBFLOW_LANG": configured, "LANG": locale}):
                    self.assertEqual(doctor.resolve_language(explicit), expected)
                    args = ["doctor", "--json"] + (["--lang", explicit] if explicit else [])
                    code, output = self.cli(args)
                    self.assertEqual(code, 1)
                    first = json.loads(output)["checks"][0]
                    self.assertEqual(first["message"], "Ready" if expected == "en" else "已就绪")
        code, output = self.cli(["doctor", "--lang", "en"])
        self.assertEqual(code, 1)
        self.assertIn("(required)", output)
        self.assertIn("Not ready:", output)
        self.assertIn("copy the template and edit it:", output)
        self.ready()
        code, output = self.cli(["doctor", "--lang", "en"])
        self.assertEqual(code, 0)
        self.assertIn("Ready: all required checks passed.", output)

    def test_undecided_preference_is_ready_only_after_customizing_goals(self):
        self.ready()
        for mode in ("null", "omitted"):
            if mode == "omitted":
                self.goals.pop("foreign_first", None)
            else:
                self.goals["foreign_first"] = None
            self.write("goals.json", self.goals)
            self.assertIsNone(profile_summary(self.goals)["foreign_first"])
            self.assertEqual(self.cli(["doctor", "--json"])[0], 0)
        example = json.loads((self.system / "examples/screening/goals.example.json").read_text())
        example.pop("foreign_first", None)
        self.write("goals.json", example)
        self.assertEqual(self.checks()["goals"]["status"], "missing")

    def test_console_requires_both_executable_tools_and_honors_override(self):
        self.ready()
        console = self.root / "console"
        tools = console / "node_modules/.bin"
        tools.mkdir(parents=True)
        self.assertEqual(self.checks()["console_dependencies"]["status"], "warn")
        for name in ("tsc", "next"):
            path = tools / name
            path.write_text("#!/bin/sh\nexit 0\n")
            path.chmod(0o700)
            expected = "ok" if name == "next" else "warn"
            self.assertEqual(self.checks()["console_dependencies"]["status"], expected)
            self.assertEqual(console_dependencies_ready(console), expected == "ok")
        (tools / "next").chmod(0o600)
        self.assertFalse(console_dependencies_ready(console))
        self.assertEqual(self.checks()["console_dependencies"]["status"], "warn")
        (tools / "next").unlink()
        (tools / "next").symlink_to(tools / "missing")
        self.assertFalse(console_dependencies_ready(console))
        with patch.dict(os.environ, {"JOBFLOW_CONSOLE_DIR": str(self.base / "other-console")}):
            self.assertEqual(self.checks()["console_dependencies"]["status"], "warn")

    def test_channel_repair_command_can_be_copied_with_quoted_paths(self):
        directory = self.base / "profile with spaces and ' quote"
        with patch.dict(os.environ, {"JOBFLOW_PROFILE_DIR": str(directory)}):
            fix = self.checks()["search_channels"]["fix"]
            command = fix.split("：", 1)[1]
            process = subprocess.Popen(command, shell=True, cwd=self.root,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            _, error = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, error)
        self.assertEqual(json.loads((directory / "search_channels.json").read_text()),
                         json.loads((self.system / "config/search_channels.json").read_text()))

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
        for version, expected in (("v20.8.9", "missing"), ("v20.9.0", "ok"), ("v22.0.0", "ok"), ("broken", "missing")):
            with patch.object(environment.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, version)):
                self.assertEqual(self.checks()["node"]["status"], expected)
        for error in (FileNotFoundError(), subprocess.TimeoutExpired("node", 5)):
            with patch.object(environment.subprocess, "run", side_effect=error):
                self.assertTrue(doctor.check_readiness(self.root)["ready"])
                self.assertEqual(self.checks()["node"]["status"], "missing")

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
