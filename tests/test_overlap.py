import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tempfile, unittest

import overlap

CORR = "# Correlation\n\nA correlation coefficient measures how strongly two variables move together. Positive correlation means both rise. Negative correlation means one falls. Scatterplots show strength and direction of correlation coefficient values."
CORR2 = "# Correlation and r\n\nThe correlation coefficient r measures how strongly two variables move together. Positive correlation means both rise, negative correlation means one falls. Scatterplots show the strength and direction."
STRESS = "# Stress\n\nAcute stress is short and sharp, like a deadline. Chronic stress lasts for months and wears the body down through cortisol."


class Overlap(unittest.TestCase):
    def test_same_topic_pages_are_paired_and_others_are_not(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for n, t in (("a.md", CORR), ("b.md", CORR2), ("c.md", STRESS)):
                (d / n).write_text(t)
            pairs = overlap.overlaps(d)
        self.assertEqual([(a.name, b.name) for a, b, _ in pairs], [("a.md", "b.md")])

    def test_source_header_lines_do_not_count(self):  # every page cites "Sources"/"Raw"/"Updated": that is not shared content
        head = "> Sources: OpenStax Psychology chapter reading lecture\n> Raw: [x](../../raw/psc/x.md)\n> Updated: 2026-09-26\n\n"
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "a.md").write_text(head + STRESS)
            (d / "b.md").write_text(head + "# Habits\n\nRepeating a small action after the same cue turns it into an automatic routine over weeks.")
            self.assertEqual(overlap.overlaps(d), [])


if __name__ == "__main__":
    unittest.main()
