import json, os, subprocess, sys, tempfile, threading, unittest
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
SCRIPT = Path(__file__).parent.parent / "scripts" / "exam_dates.py"
KEY = "sekrit-test-key-123"
ITEMS = [
    {"course_label": "MAT 19A", "title": "Syllabus Quiz", "due_date": "2026-09-30", "type": "quiz"},
    {"course_label": "MAT 19A", "title": "Midterm 1", "due_date": "2026-10-16", "type": "exam"},
    {"course_label": "MAT 19A", "title": "Midterm 2", "due_date": "2026-11-06", "type": "exam"},
    {"course_label": "MAT 19A", "title": "Final Exam", "due_date": "2026-12-09", "type": "exam"},
    {"course_label": "CHE 2A", "title": "Midterm 1", "due_date": "2026-10-01", "type": "exam"},
]


class PickTest(unittest.TestCase):
    def test_next_midterm_skips_quiz_and_other_class(self):
        from exam_dates import pick
        r = pick(ITEMS, "mat-19a", date(2026, 9, 24))
        self.assertEqual(r["next"]["title"], "Midterm 1")
        self.assertIsNone(r["previous"])

    def test_previous_exam_between(self):
        from exam_dates import pick
        r = pick(ITEMS, "mat-19a", date(2026, 10, 20))
        self.assertEqual((r["previous"]["title"], r["next"]["title"]), ("Midterm 1", "Midterm 2"))

    def test_exam_today_is_next(self):
        from exam_dates import pick
        self.assertEqual(pick(ITEMS, "mat-19a", date(2026, 12, 9))["next"]["title"], "Final Exam")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        ok = self.headers.get("x-app-key") == KEY
        self.send_response(200 if ok else 401)
        self.end_headers()
        self.wfile.write(json.dumps({"deadlines": ITEMS} if ok else {"detail": "bad key"}).encode())

    def log_message(self, *a):
        pass


class CliTest(unittest.TestCase):
    def run_cli(self, key):
        srv = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        kf = Path(tempfile.mkdtemp()) / ".app-key"
        kf.write_text(key + "\n")
        env = {**os.environ, "EXAM_API_URL": f"http://127.0.0.1:{srv.server_port}/api/deadlines",
               "EXAM_KEY_FILE": str(kf), "EXAM_TODAY": "2026-09-24"}
        r = subprocess.run([sys.executable, SCRIPT, "mat-19a"], capture_output=True, text=True, env=env)
        srv.shutdown()
        return r

    def test_prints_next_exam_and_never_the_key(self):
        r = self.run_cli(KEY)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["next"]["due_date"], "2026-10-16")
        self.assertNotIn(KEY, r.stdout + r.stderr)

    def test_401_explains_drift_without_leaking_key(self):
        r = self.run_cli("wrong-key-456")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("401", r.stderr)
        self.assertNotIn("wrong-key-456", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
