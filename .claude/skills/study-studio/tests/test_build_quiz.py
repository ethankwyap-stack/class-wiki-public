import json, subprocess, sys, tempfile, unittest
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "build_quiz.py"

QUIZ = {"title": "Limits", "class": "mat-19a", "questions": [
    {"type": "mcq", "q": "What is lim 1/x as x→∞?", "choices": ["0", "1", "∞"], "answer": 0,
     "explain": "1/x shrinks.", "source": "wiki/mat-19a/limits.md"},
    {"type": "short", "q": "Evil </script><img src=x onerror=alert(1)>", "answer": "a",
     "explain": "b", "source": "wiki/mat-19a/continuity.md"}]}
CARDS = {"title": "Deck", "class": "mat-19a", "cards": [
    {"front": "Derivative of x^2", "back": "2x", "source": "wiki/mat-19a/derivatives.md"}]}


def build(data, kind):
    root = Path(tempfile.mkdtemp())
    (root / "in.json").write_text(json.dumps(data))
    out = root / "studio" / "mat-19a" / "quizzes" / "q.html"
    subprocess.run([sys.executable, SCRIPT, root / "in.json", out, "--kind", kind, "--root", root], check=True)
    return out.read_text()


class BuildQuizTest(unittest.TestCase):
    def test_quiz_has_every_question_and_source_link(self):
        html = build(QUIZ, "quiz")
        self.assertIn("What is lim 1/x as x", html)
        self.assertIn("../../../wiki/mat-19a/limits.md", html)
        self.assertIn("../../../wiki/mat-19a/continuity.md", html)

    def test_no_network_urls(self):
        for data, kind in ((QUIZ, "quiz"), (CARDS, "cards")):
            self.assertNotIn("http", build(data, kind))

    def test_script_tag_in_content_is_escaped(self):
        self.assertNotIn("</script><img", build(QUIZ, "quiz"))

    def test_answers_saved_for_weak_spots(self):  # the site stores them in studio/<class>/scores.json
        for data, kind in ((QUIZ, "quiz"), (CARDS, "cards")):
            self.assertIn("SAVE(", build(data, kind).split("const SAVE")[1])

    def test_quiz_sends_its_tally_for_the_card(self):  # the Study card shows "7/10"
        self.assertIn("run: {out: location.pathname", build(QUIZ, "quiz"))

    def test_source_links_to_section(self):  # wrong answer -> the exact part of the page
        q = dict(QUIZ["questions"][0], section="One-sided limits")
        self.assertIn("limits.md?sec=One-sided%20limits", build({"title": "t", "class": "c", "questions": [q]}, "quiz"))

    def test_typed_answers_graded_and_retried(self):
        html = build(QUIZ, "quiz")
        self.assertIn("/api/grade", html)
        self.assertIn("Try again", html)
        self.assertIn("Your guess", build(CARDS, "cards"))  # cards: type before flip

    def test_challenge_label_and_hint(self):
        q = dict(QUIZ["questions"][1], challenge=True, hint="Start from zero sales.")
        html = build({"title": "t", "class": "c", "questions": [q]}, "quiz")
        self.assertIn("Challenge", html)
        self.assertIn("Hint", html)
        self.assertIn("Start from zero sales.", html)

    def test_page_title_is_the_deck_title(self):  # the site's Study tab shows it
        for data, kind in ((QUIZ, "quiz"), (CARDS, "cards")):
            self.assertIn(f"<title>{data['title']}</title>", build(data, kind))

    def test_cards(self):
        html = build(CARDS, "cards")
        self.assertIn("Derivative of x^2", html)
        self.assertIn("../../../wiki/mat-19a/derivatives.md", html)

    def test_choices_shuffled_answer_still_correct(self):
        import re
        q = {"type": "mcq", "q": "q", "choices": ["RIGHT", "w1", "w2", "w3"], "answer": 0, "explain": "", "source": "wiki/x.md"}
        positions = set()
        for _ in range(12):
            data = json.loads(re.search(r"const DATA = (.*);\n", build({"title": "t", "class": "c", "questions": [dict(q, choices=list(q["choices"]))]}, "quiz")).group(1))
            got = data["questions"][0]
            self.assertEqual(got["choices"][got["answer"]], "RIGHT")
            positions.add(got["answer"])
        self.assertGreater(len(positions), 1)

    def test_why_wrong_follows_its_choice(self):  # wrong MCQ pick -> why that pick is wrong
        import re
        q = {"type": "mcq", "q": "q", "choices": ["RIGHT", "w1", "w2"], "why": ["", "why w1", "why w2"],
             "answer": 0, "explain": "", "source": "wiki/x.md"}
        for _ in range(8):
            html = build({"title": "t", "class": "c", "questions": [json.loads(json.dumps(q))]}, "quiz")
            got = json.loads(re.search(r"const DATA = (.*);\n", html).group(1))["questions"][0]
            for c, w in zip(got["choices"], got["why"]):
                self.assertEqual(w, "" if c == "RIGHT" else "why " + c)
        self.assertIn("Why not", html)

    def test_rejects_missing_source(self):
        bad = {"title": "x", "class": "c", "questions": [{"type": "short", "q": "q", "answer": "a", "explain": "e"}]}
        root = Path(tempfile.mkdtemp())
        (root / "in.json").write_text(json.dumps(bad))
        r = subprocess.run([sys.executable, SCRIPT, root / "in.json", root / "o.html"], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("source", r.stderr)


if __name__ == "__main__":
    unittest.main()
