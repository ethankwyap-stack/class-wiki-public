import json, subprocess, sys, tempfile, unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import daily_pick

TODAY = date(2026, 10, 1)


def make(root, pages, review=None, missed=None, quizzes=()):
    w = root / "wiki" / "psc-001"
    w.mkdir(parents=True)
    for p in pages:
        (w / p).write_text("# " + p)
    st = root / "studio" / "psc-001"
    (st / "quizzes").mkdir(parents=True)
    if review is not None:
        (st / "review.json").write_text(json.dumps(review))
    if missed is not None:
        (st / "missed.json").write_text(json.dumps(missed))
    for i, qs in enumerate(quizzes):
        (st / "quizzes" / f"q{i}.json").write_text(json.dumps({"questions": qs}))


def P(name):
    return f"wiki/psc-001/{name}"


class PickTest(unittest.TestCase):
    def test_not_tested_pages_never_come_back(self):  # study advice: kept in the wiki, never quizzed
        root = Path(tempfile.mkdtemp())
        make(root, ["advice.md", "real.md"], review={P("advice.md"): {"box": 1, "due": "2026-09-20"}},
             missed={"Why sleep?": {"source": P("advice.md"), "answer": "x"}})
        (root / "classes.json").write_text(json.dumps([{"slug": "psc-001", "name": "PSC 001", "not_tested": ["advice.md"]}]))
        got = daily_pick.pick(root, "psc-001", TODAY)
        self.assertEqual((got["due"], got["new"], got["missed"]), ([], [P("real.md")], []))

    def test_due_pages_first_oldest_first_and_future_pages_wait(self):
        root = Path(tempfile.mkdtemp())
        make(root, ["a.md", "b.md", "c.md"], review={
            P("a.md"): {"box": 2, "due": "2026-09-30"}, P("b.md"): {"box": 1, "due": "2026-09-20"},
            P("c.md"): {"box": 3, "due": "2026-10-09"}})
        got = daily_pick.pick(root, "psc-001", TODAY)
        self.assertEqual(got["due"], [P("b.md"), P("a.md")])
        self.assertEqual(got["new"], [])

    def test_new_pages_are_capped_so_a_backlog_spreads_over_days(self):
        root = Path(tempfile.mkdtemp())
        make(root, [f"p{i}.md" for i in range(10)])
        got = daily_pick.pick(root, "psc-001", TODAY)
        self.assertEqual(len(got["new"]), daily_pick.NEW_PER_DAY)

    def test_exam_soon_speeds_up_new_pages(self):  # 19 new pages, test in 6 days: all seen at least a day early
        root = Path(tempfile.mkdtemp())
        make(root, [f"p{i:02}.md" for i in range(19)])
        self.assertEqual(len(daily_pick.pick(root, "psc-001", TODAY, exam_in=6)["new"]), 4)  # ceil(19 / 5)
        self.assertEqual(len(daily_pick.pick(root, "psc-001", TODAY, exam_in=1)["new"]), daily_pick.MAX_PAGES)
        self.assertEqual(len(daily_pick.pick(root, "psc-001", TODAY, exam_in=60)["new"]), daily_pick.NEW_PER_DAY)

    def test_total_pages_capped_due_before_new(self):
        root = Path(tempfile.mkdtemp())
        names = [f"p{i:02}.md" for i in range(20)]
        make(root, names, review={P(n): {"box": 0, "due": "2026-09-30"} for n in names[:15]})
        got = daily_pick.pick(root, "psc-001", TODAY)
        self.assertEqual(len(got["due"]) + len(got["new"]), daily_pick.MAX_PAGES)
        self.assertEqual(got["new"], [])

    def test_avoid_lists_every_past_question_on_picked_pages(self):
        root = Path(tempfile.mkdtemp())
        make(root, ["a.md", "b.md"], review={P("b.md"): {"box": 2, "due": "2026-12-01"}},
             quizzes=[[{"q": "Old A?", "source": P("a.md")}, {"q": "Old B?", "source": P("b.md")}],
                      [{"q": "Older A?", "source": P("a.md")}]])
        got = daily_pick.pick(root, "psc-001", TODAY)
        self.assertEqual(sorted(got["avoid"]), ["Old A?", "Older A?"])  # b is not due: its questions are not needed

    def test_missed_questions_come_back_and_their_page_is_in(self):
        root = Path(tempfile.mkdtemp())
        make(root, ["a.md"], review={P("a.md"): {"box": 3, "due": "2026-12-01"}},
             missed={"Why X?": {"answer": "Y", "source": P("a.md")}})
        got = daily_pick.pick(root, "psc-001", TODAY)
        self.assertEqual(got["missed"], [{"q": "Why X?", "answer": "Y", "source": P("a.md")}])
        self.assertIn("Why X?", got["avoid"])  # re-ask the idea, never the same words

    def test_tested_counts_bullets_under_past_questions(self):
        f = Path(tempfile.mkdtemp()) / "a.md"
        f.write_text("# A\n\n## Overview\n- not a question\n\n## Past questions\n- Q1 (Canvas)\n  - Answer: B\n- Q2\n\n## See Also\n- x\n")
        self.assertEqual(daily_pick.tested(f), 2)
        f.write_text("# A\n- no section\n")
        self.assertEqual(daily_pick.tested(f), 0)

    def test_new_pages_with_past_questions_come_first(self):  # the teacher already tested them
        root = Path(tempfile.mkdtemp())
        make(root, [f"p{i}.md" for i in range(6)])
        (root / P("p5.md")).write_text("# p5\n\n## Past questions\n- Q (Canvas)\n")
        got = daily_pick.pick(root, "psc-001", TODAY)
        self.assertEqual(got["new"][0], P("p5.md"))
        self.assertEqual(got["tested"], [P("p5.md")])

    def test_each_slot_is_a_different_concept_least_asked_first(self):  # a concept = one "## " heading on a page
        root = Path(tempfile.mkdtemp())
        make(root, ["a.md", "b.md"], review={P("a.md"): {"box": 1, "due": "2026-09-30"}},
             quizzes=[[{"q": "1", "source": P("a.md"), "section": "Alpha"}, {"q": "2", "source": P("a.md"), "section": "Alpha"},
                       {"q": "3", "source": P("a.md"), "section": "Beta"}]])
        (root / P("a.md")).write_text("# a\n\n## Overview\nx\n\n## Alpha\nx\n\n## Beta\nx\n\n## Gamma\nx\n\n## See Also\n- b\n")
        (root / P("b.md")).write_text("# b\n\n## Overview\nx\n\n## Past questions\n- Q\n")
        got = daily_pick.pick(root, "psc-001", TODAY)
        slots = [(c["source"], c["section"]) for c in got["concepts"]]
        self.assertEqual(slots[0], (P("a.md"), "Gamma"))  # never asked beats asked once or twice
        self.assertEqual(len(slots), len(set(slots)))
        self.assertIn((P("b.md"), "Overview"), slots)  # a page with no other concept falls back to its Overview
        self.assertFalse({s for _, s in slots} & {"See Also", "Past questions"})

    def test_an_example_heading_is_not_a_concept_but_a_named_study_is(self):  # an example only shows a concept on the page
        f = Path(tempfile.mkdtemp()) / "a.md"
        f.write_text("# a\n\n## Overview\nx\n\n## Example: monogamy\nx\n\n## The Los Angeles earthquake example\nx\n\n"
                     "## Examples of bias\nx\n\n## Study: London taxi drivers (2011)\nx\n\n## Converse error\nx\n")
        self.assertEqual(daily_pick.concepts(f), ["Study: London taxi drivers (2011)", "Converse error"])

    def test_a_missed_question_keeps_its_own_concept(self):
        root = Path(tempfile.mkdtemp())
        make(root, ["a.md"], review={P("a.md"): {"box": 1, "due": "2026-09-30"}},
             missed={"Why?": {"source": P("a.md"), "section": "Alpha", "answer": "y"}})
        (root / P("a.md")).write_text("# a\n\n## Alpha\nx\n\n## Beta\nx\n")
        got = daily_pick.pick(root, "psc-001", TODAY)
        self.assertEqual(sorted(c["section"] for c in got["concepts"]), ["Alpha", "Beta"])  # due page moves on to Beta

    def test_check_fails_two_questions_on_one_concept(self):
        f = Path(tempfile.mkdtemp()) / "d.json"
        f.write_text(json.dumps({"questions": [{"type": "mcq", "source": P("a.md"), "section": "Alpha"}] * 2}))
        r = subprocess.run([sys.executable, daily_pick.__file__, "psc-001", "--check", f], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Alpha", r.stdout)

    def test_nothing_due_means_no_quiz(self):
        root = Path(tempfile.mkdtemp())
        make(root, ["a.md"], review={P("a.md"): {"box": 3, "due": "2026-12-01"}})
        self.assertIsNone(daily_pick.pick(root, "psc-001", TODAY))

    def test_minutes_mcq_1_short_1_5_challenge_3(self):
        qs = [{"type": "mcq"}, {"type": "short"}, {"type": "short", "challenge": True}]
        self.assertEqual(daily_pick.minutes(qs), 5.5)

    def test_check_fails_a_quiz_over_15_minutes(self):
        root = Path(tempfile.mkdtemp())
        f = root / "d.json"
        f.write_text(json.dumps({"questions": [{"type": "short", "challenge": True}] * 6}))  # 18 min
        r = subprocess.run([sys.executable, daily_pick.__file__, "psc-001", "--check", f], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        f.write_text(json.dumps({"questions": [{"type": "mcq"}] * 6}))
        r = subprocess.run([sys.executable, daily_pick.__file__, "psc-001", "--check", f], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
