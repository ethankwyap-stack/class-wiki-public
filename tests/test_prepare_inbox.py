import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # code lives one folder up
import shutil, subprocess, tempfile, unittest
from pathlib import Path

import prepare_inbox as P


def tiny_pdf(text, picture=False):
    """Smallest valid one-page PDF with one line of text (pdftotext can read it), and a 120x60 picture if asked."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode() + (b" q 120 0 0 60 72 500 cm /Im1 Do Q" if picture else b"")
    xobj = b"/XObject<</Im1 6 0 R>>" if picture else b""
    objs = [b"<</Type/Catalog/Pages 2 0 R>>", b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
            b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Resources<</Font<</F1 5 0 R>>" + xobj + b">>/Contents 4 0 R>>",
            b"<</Length %d>>stream\n" % len(stream) + stream + b"\nendstream",
            b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>"]
    if picture:
        objs.append(b"<</Type/XObject/Subtype/Image/Width 120/Height 60/ColorSpace/DeviceGray/BitsPerComponent 8/Length 7200>>"
                    b"stream\n" + b"\x80" * 7200 + b"\nendstream")
    out, offs = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offs)
    out += b"trailer\n<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, x)
    return bytes(out)


class PrepareTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.inbox = self.root / "inbox" / "mat-19a"
        self.inbox.mkdir(parents=True)
        self.calls = []

        def fake_claude(prompt, root):  # writes whatever file the prompt names after "Write it to "
            self.calls.append(prompt)
            out = prompt.split("Write it to ")[1].split()[0]
            (root / out).write_text("# Notes\nfrom claude\n")
        self._orig = P.run_claude, P.run_watch, P.fetch_gdoc
        P.run_claude = fake_claude

    def tearDown(self):
        P.run_claude, P.run_watch, P.fetch_gdoc = self._orig

    def run_prepare(self):
        P.main("mat-19a", self.root)
        return sorted(p.name for p in self.inbox.glob("*.md"))

    def test_txt_becomes_md(self):
        (self.inbox / "notes.txt").write_text("hello")
        self.assertEqual(self.run_prepare(), ["notes.md"])

    def test_text_pdf_uses_pdftotext_and_keeps_original(self):
        (self.inbox / "hw1.pdf").write_bytes(tiny_pdf("The limit of 1/x is 0. " * 20))
        self.assertEqual(self.run_prepare(), ["hw1.md"])
        self.assertIn("The limit of 1/x is 0.", (self.inbox / "hw1.md").read_text())
        self.assertEqual(self.calls, [])
        self.assertTrue((self.root / "raw/mat-19a/files/hw1.pdf").exists())
        self.assertFalse((self.inbox / "hw1.pdf").exists())

    def test_photo_is_deleted_once_its_notes_exist(self):  # the notes are the source; no photo clutter
        (self.inbox / "IMG_0001.jpg").write_bytes(b"photo")
        self.assertEqual(self.run_prepare(), ["IMG_0001.md"])
        self.assertFalse((self.inbox / "IMG_0001.jpg").exists())
        self.assertFalse((self.root / "raw/mat-19a/files").exists())
        self.assertIn("short title", self.calls[0])  # a readable source name, not IMG_0001

    def test_pdf_with_pictures_keeps_its_text_and_adds_what_claude_reads_in_the_pictures(self):  # Canvas screenshots in a Google Doc
        (self.inbox / "quiz.pdf").write_bytes(tiny_pdf("Unit 1 Canvas quiz " + "q " * 35, picture=True))
        self.assertEqual(self.run_prepare(), ["quiz.md"])
        md = (self.inbox / "quiz.md").read_text()
        self.assertIn("Unit 1 Canvas quiz", md)  # typed text stays exact
        self.assertIn("## Text in pictures", md)
        self.assertIn("from claude", md)
        self.assertEqual(len(self.calls), 1)
        self.assertIn("inbox/mat-19a/quiz.pdf", self.calls[0])

    def test_same_pdf_name_twice_keeps_both_originals(self):
        files = self.root / "raw/mat-19a/files"
        files.mkdir(parents=True)
        (files / "hw.pdf").write_bytes(b"old")
        (self.inbox / "hw.pdf").write_bytes(tiny_pdf("word " * 40))
        self.run_prepare()
        self.assertEqual(sorted(f.name for f in files.iterdir()), ["hw-1.pdf", "hw.pdf"])

    def test_scanned_pdf_goes_to_claude(self):
        (self.inbox / "scan.pdf").write_bytes(tiny_pdf(""))
        self.assertEqual(self.run_prepare(), ["scan.md"])
        self.assertIn("inbox/mat-19a/scan.pdf", self.calls[0])
        self.assertTrue((self.root / "raw/mat-19a/files/scan.pdf").exists())

    def test_claude_never_copies_student_ids(self):  # a graded test has Name + Student ID; raw/ goes to GitHub
        (self.inbox / "scan.pdf").write_bytes(tiny_pdf(""))
        (self.inbox / "q.pdf").write_bytes(tiny_pdf("Unit 1 Canvas quiz " + "q " * 35, picture=True))
        self.run_prepare()
        self.assertEqual(len(self.calls), 2)
        for prompt in self.calls:
            self.assertIn("student ID", prompt)

    def test_iphone_heic_is_converted_then_read_by_claude(self):
        png = self.root / "p.png"
        subprocess.run(["sips", "-s", "format", "png", "-z", "8", "8", "/System/Library/CoreServices/CoreTypes.bundle/Contents/Resources/GenericDocumentIcon.icns",
                        "--out", png], check=True, capture_output=True)
        subprocess.run(["sips", "-s", "format", "heic", png, "--out", self.inbox / "IMG_0001.HEIC"], check=True, capture_output=True)
        self.assertEqual(self.run_prepare(), ["IMG_0001.md"])
        self.assertIn("IMG_0001.jpg", self.calls[0])
        self.assertFalse((self.inbox / "IMG_0001.HEIC").exists())
        self.assertFalse((self.root / "raw/mat-19a/files").exists())

    def test_youtube_link_keeps_transcript_verbatim(self):
        P.run_watch = lambda url, work: (work.mkdir(parents=True, exist_ok=True) or
            "- **Title:** Limits Intro!\n## Transcript\n\n```\n[00:01] a limit is 3.14\n```\n")
        (self.inbox / "20260925-101500-youtube.url").write_text("https://youtu.be/abc\n")
        [name] = self.run_prepare()
        self.assertEqual(name, f"{P.datetime.now():%Y-%m-%d}-youtube-limits-intro.md")
        md = (self.inbox / name).read_text()
        self.assertIn("https://youtu.be/abc", md)
        self.assertIn("[00:01] a limit is 3.14", md)
        self.assertIn("from claude", md)
        self.assertFalse((self.inbox / ".work").exists())

    def test_google_doc_becomes_pdf_notes(self):
        asked = []
        P.fetch_gdoc = lambda doc_id: asked.append(doc_id) or ("Unit 1 Quiz", tiny_pdf("The limit of 1/x is 0. " * 20))
        (self.inbox / "20260929-101500-gdoc.url").write_text(
            "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123/edit?usp=sharing\n")
        self.assertEqual(self.run_prepare(), ["Unit 1 Quiz.md"])
        self.assertEqual(asked, ["1AbCdEfGhIjKlMnOpQrStUvWxYz0123"])
        self.assertIn("The limit of 1/x is 0.", (self.inbox / "Unit 1 Quiz.md").read_text())
        self.assertTrue((self.root / "raw/mat-19a/files/Unit 1 Quiz.pdf").exists())
        self.assertTrue((self.root / "inbox/done/mat-19a/20260929-101500-gdoc.url").exists())

    def test_private_google_doc_fails(self):
        P.fetch_gdoc = lambda doc_id: ("x", b"<html>Sign in</html>")
        (self.inbox / "a-gdoc.url").write_text("https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123/edit")
        self.assertEqual(self.run_prepare(), [])
        self.assertTrue((self.inbox / "failed" / "a-gdoc.url").exists())

    def test_failure_moves_file_aside(self):
        P.run_claude = lambda prompt, root: None  # writes nothing
        (self.inbox / "IMG_2.jpg").write_bytes(b"x")
        self.assertEqual(self.run_prepare(), [])
        self.assertTrue((self.inbox / "failed" / "IMG_2.jpg").exists())


if __name__ == "__main__":
    unittest.main()
