import os, subprocess, sys, tempfile, unittest
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "build_index.py"


class IndexTest(unittest.TestCase):
    def test_lists_outputs_newest_first_with_relative_links(self):
        root = Path(tempfile.mkdtemp())
        d = root / "studio" / "mat-19a"
        for i, rel in enumerate(["quizzes/2026-09-20-limits.html", "slides/2026-09-22-limits.pdf", "slides/deck.001.png",
                                 "slides/2026-09-22-limits.md", "exam/2026-10-16-midterm-1/plan.md"]):
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_text("x")
            os.utime(d / rel, (1e9 + i, 1e9 + i))
        subprocess.run([sys.executable, SCRIPT, "mat-19a", "--root", root], check=True)
        html = (d / "index.html").read_text()
        self.assertLess(html.index("slides/2026-09-22-limits.pdf"), html.index("quizzes/2026-09-20-limits.html"))
        self.assertNotIn("deck.001.png", html)  # video frames are not outputs
        self.assertNotIn("http", html)
        self.assertNotIn("slides/2026-09-22-limits.md", html)  # source of the pdf, not an output
        self.assertIn(">exam · ", html)  # label = top-level kind, not the exam folder
        self.assertIn("exam/2026-10-16-midterm-1/plan.md", html)


if __name__ == "__main__":
    unittest.main()
