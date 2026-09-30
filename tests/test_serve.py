import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # code lives one folder up
import json, os, tempfile, threading, time, unittest, urllib.error, urllib.request
from unittest import mock
from pathlib import Path

import serve


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


class ServeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = root = Path(tempfile.mkdtemp())
        for rel in ["site/index.html", "wiki/index.md", "studio/mat-19a/index.html", "raw/mat-19a/2026-09-24-lecture.md",
                    ".models/secret.bin", "CLAUDE.md"]:
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(rel)
        (root / "wiki/mat-19a").mkdir()
        (root / "wiki/mat-19a/limits.md").write_text("# Limits\n\nbody")
        (root / "raw/mat-19a/hw1.md").write_text("# Homework 1\n\nFind the Derivative of x^2.")
        (root / "raw/mat-19a/files").mkdir()
        (root / "raw/mat-19a/files/hw1.pdf").write_bytes(b"%PDF")
        (root / "classes.json").write_text('[{"slug": "mat-19a", "name": "MAT 19A"}]')
        serve.INGEST = ["sh", "-c", 'echo "$0" >> ran.txt']  # stand-in for ingest.sh <class>
        serve.STUDY = ["sh", "-c", 'echo "$0 $1 $2" >> made.txt']  # stand-in for study.sh <class> <kind> <topic>
        cls.srv = serve.make_server(root, 0)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.open = urllib.request.build_opener(NoRedirect).open

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def req(self, path, body=None, headers=None, method=None):
        h = {"X-Class-Wiki": "1", **(headers or {})}
        data = body if isinstance(body, bytes) or body is None else json.dumps(body).encode()
        try:
            r = self.open(urllib.request.Request(self.base + path, data=data, headers=h, method=method))
            return r.status, r.headers, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read().decode()

    def get(self, path):
        return self.req(path)

    def ran(self, name="ran.txt"):
        f = self.root / name
        for _ in range(50):
            if f.exists():
                return f.read_text().split()
            time.sleep(0.05)
        return []

    # --- reading
    def test_root_is_viewer(self):
        self.assertEqual(self.get("/")[2], "site/index.html")

    def test_raw_markdown_for_viewer(self):
        self.assertEqual(self.get("/wiki/mat-19a/limits.md?raw=1")[2], "# Limits\n\nbody")

    def test_plain_md_link_redirects_into_viewer(self):
        code, headers, _ = self.get("/wiki/mat-19a/limits.md")
        self.assertEqual((code, headers["Location"]), (302, "/#/wiki/mat-19a/limits.md"))

    def test_private_files_hidden(self):
        for p in ["/.models/secret.bin", "/CLAUDE.md?raw=1", "/serve.py", "/wiki/../CLAUDE.md?raw=1", "/classes.json",
                  "/inbox/mat-19a/x"]:
            self.assertEqual(self.get(p)[0], 404, p)

    def test_localhost_only(self):
        self.assertEqual(self.srv.server_address[0], "127.0.0.1")
        self.assertEqual(self.req("/", headers={"Host": "evil.example:4323"})[0], 403)  # DNS rebinding

    def test_own_tailnet_name_allowed(self):  # phone via `tailscale serve`; other tailnets still blocked
        with mock.patch.object(serve, "HOSTS", {"localhost", "127.0.0.1", "mac.tail1.ts.net"}):
            self.assertEqual(self.req("/", headers={"Host": "mac.tail1.ts.net:4323"})[0], 200)
            self.assertEqual(self.req("/", headers={"Host": "evil.tail9.ts.net"})[0], 403)

    def test_tailnet_name_from_cli(self):
        out = json.dumps({"Self": {"DNSName": "mac.tail1.ts.net."}})
        with mock.patch.object(serve.subprocess, "run", return_value=mock.Mock(returncode=0, stdout=out)):
            self.assertEqual(serve.tailnet_name(), {"mac.tail1.ts.net"})
        with mock.patch.object(serve.subprocess, "run", side_effect=FileNotFoundError):
            self.assertEqual(serve.tailnet_name(), set())

    def test_class_detail(self):
        d = json.loads(self.get("/api/class/mat-19a")[2])
        self.assertEqual(d["name"], "MAT 19A")
        self.assertEqual(d["pages"], [{"path": "wiki/mat-19a/limits.md", "title": "Limits", "raw": [], "tested": 0}])
        self.assertTrue(d["studio"])
        self.assertEqual(self.get("/api/class/nope")[0], 404)

    def test_outputs_listed_by_kind_with_titles(self):  # the Study tab: one item per output, PDF beside its slides
        st = self.root / "studio/mat-19a"
        (st / "quizzes").mkdir(parents=True, exist_ok=True); (st / "slides").mkdir(exist_ok=True)
        (st / "quizzes/q1.html").write_text("<title>Limits quiz</title>")
        (st / "slides/s1.html").write_text("<title>Deck</title>"); (st / "slides/s1.pdf").write_bytes(b"%PDF")
        (st / "slides/s1.md").write_text("# notes")
        got = {o["kind"]: o for o in json.loads(self.get("/api/class/mat-19a")[2])["outputs"]}
        self.assertEqual(got["quizzes"]["title"], "Limits quiz")
        self.assertEqual(got["quizzes"]["path"], "studio/mat-19a/quizzes/q1.html")
        self.assertEqual([x["label"] for x in got["slides"]["also"]], ["PDF", "Text"])

    def test_quiz_run_score_shown_on_card(self):  # the Study card shows "7/10"
        out = "studio/mat-19a/quizzes/q1.html"
        (self.root / out).parent.mkdir(parents=True, exist_ok=True); (self.root / out).write_text("<title>Q</title>")
        run = {"out": "/" + out, "right": 7, "done": 10, "of": 10}
        self.assertEqual(self.req("/api/score", {"class": "mat-19a", "source": "wiki/mat-19a/runs.md", "ok": True, "run": run})[0], 200)
        self.assertEqual(json.loads(self.get("/api/class/mat-19a")[2])["results"][out], {"right": 7, "done": 10, "of": 10})
        bad = dict(run, out="/studio/other/x.html")
        self.req("/api/score", {"class": "mat-19a", "source": "wiki/mat-19a/runs.md", "ok": True, "run": bad})
        self.assertNotIn("studio/other/x.html", json.loads(self.get("/api/class/mat-19a")[2])["results"])

    def test_delete_moves_to_trash_and_tidies(self):
        r = self.root
        for rel, text in {"studio/mat-19a/cards/d1.html": "<title>D</title>", "studio/mat-19a/cards/d1.json": "{}",
                          "raw/mat-19a/tmp-src.md": "# Tmp", "raw/mat-19a/files/tmp-src.pdf": "%PDF",
                          "wiki/mat-19a/tmp-page.md": "# Tmp page"}.items():
            (r / rel).parent.mkdir(parents=True, exist_ok=True); (r / rel).write_text(text)
        (r / "wiki/index.md").write_text("| [Tmp page](mat-19a/tmp-page.md) | s | d |\n| [Keep](mat-19a/limits.md) | s | d |\n")
        for rel in ["studio/mat-19a/cards/d1.html", "raw/mat-19a/tmp-src.md", "wiki/mat-19a/tmp-page.md"]:
            self.assertEqual(self.req("/api/delete", {"class": "mat-19a", "path": rel})[0], 200, rel)
        for rel in ["studio/mat-19a/cards/d1.html", "studio/mat-19a/cards/d1.json", "raw/mat-19a/tmp-src.md",
                    "raw/mat-19a/files/tmp-src.pdf", "wiki/mat-19a/tmp-page.md"]:
            self.assertFalse((r / rel).exists(), rel)
        self.assertTrue(list((r / ".trash").rglob("tmp-src.pdf")))  # kept, not erased
        self.assertEqual((r / "wiki/index.md").read_text(), "| [Keep](mat-19a/limits.md) | s | d |\n")

    def test_delete_refuses_other_paths(self):
        for rel in ["wiki/index.md", "wiki/mat-19a/../../CLAUDE.md", "../x.md", "serve.py", "wiki/other/x.md", "studio/mat-19a/index.html"]:
            self.assertEqual(self.req("/api/delete", {"class": "mat-19a", "path": rel})[0], 400, rel)
        self.assertEqual(self.req("/api/delete", {"class": "nope", "path": "wiki/nope/x.md"})[0], 404)
        self.assertTrue((self.root / "wiki/mat-19a/limits.md").exists())

    def test_sources_one_row_each_with_title_and_original(self):
        d = json.loads(self.get("/api/class/mat-19a")[2])
        self.assertEqual(d["sources"], [
            {"path": "raw/mat-19a/2026-09-24-lecture.md", "title": "2026-09-24-lecture", "original": None},
            {"path": "raw/mat-19a/hw1.md", "title": "Homework 1", "original": "raw/mat-19a/files/hw1.pdf"}])

    def test_search_sources_by_text(self):
        hits = json.loads(self.get("/api/search?class=mat-19a&q=derivative")[2])
        self.assertEqual([h["title"] for h in hits], ["Homework 1"])
        self.assertIn("Derivative of x^2", hits[0]["snippet"])
        self.assertEqual(json.loads(self.get("/api/search?class=mat-19a&q=zzz")[2]), [])
        self.assertEqual(self.get("/api/search?class=nope&q=a")[0], 404)

    def test_search_wiki_across_all_classes(self):  # the home page search box: no class given
        hits = json.loads(self.get("/api/search?q=body&in=wiki")[2])
        self.assertEqual([(h["class"], h["title"]) for h in hits], [("MAT 19A", "Limits")])
        self.assertEqual(json.loads(self.get("/api/search?q=zzz&in=wiki")[2]), [])

    def test_search_wiki_pages_by_text(self):
        hits = json.loads(self.get("/api/search?class=mat-19a&q=body&in=wiki")[2])
        self.assertEqual([(h["path"], h["title"]) for h in hits[:1]], [("wiki/mat-19a/limits.md", "Limits")])

    # --- writing
    def test_add_class(self):
        code, _, body = self.req("/api/classes", {"name": "Chem 2A: Intro!"})
        self.assertEqual((code, json.loads(body)), (200, {"slug": "chem-2a-intro"}))
        for d in ["wiki", "raw", "studio", "inbox"]:
            self.assertTrue((self.root / d / "chem-2a-intro").is_dir(), d)
        names = [c["name"] for c in json.loads(self.get("/api/classes")[2])]
        self.assertEqual(names, ["MAT 19A", "Chem 2A: Intro!"])
        self.assertEqual(self.req("/api/classes", {"name": "chem 2a intro"})[0], 409)
        self.assertEqual(self.req("/api/classes", {"name": "  !! "})[0], 400)

    def test_upload_then_auto_ingest(self):
        code, _, body = self.req("/api/upload?class=mat-19a&name=IMG%201%20(2).HEIC", b"photo-bytes")
        self.assertEqual(code, 200, body)
        self.assertEqual((self.root / "inbox/mat-19a/IMG-1-2-.HEIC").read_bytes(), b"photo-bytes")
        self.assertEqual(self.ran(), ["mat-19a"])
        self.assertEqual(self.req("/api/upload?class=mat-19a&name=x.pdf", b"again")[0], 200)
        self.assertEqual(self.req("/api/upload?class=mat-19a&name=x.pdf", b"again")[0], 200)
        pending = json.loads(self.get("/api/class/mat-19a")[2])["pending"]
        self.assertTrue({"x.pdf", "x-1.pdf"} <= set(pending), pending)  # same name twice: no overwrite

    def test_upload_rejects(self):
        code, _, body = self.req("/api/upload?class=mat-19a&name=a.exe", b"x")
        self.assertEqual((code, json.loads(body)), (400, {"error": "Only PDF, photo, .txt or .md files"}))
        self.assertEqual(self.req("/api/upload?class=nope&name=a.pdf", b"x")[0], 404)
        self.assertEqual(self.req("/api/upload?class=../wiki&name=a.pdf", b"x")[0], 404)
        self.assertEqual(self.req("/api/upload?class=mat-19a&name=a.pdf", b"x", {"X-Class-Wiki": ""})[0], 403)  # CSRF

    def test_retry_failed(self):
        (self.root / "inbox/mat-19a/failed").mkdir(parents=True, exist_ok=True)
        (self.root / "inbox/mat-19a/failed/old.url").write_text("u")
        self.assertEqual(self.req("/api/retry", {"class": "mat-19a"})[0], 200)
        self.assertTrue((self.root / "inbox/mat-19a/old.url").exists())
        self.assertIn("mat-19a", self.ran())

    def test_youtube_link(self):
        self.assertEqual(self.req("/api/link", {"class": "mat-19a", "url": "https://www.youtube.com/watch?v=abc"})[0], 200)
        [f] = (self.root / "inbox/mat-19a").glob("*-youtube.url")
        self.assertEqual(f.read_text(), "https://www.youtube.com/watch?v=abc")
        for bad in ["https://evil.com/watch?v=abc", "file:///etc/passwd", "https://youtube.com.evil.com/x", "--exec=x"]:
            self.assertEqual(self.req("/api/link", {"class": "mat-19a", "url": bad})[0], 400, bad)

    def test_google_doc_link(self):
        doc = "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/edit?usp=sharing"
        self.assertEqual(self.req("/api/link", {"class": "mat-19a", "url": doc})[0], 200)
        [f] = (self.root / "inbox/mat-19a").glob("*-gdoc.url")
        self.assertEqual(f.read_text(), doc)
        self.assertEqual(self.ran(), ["mat-19a"])
        (self.root / "ran.txt").unlink()  # test_upload_then_auto_ingest counts runs from zero
        for bad in ["https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit",
                    "https://docs.google.com.evil.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit"]:
            self.assertEqual(self.req("/api/link", {"class": "mat-19a", "url": bad})[0], 400, bad)

    def test_make_study_output(self):
        code, _, body = self.req("/api/study", {"class": "mat-19a", "kind": "cards", "topic": "limits"})
        self.assertEqual(code, 200, body)
        self.assertEqual(self.ran("made.txt"), ["mat-19a", "cards", "limits"])  # study.sh <class> <kind> <topic>
        self.assertEqual(self.req("/api/study", {"class": "mat-19a", "kind": "rm -rf"})[0], 400)
        self.assertEqual(self.req("/api/study", {"class": "nope", "kind": "quiz"})[0], 404)

    def test_cancel_study_output(self):
        old, serve.STUDY = serve.STUDY, ["sh", "-c", 'echo start >> slow.txt; sleep 5; echo end >> slow.txt']
        try:
            self.req("/api/study", {"class": "mat-19a", "kind": "audio"})
            self.req("/api/study", {"class": "mat-19a", "kind": "video"})
            self.assertEqual(self.ran("slow.txt"), ["start"])  # audio running, video waiting
            making = lambda: json.loads(self.get("/api/class/mat-19a")[2])["making"]
            self.assertEqual(making(), ["audio", "video"])
            self.assertEqual(self.req("/api/cancel", {"class": "mat-19a", "kind": "video"})[0], 200)  # waiting: dropped
            self.assertEqual(self.req("/api/cancel", {"class": "mat-19a", "kind": "audio"})[0], 200)  # running: stopped
            for _ in range(50):
                if not making():
                    break
                time.sleep(0.05)
            self.assertEqual(making(), [])
            time.sleep(5.5)
            self.assertEqual(self.ran("slow.txt"), ["start"])  # killed before "end"; video never started
        finally:
            serve.STUDY = old

    def test_quiz_scores_saved_per_page(self):
        for ok in [True, False, False]:
            self.assertEqual(self.req("/api/score", {"class": "mat-19a", "source": "wiki/mat-19a/limits.md", "ok": ok})[0], 200)
        self.assertEqual(self.req("/api/score", {"class": "mat-19a", "source": "../x", "ok": True})[0], 400)
        scores = json.loads((self.root / "studio/mat-19a/scores.json").read_text())
        self.assertEqual(scores["wiki/mat-19a/limits.md"], {"right": 1, "total": 3})
        self.assertEqual(json.loads(self.get("/api/class/mat-19a")[2])["weak"][0]["path"], "wiki/mat-19a/limits.md")

    def test_missed_questions_list(self):  # a wrong answer is kept until a later right answer
        miss = {"class": "mat-19a", "source": "wiki/mat-19a/missed.md", "q": "Slope of 25m − 900?", "answer": "25",
                "text": "900", "section": "Slope"}
        self.req("/api/score", {**miss, "ok": False})
        f = self.root / "studio/mat-19a/missed.json"
        self.assertEqual(json.loads(f.read_text())["Slope of 25m − 900?"]["text"], "900")
        self.req("/api/score", {**miss, "ok": True})
        self.assertNotIn("Slope of 25m − 900?", json.loads(f.read_text()))

    def plan(self, items):  # what the planner sent us: kept in a cache file so a page load never waits on Render
        from datetime import date, timedelta
        d = lambda n: (date.today() + timedelta(days=n)).isoformat()
        (self.root / ".planner-cache.json").write_text(json.dumps({"at": time.time(), "deadlines": [
            {"course_label": lab, "title": t, "type": ty, "weight_pct": w, "due_date": d(n)} for lab, t, ty, w, n in items]}))

    def test_syllabus_comes_from_planner_by_class_name(self):
        self.plan([("MAT 19A", "Midterm 2", "exam", None, 20), ("MAT 19A", "Midterm 1", "exam", 15, 5),
                   ("MAT 19A", "Old quiz", "quiz", None, -3), ("PSC 001", "Unit 1 Test", "exam", 14, 2)])
        d = json.loads(self.get("/api/class/mat-19a")[2])
        self.assertEqual([i["title"] for i in d["coming"]], ["Midterm 1", "Midterm 2"])  # by date, past and other classes dropped
        self.assertEqual(d["coming"][0]["days"], 5)
        self.assertEqual(d["focus"]["title"], "Midterm 1")  # biggest weight inside 14 days
        card = next(c for c in json.loads(self.get("/api/classes")[2]) if c["slug"] == "mat-19a")
        self.assertEqual((card["next"]["title"], card["next"]["days"]), ("Midterm 1", 5))

    def test_focus_needs_weight_or_an_exam(self):
        self.plan([("MAT 19A", "Pre-lab quiz", "quiz", None, 2)])
        self.assertIsNone(json.loads(self.get("/api/class/mat-19a")[2])["focus"])  # a quiz with no weight is not "first"
        self.plan([("MAT 19A", "Pre-lab quiz", "quiz", None, 2), ("MAT 19A", "Midterm", "exam", None, 9)])
        self.assertEqual(json.loads(self.get("/api/class/mat-19a")[2])["focus"]["title"], "Midterm")

    def test_calendar_has_every_class_past_and_future(self):
        self.plan([("MAT 19A", "Midterm 1", "exam", 15, 5), ("MAT 19A", "Old quiz", "quiz", None, -3),
                   ("PSC 001", "Unit 1 Test", "exam", 14, 2), ("ZZZ 999", "Not mine", "exam", None, 1)])
        rows = json.loads(self.get("/api/calendar")[2])
        self.assertEqual(sorted(r["title"] for r in rows), ["Midterm 1", "Old quiz"])  # only classes on the site (PSC has no folder here)
        self.assertEqual({(r["class"], r["idx"]) for r in rows}, {("mat-19a", 0)})
        self.assertEqual(next(r for r in rows if r["title"] == "Old quiz")["days"], -3)

    def test_syllabus_missing_is_quiet(self):
        (self.root / ".planner-cache.json").unlink(missing_ok=True)
        d = json.loads(self.get("/api/class/mat-19a")[2])
        self.assertEqual((d["coming"], d["focus"]), ([], None))

    def test_chat_knows_the_syllabus(self):
        self.plan([("MAT 19A", "Midterm 1", "exam", 15, 5)])
        old, serve.CLAUDE = serve.CLAUDE, ["cat"]
        try:
            answer = json.loads(self.req("/api/chat", {"class": "mat-19a", "messages": [{"role": "user", "text": "what now?"}]})[2])["answer"]
        finally:
            serve.CLAUDE = old
        self.assertIn("Midterm 1", answer)
        self.assertIn("weight 15%", answer)

    def test_chat_uses_plan_not_api_key(self):
        old, serve.CLAUDE = serve.CLAUDE, ["sh", "-c", 'echo "key=${ANTHROPIC_API_KEY:-none}"; cat']  # stand-in: echo env + prompt
        os.environ["ANTHROPIC_API_KEY"] = "sk-fake"
        try:
            code, _, body = self.req("/api/chat", {"class": "mat-19a", "messages": [{"role": "user", "text": "What is a limit?"}]})
            self.assertEqual(code, 200, body)
            answer = json.loads(body)["answer"]
            self.assertIn("key=none", answer)  # an API key would bill per question; the plan does not
            self.assertIn("# Limits", answer)  # the class wiki is in the prompt
            self.assertIn("What is a limit?", answer)
            self.assertEqual(self.req("/api/chat", {"class": "nope", "messages": [{"role": "user", "text": "x"}]})[0], 404)
            self.assertEqual(self.req("/api/chat", {"class": "mat-19a", "messages": []})[0], 400)
        finally:
            serve.CLAUDE = old
            del os.environ["ANTHROPIC_API_KEY"]

    def fake_claude(self, out):
        old, serve.CLAUDE = serve.CLAUDE, ["sh", "-c", f"cat > /dev/null; printf '{out}'"]
        self.addCleanup(setattr, serve, "CLAUDE", old)

    def test_grade_typed_answer_and_recall(self):
        self.fake_claude("VERDICT: right\\nGood, you named both parts.")
        code, _, body = self.req("/api/grade", {"class": "mat-19a", "source": "wiki/mat-19a/limits.md", "kind": "answer",
                                                "question": "q", "answer": "a", "text": "my try"})
        self.assertEqual((code, json.loads(body)), (200, {"ok": True, "feedback": "Good, you named both parts."}))
        self.fake_claude("VERDICT: wrong\\nYou missed the definition.")
        d = json.loads(self.req("/api/grade", {"class": "mat-19a", "source": "wiki/mat-19a/limits.md", "kind": "recall", "text": "x"})[2])
        self.assertFalse(d["ok"])
        self.assertEqual(self.req("/api/grade", {"class": "mat-19a", "source": "../CLAUDE.md", "kind": "recall", "text": "x"})[0], 400)
        self.assertEqual(self.req("/api/grade", {"class": "mat-19a", "source": "wiki/mat-19a/limits.md", "kind": "rm", "text": "x"})[0], 400)
        self.assertEqual(self.req("/api/grade", {"class": "mat-19a", "source": "wiki/mat-19a/limits.md", "kind": "recall", "text": " "})[0], 400)

    def test_typed_answer_is_graded_on_the_idea_in_plain_text(self):  # "4x-4x is 0" was marked wrong for skipped steps
        seen = self.root / "prompt.txt"
        old, serve.CLAUDE = serve.CLAUDE, ["sh", "-c", f"cat > '{seen}'; printf 'VERDICT: right'"]
        self.addCleanup(setattr, serve, "CLAUDE", old)
        self.req("/api/grade", {"class": "mat-19a", "source": "wiki/mat-19a/limits.md", "kind": "answer",
                                "question": "q", "answer": "a", "text": "my try"})
        p = seen.read_text()
        self.assertIn("key idea", p)
        self.assertNotIn("$...$", p)  # the quiz page shows feedback as plain text: LaTeX appears as raw code
        self.req("/api/grade", {"class": "mat-19a", "source": "wiki/mat-19a/limits.md", "kind": "recall", "text": "x"})
        self.assertIn("$...$", seen.read_text())  # the site page renders math

    def test_pretest_questions_from_existing_quizzes(self):
        d = self.root / "studio/mat-19a/quizzes"
        d.mkdir(parents=True, exist_ok=True)
        (d / "q.json").write_text(json.dumps({"questions": [
            {"type": "short", "q": "What is a limit?", "answer": "a", "source": "wiki/mat-19a/limits.md"},
            {"type": "short", "q": "Other page", "answer": "b", "source": "wiki/mat-19a/other.md"}]}))
        qs = json.loads(self.get("/api/questions?page=wiki/mat-19a/limits.md")[2])
        self.assertEqual([q["q"] for q in qs], ["What is a limit?"])
        self.assertEqual(json.loads(self.get("/api/questions?page=../x")[2]), [])

    def test_quiz_me_chat_saves_scores(self):
        self.fake_claude("Right!\\nSCORE: wiki/mat-19a/quizme.md right\\nNext: what is x?")
        body = self.req("/api/chat", {"class": "mat-19a", "mode": "quiz", "messages": [{"role": "user", "text": "2"}]})[2]
        self.assertEqual(json.loads(body)["answer"], "Right!\nNext: what is x?")
        self.assertEqual(json.loads((self.root / "studio/mat-19a/scores.json").read_text())["wiki/mat-19a/quizme.md"], {"right": 1, "total": 1})

    def test_source_link_to_section(self):
        code, headers, _ = self.get("/wiki/mat-19a/limits.md?sec=One%20sided")
        self.assertEqual(headers["Location"], "/#/wiki/mat-19a/limits.md#One%20sided")

    # --- daily quiz (spaced repetition by wiki page) and the Quiz tab
    def test_review_boxes(self):  # right: next box, longer wait (once a day); wrong: box 0, back tomorrow
        from datetime import date
        d, m, pg = date(2026, 10, 1), {}, "wiki/mat-19a/limits.md"
        serve.review(m, pg, True, d)
        self.assertEqual(m[pg], {"box": 1, "due": "2026-10-03", "up": "2026-10-01"})
        serve.review(m, pg, True, d)  # a second right the same day: no extra jump
        self.assertEqual(m[pg]["box"], 1)
        serve.review(m, pg, False, d)
        self.assertEqual(m[pg]["box"], 0)
        self.assertEqual(m[pg]["due"], "2026-10-02")

    def test_score_updates_review_file(self):
        self.req("/api/score", {"class": "mat-19a", "source": "wiki/mat-19a/rev.md", "ok": True})
        self.assertEqual(json.loads((self.root / "studio/mat-19a/review.json").read_text())["wiki/mat-19a/rev.md"]["box"], 1)

    def test_daily_queued_once_a_day_per_class_with_pages(self):
        from datetime import date
        class Fake:
            jobs = []
            def add(self, *j): self.jobs.append(j)
        f, tried, d = Fake(), {}, date(2026, 10, 1)
        (self.root / ".planner-cache.json").unlink(missing_ok=True)  # other tests leave a syllabus behind
        serve.queue_daily(self.root, f, d, tried)
        serve.queue_daily(self.root, f, d, tried)  # 10 min later: already tried today
        self.assertEqual(f.jobs, [("mat-19a", "daily", "")])  # no exam in the planner: normal pace
        f.jobs.clear()
        self.plan([("MAT 19A", "Midterm 1", "exam", 20, 6)])
        try:
            serve.queue_daily(self.root, f, date(2030, 1, 1), {})  # a day with no daily file yet
        finally:
            (self.root / ".planner-cache.json").unlink()
        self.assertEqual(f.jobs, [("mat-19a", "daily", "--exam-in 6")])  # exam soon: new pages come faster
        f.jobs.clear()
        (self.root / "studio/mat-19a/daily").mkdir(parents=True, exist_ok=True)
        (self.root / "studio/mat-19a/daily/2026-10-02.html").write_text("x")
        serve.queue_daily(self.root, f, date(2026, 10, 2), {})  # made already (server restarted)
        self.assertEqual(f.jobs, [])

    def test_class_detail_shows_todays_daily_quiz(self):
        from datetime import date
        d = self.root / "studio/mat-19a/daily"; d.mkdir(parents=True, exist_ok=True)
        t = date.today().isoformat()
        (d / f"{t}.json").write_text(json.dumps({"questions": [{"type": "mcq"}, {"type": "short"}]}))
        (d / f"{t}.html").write_text("<title>Daily</title>")
        got = json.loads(self.get("/api/class/mat-19a")[2])["daily"]
        self.assertEqual(got, {"path": f"studio/mat-19a/daily/{t}.html", "n": 2, "min": 2.5})
        home = json.loads(self.get("/api/classes")[2])[0]
        self.assertEqual(home["daily"], "ready")

    def test_page_raw_links(self):  # Quiz tab: tick a lecture -> the wiki pages written from it
        f = self.root / "rawlinks.md"
        f.write_text("# X\n\n> Raw: [A](../../raw/mat-19a/a.md); [B](../../raw/mat-19a/b.md)\n\nbody")
        self.assertEqual(serve.raw_links(f), ["raw/mat-19a/a.md", "raw/mat-19a/b.md"])

    def test_study_topic_fits_many_pages(self):  # Quiz tab sends --pages with every ticked page
        old, serve.STUDY = serve.STUDY, ["sh", "-c", 'echo "$2" >> long.txt']
        try:
            pages = ",".join(f"wiki/mat-19a/page-{i:02}.md" for i in range(30))
            self.req("/api/study", {"class": "mat-19a", "kind": "quiz", "topic": "--pages " + pages})
            self.assertIn("page-29.md", " ".join(self.ran("long.txt")))
        finally:
            serve.STUDY = old


if __name__ == "__main__":
    unittest.main()
