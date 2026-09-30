import json, re, subprocess, sys, tempfile, unittest
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "build_sheet.py"

SHEET = {"title": "Midterm 1 notes sheet", "class": "psc-001", "sections": [
    {"head": "Correlation vs causation", "why": "weak", "source": "wiki/psc-001/correlation.md",
     "items": ["r runs -1 to +1; sign = direction, size = strength", "Third variable can drive both"]},
    {"head": "Evil </style><script>alert(1)</script>", "why": "tested", "source": "wiki/psc-001/methods.md",
     "items": ["<b>not bold</b>"]}]}


def build(data):
    root = Path(tempfile.mkdtemp())
    (root / "in.json").write_text(json.dumps(data))
    out = root / "studio" / "psc-001" / "sheets" / "s.html"
    r = subprocess.run([sys.executable, SCRIPT, root / "in.json", out, "--root", root], capture_output=True, text=True)
    return r, (out.read_text() if out.exists() else "")


class BuildSheetTest(unittest.TestCase):
    def test_two_letter_sides_with_name_line_on_side_one(self):
        r, html = build(SHEET)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(html.count('class="side"'), 2)
        self.assertIn("size:letter", html)
        self.assertLess(html.index("Name"), html.index('class="side"', html.index('class="side"') + 1))

    def test_text_is_big_enough_to_read(self):  # the rule: "easily read by someone with normal vision"
        _, html = build(SHEET)
        sizes = [float(s) for s in re.findall(r"font-size:([\d.]+)pt", html)]
        self.assertTrue(sizes and min(sizes) >= 9, sizes)

    def test_every_block_links_its_wiki_page(self):
        _, html = build(SHEET)
        self.assertIn("../../../wiki/psc-001/correlation.md", html)
        self.assertIn("../../../wiki/psc-001/methods.md", html)

    def test_content_is_escaped_and_offline(self):
        _, html = build(SHEET)
        self.assertNotIn("<script>alert", html)
        self.assertNotIn("<b>not bold", html)
        self.assertNotIn("http", html)

    def test_too_many_words_fails_so_claude_cuts(self):  # a draft he cannot copy onto one sheet is useless
        big = dict(SHEET, sections=[dict(SHEET["sections"][0], items=["word " * 50] * 30)])
        r, _ = build(big)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("words", r.stderr)


if __name__ == "__main__":
    unittest.main()
