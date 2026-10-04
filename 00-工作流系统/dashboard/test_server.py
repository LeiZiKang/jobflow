import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("server.py")
SPEC = importlib.util.spec_from_file_location("jobflow_dashboard", SCRIPT)
assert SPEC and SPEC.loader
dashboard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dashboard)


class DashboardTests(unittest.TestCase):
    def make_repo(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        state = root / dashboard.SYSTEM_DIR / "state"
        state.mkdir(parents=True)
        reports = root / dashboard.REPORTS_DIR
        reports.mkdir()
        docs = {
            "current.json": {"metrics": {"diagnostic_sample_target": 15}, "known_blockers": []},
            "applications.json": {"applications": []},
            "candidates.json": {"candidates": []},
            "task_queue.json": {"tasks": []},
            "recurring_jobs.json": {
                "jobs": [
                    {
                        "title": "每日 inbound 巡检",
                        "enabled": False,
                        "disabled_reason": "fixture paused",
                        "trigger": {"runtime_status": "disabled_confirmed"},
                        "last_run": {"status": "blocked", "blocker": "old blocker"},
                    }
                ]
            },
            "active_decider.json": {"status": "unclaimed"},
        }
        for name, value in docs.items():
            (state / name).write_text(json.dumps(value), encoding="utf-8")
        return root

    def test_disabled_job_is_not_presented_as_running(self):
        root = self.make_repo()
        original = dashboard.REPO
        dashboard.REPO = dashboard.Repo(root)
        self.addCleanup(setattr, dashboard, "REPO", original)
        body = dashboard.render_overview().decode("utf-8")
        self.assertIn("已关闭", body)
        self.assertIn("外部触发器已确认停用", body)
        self.assertIn("fixture paused", body)

    def test_bad_state_is_loud(self):
        root = self.make_repo()
        path = root / dashboard.SYSTEM_DIR / "state" / "current.json"
        path.write_text("not json", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "JSON 损坏"):
            dashboard.Repo(root).load("current.json")

    def test_enabled_daily_job_shows_local_schedule(self):
        root = self.make_repo()
        path = root / dashboard.SYSTEM_DIR / "state" / "recurring_jobs.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["jobs"].append(
            {
                "title": "每日岗位增量检索",
                "enabled": True,
                "trigger": {"runtime_status": "enabled_confirmed"},
                "schedule": {"local_time": "09:30", "timezone": "Asia/Shanghai"},
                "next_due": "2026-09-03",
                "last_run": None,
            }
        )
        path.write_text(json.dumps(doc), encoding="utf-8")
        original = dashboard.REPO
        dashboard.REPO = dashboard.Repo(root)
        self.addCleanup(setattr, dashboard, "REPO", original)
        body = dashboard.render_overview().decode("utf-8")
        self.assertIn("每日岗位增量检索", body)
        self.assertIn("每天 09:30 Asia/Shanghai", body)
        self.assertIn("已开启", body)

    def test_report_path_rejects_traversal_and_non_html(self):
        root = self.make_repo()
        allowed = root / dashboard.REPORTS_DIR / "ok.html"
        allowed.write_text("<p>ok</p>", encoding="utf-8")
        outside = root / "secret.html"
        outside.write_text("no", encoding="utf-8")
        text_file = root / dashboard.REPORTS_DIR / "no.txt"
        text_file.write_text("no", encoding="utf-8")
        self.assertEqual(allowed.resolve(), dashboard.resolve_report_path(root, "05-检索报告/ok.html"))
        with self.assertRaises(ValueError):
            dashboard.resolve_report_path(root, "secret.html")
        with self.assertRaises(ValueError):
            dashboard.resolve_report_path(root, "05-检索报告/no.txt")

    def test_dashboard_defaults_to_explicit_chrome_command(self):
        self.assertEqual(
            ["open", "-a", "Google Chrome", "http://127.0.0.1:8787/"],
            dashboard.browser_open_command("chrome", "http://127.0.0.1:8787/"),
        )
        self.assertEqual(
            ["open", "http://127.0.0.1:8787/"],
            dashboard.browser_open_command("default", "http://127.0.0.1:8787/"),
        )
        self.assertIsNone(dashboard.browser_open_command("none", "http://127.0.0.1:8787/"))

    def test_application_links_and_case_path_are_id_bound(self):
        root = self.make_repo()
        state_path = root / dashboard.SYSTEM_DIR / "state" / "applications.json"
        applications = json.loads(state_path.read_text(encoding="utf-8"))
        app_id = "app-test-1"
        case_path = root / "04-面试" / "公司" / app_id / "index.html"
        case_path.parent.mkdir(parents=True)
        case_path.write_text("<h1>Case</h1>", encoding="utf-8")
        applications["applications"] = [
            {
                "application_id": app_id,
                "company": "Example",
                "role": "iOS",
                "status": "interviewing",
                "submitted_at": "2026-09-01",
                "case": {"view_path": f"04-面试/公司/{app_id}/index.html"},
            }
        ]
        state_path.write_text(json.dumps(applications), encoding="utf-8")
        original = dashboard.REPO
        dashboard.REPO = dashboard.Repo(root)
        self.addCleanup(setattr, dashboard, "REPO", original)
        body = dashboard.render_overview().decode("utf-8")
        self.assertIn(f"/application/{app_id}", body)
        self.assertEqual(
            case_path.resolve(),
            dashboard.resolve_case_path(root, f"04-面试/公司/{app_id}/index.html", app_id),
        )
        with self.assertRaises(ValueError):
            dashboard.resolve_case_path(root, f"04-面试/公司/{app_id}/index.html", "other-id")
        with self.assertRaises(ValueError):
            dashboard.resolve_case_path(root, f"04-面试/公司/{app_id}/index.html", "../escape")
        alias_id = "app-test-alias"
        alias = root / "04-面试" / "公司" / alias_id / "index.html"
        alias.parent.mkdir(parents=True)
        alias.symlink_to(case_path)
        with self.assertRaises(ValueError):
            dashboard.resolve_case_path(root, f"04-面试/公司/{alias_id}/index.html", alias_id)

    def test_overview_only_links_applications_with_cases(self):
        root = self.make_repo()
        state_path = root / dashboard.SYSTEM_DIR / "state" / "applications.json"
        state_path.write_text(
            json.dumps(
                {
                    "applications": [
                        {
                            "application_id": "app-without-case",
                            "company": "Plain Company",
                            "role": "iOS",
                            "status": "submitted_verified",
                            "submitted_at": "2026-09-01",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        original = dashboard.REPO
        dashboard.REPO = dashboard.Repo(root)
        self.addCleanup(setattr, dashboard, "REPO", original)
        body = dashboard.render_overview().decode("utf-8")
        self.assertIn("Plain Company", body)
        self.assertNotIn("/application/app-without-case", body)

    def test_document_route_resolver_is_allowlisted(self):
        root = self.make_repo()
        allowed = root / "04-面试" / "公司" / "case" / "note.md"
        allowed.parent.mkdir(parents=True)
        allowed.write_text("ok", encoding="utf-8")
        self.assertEqual(
            allowed.resolve(),
            dashboard.resolve_document_path(root, "04-面试/公司/case/note.md"),
        )
        bad = root / "04-面试" / "公司" / "case" / "secret.json"
        bad.write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            dashboard.resolve_document_path(root, "04-面试/公司/case/secret.json")
        with self.assertRaises(ValueError):
            dashboard.resolve_document_path(root, "../outside.md")

    def test_document_route_uses_deterministic_markdown_mime(self):
        root = self.make_repo()
        note = root / "04-面试" / "公司" / "case" / "中文记录.md"
        note.parent.mkdir(parents=True)
        note.write_text("面试记录", encoding="utf-8")
        original = dashboard.REPO
        dashboard.REPO = dashboard.Repo(root)
        self.addCleanup(setattr, dashboard, "REPO", original)

        class Capture:
            def _send(self, body, ctype="text/html; charset=utf-8", code=200, report=False):
                return body, ctype, code, report

        result = dashboard.Handler._serve_document(
            Capture(), "f=" + dashboard.quote("04-面试/公司/case/中文记录.md", safe="")
        )
        self.assertEqual("text/plain; charset=utf-8", result[1])
        self.assertEqual(200, result[2])
        self.assertEqual("面试记录".encode("utf-8"), result[0])

    def test_application_handler_returns_case_and_unknown_404(self):
        root = self.make_repo()
        app_id = "app-test-handler"
        case_path = root / "04-面试" / "公司" / app_id / "index.html"
        case_path.parent.mkdir(parents=True)
        case_path.write_text("<h1>Case</h1>", encoding="utf-8")
        state_path = root / dashboard.SYSTEM_DIR / "state" / "applications.json"
        state_path.write_text(
            json.dumps(
                {
                    "applications": [
                        {
                            "application_id": app_id,
                            "case": {"view_path": f"04-面试/公司/{app_id}/index.html"},
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        original = dashboard.REPO
        dashboard.REPO = dashboard.Repo(root)
        self.addCleanup(setattr, dashboard, "REPO", original)

        class Capture:
            def _send(self, body, ctype="text/html; charset=utf-8", code=200, report=False):
                return body, ctype, code, report

        ok = dashboard.Handler._serve_application(Capture(), app_id)
        missing = dashboard.Handler._serve_application(Capture(), "app-missing")
        self.assertEqual((b"<h1>Case</h1>", "text/html; charset=utf-8", 200, True), ok)
        self.assertEqual(404, missing[2])

    def test_report_response_has_strict_security_headers(self):
        class Capture:
            def __init__(self):
                self.status = None
                self.headers = {}
                self.wfile = io.BytesIO()

            def send_response(self, code):
                self.status = code

            def send_header(self, key, value):
                self.headers[key] = value

            def end_headers(self):
                return None

        capture = Capture()
        dashboard.Handler._send(capture, b"ok", report=True)
        self.assertEqual(200, capture.status)
        self.assertEqual("nosniff", capture.headers["X-Content-Type-Options"])
        self.assertEqual("no-store", capture.headers["Cache-Control"])
        self.assertIn("script-src 'none'", capture.headers["Content-Security-Policy"])


if __name__ == "__main__":
    unittest.main()
