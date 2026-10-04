"""离线流程测试：所有编译、签名、公证和镜像工具均为桩，不访问钥匙串或网络。"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


BUILD = Path(__file__).with_name("build.sh")
IDENTITY = "Developer ID Application: <Name> (<TEAMID>)"
SUBMISSION = "00000000-0000-0000-0000-000000000001"
STUB = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ["CALLS"], "a") as f:
    f.write(json.dumps([name, *args]) + "\n")
def touch(path):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.touch()
if name in ("swiftc", "iconutil"):
    touch(args[args.index("-o") + 1])
elif name == "swift":
    touch(args[-1])
elif name == "lipo":
    touch(args[args.index("-output") + 1])
elif name == "sips":
    touch(args[args.index("--out") + 1])
elif name == "ditto":
    touch(args[-1])
elif name == "hdiutil":
    app = pathlib.Path(args[args.index("-srcfolder") + 1]) / "求职控制台.app"
    if os.environ.get("EXPECT_TICKET"):
        assert (app / "ticket").exists(), "DMG 必须包含已装订的 App"
    touch(args[-1])
elif name == "codesign" and "--sign" in args:
    if "Nonexistent" in args[args.index("--sign") + 1]:
        sys.exit(1)
elif name == "xcrun":
    if args[:2] == ["notarytool", "submit"]:
        is_dmg = args[2].endswith(".dmg")
        status = os.environ.get("DMG_STATUS" if is_dmg else "APP_STATUS", "Accepted")
        if status == "TransportError":
            print("private server error", file=sys.stderr)
            sys.exit(1)
        print(json.dumps({"id": "00000000-0000-0000-0000-000000000001", "status": status}))
    elif args[:2] == ["stapler", "staple"]:
        if args[-1].endswith(".app"):
            touch(pathlib.Path(args[-1]) / "ticket")
    elif args[:2] != ["stapler", "validate"]:
        sys.exit("unexpected xcrun invocation")
elif name == "spctl" and os.environ.get("FAIL_SPCTL"):
    sys.exit(1)
'''


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jobflow-build-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for tool in ("swiftc", "swift", "lipo", "sips", "iconutil", "codesign",
                     "hdiutil", "ditto", "xcrun", "spctl"):
            path = self.bin / tool
            path.write_text(STUB)
            path.chmod(0o755)
        self.calls = self.root / "calls.jsonl"
        self.output = self.root / "output with spaces" / "Jobflow.dmg"
        self.env = {k: v for k, v in os.environ.items()
                    if k not in ("JOBFLOW_SIGN_IDENTITY", "JOBFLOW_NOTARY_PROFILE")}
        self.env.update(PATH=f"{self.bin}:/usr/bin:/bin:/usr/sbin:/sbin",
                        TMPDIR=str(self.root), CALLS=str(self.calls))

    def run_build(self, notarize=False, **env):
        args = ["/bin/bash", str(BUILD), "--dmg", str(self.output)]
        if notarize:
            args.append("--notarize")
        return subprocess.run(args, env={**self.env, **env}, text=True,
                              capture_output=True, timeout=30)

    def read_calls(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()]

    def signed(self, **env):
        return self.run_build(True, JOBFLOW_SIGN_IDENTITY=IDENTITY,
                              JOBFLOW_NOTARY_PROFILE="<PROFILE WITH SPACES>", **env)

    def test_adhoc_does_not_use_notary_or_gatekeeper(self):
        result = self.run_build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.output.exists())
        calls = self.read_calls()
        self.assertFalse(any(c[0] in ("xcrun", "spctl") for c in calls))
        signatures = [c for c in calls if c[0] == "codesign" and "--sign" in c]
        self.assertEqual(len(signatures), 1)
        self.assertEqual(signatures[0][1:4], ["--force", "--sign", "-"])

    def test_signed_without_notarization(self):
        result = self.run_build(JOBFLOW_SIGN_IDENTITY=IDENTITY)
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.read_calls()
        self.assertFalse(any(c[0] in ("xcrun", "spctl") for c in calls))
        signatures = [c for c in calls if c[0] == "codesign" and "--sign" in c]
        self.assertEqual(len(signatures), 3)
        self.assertTrue(signatures[0][-1].endswith("Contents/MacOS/JobflowMenu"))
        self.assertTrue(signatures[1][-1].endswith(".app"))
        self.assertTrue(signatures[2][-1].endswith(".dmg"))
        for c in signatures:
            self.assertIn("--timestamp", c)
            self.assertEqual(c[c.index("--sign") + 1], IDENTITY)
            self.assertNotIn("--deep", c)
        for c in signatures[:2]:
            self.assertEqual(c[c.index("--options") + 1], "runtime")

    def test_notarized_app_is_stapled_before_packaging(self):
        result = self.signed(EXPECT_TICKET="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.read_calls()
        submits = [c for c in calls if c[:3] == ["xcrun", "notarytool", "submit"]]
        self.assertEqual([Path(c[3]).suffix for c in submits], [".zip", ".dmg"])
        for c in submits:
            self.assertIn("--wait", c)
            self.assertEqual(c[c.index("--keychain-profile") + 1], "<PROFILE WITH SPACES>")
        validations = [c for c in calls if c[:3] == ["xcrun", "stapler", "validate"]]
        self.assertEqual([Path(c[-1]).suffix for c in validations], [".app", ".dmg"])
        self.assertEqual(len([c for c in calls if c[0] == "spctl"]), 2)
        self.assertTrue(self.output.exists())

    def test_missing_configuration_fails_before_tools(self):
        result = self.run_build(True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("JOBFLOW_NOTARY_PROFILE", result.stderr)
        result = self.run_build(True, JOBFLOW_NOTARY_PROFILE="<PROFILE>")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("JOBFLOW_SIGN_IDENTITY", result.stderr)
        self.assertFalse(self.calls.exists())

    def test_unknown_identity_fails_without_adhoc_fallback(self):
        result = self.run_build(JOBFLOW_SIGN_IDENTITY="Developer ID Application: Nonexistent")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Developer ID 签名失败", result.stderr)
        self.assertFalse(self.output.exists())
        self.assertFalse(any(c[0] == "hdiutil" for c in self.read_calls()))

    def test_nonaccepted_status_does_not_staple_or_publish(self):
        for status in ("Invalid", "Rejected", "In Progress"):
            with self.subTest(status=status):
                self.calls.unlink(missing_ok=True)
                result = self.signed(APP_STATUS=status)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"notarytool log {SUBMISSION}", result.stderr)
                self.assertFalse(self.output.exists())
                self.assertFalse(any(c[:2] == ["xcrun", "stapler"] for c in self.read_calls()))

    def test_transport_failure_has_recovery_command_without_raw_error(self):
        result = self.signed(APP_STATUS="TransportError")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("notarytool history", result.stderr)
        self.assertIn("notarytool log", result.stderr)
        self.assertNotIn("private server error", result.stderr)
        self.assertFalse(self.output.exists())

    def test_failed_final_assessment_preserves_previous_output(self):
        self.output.parent.mkdir()
        self.output.write_text("previous release")
        for env in ({"DMG_STATUS": "Invalid"}, {"FAIL_SPCTL": "1"}):
            with self.subTest(env=env):
                result = self.signed(**env)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.output.read_text(), "previous release")


if __name__ == "__main__":
    unittest.main()
