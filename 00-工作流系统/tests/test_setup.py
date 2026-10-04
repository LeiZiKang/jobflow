"""Offline setup contracts. Every destination is isolated; never download real assets."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

BIN = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN))
import jobflow_environment as environment
import jobflow_setup as setup
import jobflow_doctor as doctor


class SetupTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.tools = self.base / "tools"
        self.path = self.base / "path"
        self.path.mkdir()
        env = patch.dict(os.environ, {
            "JOBFLOW_PROFILE_DIR": str(self.base / "profile"),
            "JOBFLOW_RUNTIME_DIR": str(self.base / "runtime"),
            "JOBFLOW_TOOLS_DIR": str(self.tools),
            "JOBFLOW_APPLICATIONS_DIR": str(self.base / "apps"),
            "JOBFLOW_SYSTEM_APPLICATIONS_DIR": str(self.base / "system-apps"),
            "PYTHONPYCACHEPREFIX": "/tmp/jf-pyc",
            "PATH": str(self.path),
        })
        env.start()
        self.addCleanup(env.stop)
        blocked = patch.object(setup, "download", side_effect=AssertionError("No network in tests"))
        blocked.start()
        self.addCleanup(blocked.stop)

    def executable(self, path, version="v20.9.0"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"#!/bin/sh\nprintf '%s\\n' '{version}'\n")
        path.chmod(0o755)
        return path

    def archive(self, unsafe=None):
        top = f"node-v{setup.NODE_VERSION}-darwin-arm64"
        archive = self.base / (top + ".tar.gz")
        with tarfile.open(archive, "w:gz") as tar:
            for name in ("node", "npm"):
                content = b"#!/bin/sh\necho v24.21.0\n"
                info = tarfile.TarInfo(top + "/bin/" + name)
                info.mode = 0o755
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))
            if unsafe:
                info = tarfile.TarInfo(unsafe)
                info.size = 1
                tar.addfile(info, io.BytesIO(b"x"))
        sums = self.base / "SHASUMS256.txt"
        sums.write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + "  " + archive.name + "\n")
        return archive, sums

    def result(self, missing=()):
        return {"ready": True, "checks": [
            {"id": key, "install": key, "status": "warn" if key in missing else "ok", "message": "test"}
            for key in setup.ITEMS]}

    def test_plan_order_dedup_and_noninstallable(self):
        result = self.result(("node", "xcode_clt"))
        result["checks"] += [{"status": "missing", "install": "xcode_clt"}, {"status": "missing", "install": None}]
        self.assertEqual(setup.plan(result), ["xcode_clt", "node"])
        self.assertEqual(setup.plan(self.result()), [])

    def test_architecture_urls_and_destinations(self):
        for machine, expected in (("arm64", "arm64"), ("aarch64", "arm64"), ("x86_64", "x64"), ("x64", "x64")):
            self.assertEqual(setup.architecture(machine), expected)
            self.assertIn(f"darwin-{expected}.tar.gz", setup.node_urls(machine)[0])
        with self.assertRaises(ValueError):
            setup.architecture("unknown")
        self.assertEqual(environment.tools_directory(), self.tools)
        self.assertEqual(environment.applications_directory(), self.base / "apps")

    def test_clt_is_required_and_macos_only(self):
        with patch.object(doctor, "xcode_clt_ready", return_value=False), patch.object(doctor.platform, "system", return_value="Darwin"):
            checks = {c["id"]: c for c in doctor.check_readiness(self.base)["checks"]}
            self.assertEqual(checks["xcode_clt"]["status"], "missing")
            self.assertTrue(checks["xcode_clt"]["required"])
            self.assertEqual(checks["xcode_clt"]["install"], "xcode_clt")
        with patch.object(doctor.platform, "system", return_value="Linux"):
            checks = {c["id"]: c for c in doctor.check_readiness(self.base, lang="en")["checks"]}
            self.assertEqual(checks["macos"]["status"], "missing")
            self.assertIn("only macOS", checks["macos"]["fix"])

    def test_read_doctor_uses_existing_json_cli(self):
        result = self.result()
        with patch.object(setup.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, json.dumps(result))) as run:
            self.assertEqual(setup.read_doctor(self.base, "zh"), result)
            self.assertEqual(run.call_args.args[0][-4:], ["doctor", "--json", "--lang", "zh"])

    def test_download_failure_has_bounded_attempt_and_manual_guidance(self):
        with patch.object(setup, "read_doctor", return_value=self.result(("node",))), patch.object(setup.platform, "system", return_value="Darwin"), patch.object(setup, "download", side_effect=RuntimeError("HTTP error / asset unavailable")) as download, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(setup.main(["--yes", "node"]), 1)
            download.assert_called_once()
            self.assertIn("Install manually", error.getvalue())
            self.assertFalse(self.tools.exists())

    def test_node_priority_old_path_fallback_and_absence(self):
        self.assertIsNone(environment.resolve_node())
        managed = self.executable(self.tools / "node/bin/node")
        self.assertEqual(environment.resolve_node(), managed)
        path_node = self.executable(self.path / "node", "v20.8.9")
        self.assertEqual(environment.resolve_node(), managed)
        self.executable(path_node)
        self.assertEqual(environment.resolve_node(), path_node)
        second = self.executable(self.base / "second/node", "v24.21.0")
        self.executable(path_node, "v18.0.0")
        with patch.dict(os.environ, {"PATH": str(self.path) + os.pathsep + str(second.parent)}):
            self.assertEqual(environment.resolve_node(), second)

    def test_doctor_node_install_field_and_managed_detection(self):
        checks = {c["id"]: c for c in doctor.check_readiness(self.base)["checks"]}
        self.assertEqual(checks["node"]["status"], "missing")
        self.assertEqual(checks["node"]["install"], "node")
        self.assertTrue(all("install" in c for c in checks.values()))
        self.executable(self.tools / "node/bin/node")
        checks = {c["id"]: c for c in doctor.check_readiness(self.base)["checks"]}
        self.assertEqual(checks["node"]["status"], "ok")

    def test_sha_mismatch_and_missing_entry_refuse_before_writes(self):
        archive, sums = self.archive()
        for text in ("0" * 64 + "  " + archive.name, "", "a" * 64 + "  another.tar.gz"):
            sums.write_text(text)
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                setup.install_node_archive(archive, sums, "arm64")
            self.assertFalse(self.tools.exists())

    def test_valid_local_archive_installs_and_replaces_old_node(self):
        archive, sums = self.archive()
        self.executable(self.tools / "node/bin/node", "v18.0.0")
        setup.install_node_archive(archive, sums, "arm64")
        self.assertTrue(environment.node_qualified(self.tools / "node/bin/node"))
        self.assertEqual(sorted(p.name for p in self.tools.iterdir()), ["node"])

    def test_traversal_refused_and_previous_install_preserved(self):
        archive, sums = self.archive("../escape")
        old = self.executable(self.tools / "node/bin/node", "v18.0.0")
        before = old.read_bytes()
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            setup.install_node_archive(archive, sums, "arm64")
        self.assertEqual(old.read_bytes(), before)
        self.assertFalse((self.base / "escape").exists())

    def test_archive_escaping_symlink_refused(self):
        archive, sums = self.archive()
        top = f"node-v{setup.NODE_VERSION}-darwin-arm64"
        with tarfile.open(archive, "w:gz") as tar:
            link = tarfile.TarInfo(top + "/bin/npm")
            link.type = tarfile.SYMTYPE
            link.linkname = "../../../outside"
            tar.addfile(link)
        with self.assertRaisesRegex(ValueError, "escapes"):
            setup.safe_extract(archive, self.base / "extract", top)

    def test_yes_requires_exactly_one_known_item(self):
        for args in (["--yes"], ["--yes", "all"], ["--yes", "node", "--yes", "ego_browser"], ["--yes", "node", "ego_browser"], ["--check", "--yes", "node"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                setup.main(args)
            self.assertEqual(raised.exception.code, 2)

    def test_already_installed_skips_without_prompt_or_action(self):
        with patch.object(setup, "read_doctor", return_value=self.result()), patch.object(setup.platform, "system", return_value="Darwin"), patch.object(setup, "install") as install, patch("builtins.input", side_effect=AssertionError("No prompt expected")), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(setup.main(["--yes", "node"]), 0)
            install.assert_not_called()

    def test_decline_not_asked_twice_and_no_silent_dependencies(self):
        with patch.object(setup, "read_doctor", return_value=self.result(("node",))), patch.object(setup.platform, "system", return_value="Darwin"), patch.object(setup, "install") as install, patch("builtins.input", return_value="n") as prompt, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(setup.main([]), 0)
            self.assertEqual(prompt.call_count, 1)
            install.assert_not_called()
        with self.assertRaisesRegex(ValueError, "No implicit"):
            setup.install("console_dependencies", self.base)

    def test_yes_rechecks_and_only_installs_selected_item(self):
        before = self.result(("node", "ego_browser"))
        after = self.result(("ego_browser",))
        with patch.object(setup, "read_doctor", side_effect=[before, before, after, after]) as read, patch.object(setup.platform, "system", return_value="Darwin"), patch.object(setup, "install", return_value="installed") as install, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(setup.main(["--yes", "node"]), 0)
            install.assert_called_once_with("node", setup.ROOT)
            self.assertEqual(read.call_count, 4)

    def test_postcheck_failure_is_not_reported_as_success(self):
        with patch.object(setup, "read_doctor", return_value=self.result(("node",))), patch.object(setup.platform, "system", return_value="Darwin"), patch.object(setup, "install", return_value="installed"), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(setup.main(["--yes", "node"]), 1)

    def test_check_reuses_doctor_json_and_has_no_install_actions(self):
        result = self.result(("node",))
        result["ready"] = False
        with patch.object(setup, "read_doctor", return_value=result) as read, patch.object(setup, "install") as install, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(setup.main(["--check", "--lang", "en"]), 1)
            read.assert_called_once_with(setup.ROOT, "en")
            install.assert_not_called()
            self.assertIn("install=node", output.getvalue())

    def test_clt_waits_for_user_and_does_not_continue(self):
        result = self.result(("xcode_clt", "node"))
        with patch.object(setup, "read_doctor", return_value=result) as read, patch.object(setup.platform, "system", return_value="Darwin"), patch.object(setup, "install", return_value="pending-user") as install, patch("builtins.input", return_value="y"), contextlib.redirect_stdout(io.StringIO()):
            setup.main([])
            install.assert_called_once_with("xcode_clt", setup.ROOT)
            self.assertEqual(read.call_count, 2)  # No recheck after opening the dialog.

    def test_apps_skip_in_either_location(self):
        for directory in ("apps", "system-apps"):
            app = self.base / directory / "ego lite.app"
            app.mkdir(parents=True)
            self.assertEqual(environment.installed_app("ego_browser"), app)
            self.assertEqual(setup.install("ego_browser", self.base), "skipped")
            app.rmdir()

    def test_npm_ci_uses_selected_node_and_private_cache(self):
        node = self.executable(self.tools / "node/bin/node")
        self.executable(node.parent / "npm")
        console = self.base / "console"
        console.mkdir()
        (console / "package-lock.json").write_text('{"packages": {}}')
        with patch.object(setup, "resolve_node", return_value=node), patch.object(setup.subprocess, "run") as run:
            setup.install("console_dependencies", self.base)
            args, kwargs = run.call_args
            self.assertEqual(args[0][1], "ci")
            self.assertEqual(kwargs["cwd"], console)
            self.assertEqual(kwargs["env"]["PATH"].split(os.pathsep)[0], str(node.parent))
            self.assertIn(str(self.tools / "npm-cache"), args[0])

    def test_dmg_detaches_on_copy_failure(self):
        def fake_run(args, **kwargs):
            if args[1] == "attach":
                mount = Path(args[args.index("-mountpoint") + 1])
                (mount / "Jobflow.app").mkdir()
            if args[0] == "/usr/bin/ditto":
                raise subprocess.CalledProcessError(1, args)
            return subprocess.CompletedProcess(args, 0)
        with patch.object(setup.subprocess, "run", side_effect=fake_run) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                setup.install_dmg("menubar_app", self.base / "fake.dmg")
            self.assertEqual(run.call_args.args[0][1], "detach")
        self.assertFalse((self.base / "apps/Jobflow.app").exists())

    def test_launcher_resolves_tools_without_runtime_writes(self):
        node = self.executable(self.tools / "node/bin/node")
        with patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}):
            result = subprocess.run(["/bin/bash", str(BIN.parent / "local-control/start.sh"), "--resolve-node"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(node))
        self.assertFalse((self.base / "runtime").exists())


if __name__ == "__main__":
    unittest.main()
