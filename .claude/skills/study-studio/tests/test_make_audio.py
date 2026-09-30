import shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
SCRIPT = Path(__file__).parent.parent / "scripts" / "make_audio.py"
TWO_LINES = "# Title\n\nA: Today we talk about limits.\nB: Great, what is a limit?\n"


def duration(mp3):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mp3],
                         capture_output=True, text=True, check=True).stdout
    return float(out)


class ParseTest(unittest.TestCase):
    def test_parse_keeps_only_speaker_lines(self):
        from make_audio import parse
        self.assertEqual(parse("# T\n\nA: hi\nnote\nB: yo **there**\n"), [("A", "hi"), ("B", "yo there")])


class AudioTest(unittest.TestCase):
    def run_engine(self, engine):
        d = Path(tempfile.mkdtemp())
        (d / "s.md").write_text(TWO_LINES)
        subprocess.run([sys.executable, SCRIPT, d / "s.md", d / "o.mp3", "--engine", engine], check=True)
        self.assertTrue((d / "o.mp3").is_file())
        self.assertGreater(duration(d / "o.mp3"), 1.0)

    @unittest.skipUnless(shutil.which("say"), "macOS only")
    def test_say_engine(self):
        self.run_engine("say")

    def test_kokoro_engine(self):
        self.run_engine("kokoro")


if __name__ == "__main__":
    unittest.main()
