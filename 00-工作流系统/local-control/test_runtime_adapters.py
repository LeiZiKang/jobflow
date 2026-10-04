from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


MODULE_PATH = Path(__file__).with_name("runtime_adapters.py")
SPEC = importlib.util.spec_from_file_location("runtime_adapters", MODULE_PATH)
assert SPEC and SPEC.loader
runtime_adapters = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime_adapters)


class RuntimeAdaptersTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_codex_command_is_read_only_and_prompt_is_not_in_argv(self) -> None:
        command = runtime_adapters.build_agent_command(
            "codex", self.repo, "search", "xhigh", executable="/usr/bin/codex"
        )

        self.assertEqual(command[:3], ["/usr/bin/codex", "--search", "exec"])
        self.assertIn("--json", command)
        self.assertIn("--strict-config", command)
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        self.assertEqual(command[command.index("--cd") + 1], str(self.repo.resolve()))
        self.assertIn('approval_policy="never"', command)
        self.assertIn('model_reasoning_effort="xhigh"', command)
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ephemeral", command)
        self.assertIn("--search", command)
        self.assertEqual(command[-1], "-")
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)

    def test_codex_non_search_role_does_not_enable_live_search(self) -> None:
        command = runtime_adapters.build_agent_command(
            "codex", self.repo, "auditor", executable="codex"
        )
        self.assertNotIn("--search", command)

    def test_claude_command_exposes_only_read_only_tools(self) -> None:
        command = runtime_adapters.build_agent_command(
            "claude", self.repo, "researcher", "max", executable="/usr/bin/claude"
        )

        self.assertEqual(command[0], "/usr/bin/claude")
        self.assertIn("--print", command)
        self.assertEqual(command[command.index("--output-format") + 1], "stream-json")
        self.assertEqual(command[command.index("--permission-mode") + 1], "dontAsk")
        self.assertIn("--safe-mode", command)
        tools = command[command.index("--tools") + 1].split(",")
        self.assertEqual(tools, ["Read", "Glob", "Grep", "WebSearch", "WebFetch"])
        self.assertTrue({"Edit", "Write", "Bash", "Task"}.isdisjoint(tools))
        self.assertNotIn("--dangerously-skip-permissions", command)

    def test_invalid_backend_role_and_effort_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            runtime_adapters.build_agent_command("other", self.repo, "search")
        with self.assertRaises(ValueError):
            runtime_adapters.build_agent_command("claude", self.repo, "bad role")
        with self.assertRaises(ValueError):
            runtime_adapters.build_agent_command("claude", self.repo, "search", "ultra")

    def test_parse_codex_jsonl_normalizes_session_message_and_usage(self) -> None:
        lines = [
            json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
            json.dumps({"type": "turn.started"}),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "final answer"},
                }
            ),
            json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10}}),
        ]

        result = runtime_adapters.parse_jsonl("codex", lines)

        self.assertEqual(result["session_id"], "thread-1")
        self.assertEqual(result["final_text"], "final answer")
        self.assertEqual(
            [event["type"] for event in result["events"]],
            ["session_started", "run_started", "assistant_message", "completed"],
        )
        self.assertEqual(result["events"][-1]["usage"], {"input_tokens": 10})

    def test_parse_claude_stream_json_prefers_result_text_and_omits_thinking(self) -> None:
        lines = [
            json.dumps(
                {"type": "system", "subtype": "init", "session_id": "session-1"}
            ),
            json.dumps(
                {
                    "type": "assistant",
                    "session_id": "session-1",
                    "message": {
                        "content": [
                            {"type": "thinking", "thinking": "private reasoning"},
                            {"type": "text", "text": "draft"},
                            {"type": "tool_use", "name": "Read", "input": {"file": "x"}},
                        ]
                    },
                }
            ),
            json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "session_id": "session-1",
                    "is_error": False,
                    "result": "final",
                    "usage": {"input_tokens": 20},
                }
            ),
        ]

        result = runtime_adapters.parse_jsonl("claude", lines)

        self.assertEqual(result["session_id"], "session-1")
        self.assertEqual(result["final_text"], "final")
        self.assertEqual(result["events"][1]["tools"], ["Read"])
        self.assertNotIn("private reasoning", repr(result))
        self.assertNotIn("\"file\": \"x\"", repr(result))

    def test_parse_jsonl_reports_non_json_without_losing_final_result(self) -> None:
        lines = [
            "provider warning",
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "still works"},
                }
            ),
        ]

        result = runtime_adapters.parse_jsonl("codex", lines)

        self.assertEqual(result["events"][0]["type"], "protocol_warning")
        self.assertEqual(result["final_text"], "still works")

    @mock.patch.object(runtime_adapters.subprocess, "run")
    @mock.patch.object(runtime_adapters.shutil, "which")
    def test_probe_backends_only_requests_versions(self, which, run) -> None:
        which.side_effect = lambda binary: f"/usr/bin/{binary}"
        run.side_effect = [
            SimpleNamespace(returncode=0, stdout="codex 1.2.3\n", stderr=""),
            SimpleNamespace(returncode=0, stdout="claude 4.5.6\n", stderr=""),
        ]

        result = runtime_adapters.probe_backends()

        self.assertEqual(result["codex"]["version"], "codex 1.2.3")
        self.assertEqual(result["claude"]["version"], "claude 4.5.6")
        self.assertTrue(all(item["available"] for item in result.values()))
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [["/usr/bin/codex", "--version"], ["/usr/bin/claude", "--version"]],
        )

    @mock.patch.object(runtime_adapters.shutil, "which", return_value=None)
    def test_run_agent_returns_unavailable_without_spawning(self, _which) -> None:
        with mock.patch.object(runtime_adapters.subprocess, "Popen") as popen:
            result = runtime_adapters.run_agent(
                "codex", "inspect status", self.repo, "auditor", "high"
            )

        self.assertEqual(result["status"], "unavailable")
        popen.assert_not_called()

    def test_run_agent_rejects_unbounded_timeout(self) -> None:
        with self.assertRaisesRegex(ValueError, "timeout_seconds"):
            runtime_adapters.run_agent(
                "codex",
                "inspect status",
                self.repo,
                "auditor",
                "high",
                timeout_seconds=0,
            )

    def test_sanitized_environment_excludes_api_credentials(self) -> None:
        with mock.patch.dict(
            runtime_adapters.os.environ,
            {
                "PATH": "/usr/bin",
                "HOME": "/tmp/home",
                "OPENAI_API_KEY": "secret",
                "ANTHROPIC_API_KEY": "secret",
                "AWS_SECRET_ACCESS_KEY": "secret",
                "AWS_PROFILE": "jobflow",
            },
            clear=True,
        ):
            environment = runtime_adapters._sanitized_environment()
        self.assertEqual(
            {"PATH": "/usr/bin", "HOME": "/tmp/home", "AWS_PROFILE": "jobflow"},
            environment,
        )

    def test_sanitized_environment_keeps_personal_directory_overrides(self) -> None:
        overrides = {
            "JOBFLOW_PROFILE_DIR": str(self.repo / "profile"),
            "JOBFLOW_RUNTIME_DIR": str(self.repo / "runtime"),
        }
        with mock.patch.dict(runtime_adapters.os.environ, overrides):
            environment = runtime_adapters._sanitized_environment()
        for key, value in overrides.items():
            self.assertEqual(environment[key], value)

    @mock.patch.object(runtime_adapters.shutil, "which", return_value="/usr/bin/codex")
    def test_run_agent_streams_normalized_events_with_mock_process(self, _which) -> None:
        stdout = io.StringIO(
            "\n".join(
                [
                    json.dumps({"type": "thread.started", "thread_id": "thread-2"}),
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {"type": "agent_message", "text": "done"},
                        }
                    ),
                    json.dumps({"type": "turn.completed"}),
                ]
            )
            + "\n"
        )

        class FakeProcess:
            def __init__(self) -> None:
                self.stdin = io.StringIO()
                self.stdout = stdout
                self.stderr = io.StringIO("")

            def wait(self) -> int:
                return 0

        observed = []
        with mock.patch.object(runtime_adapters.subprocess, "Popen", return_value=FakeProcess()):
            result = runtime_adapters.run_agent(
                "codex", "inspect status", self.repo, "auditor", "high", observed.append
            )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["session_id"], "thread-2")
        self.assertEqual(result["final_text"], "done")
        self.assertEqual(observed, result["events"])


if __name__ == "__main__":
    unittest.main()
