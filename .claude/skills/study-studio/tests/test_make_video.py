import subprocess, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
SCRIPT = Path(__file__).parent.parent / "scripts" / "make_video.py"


def probe(f):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f],
                                capture_output=True, text=True, check=True).stdout)


class TimingTest(unittest.TestCase):
    def test_split_follows_speech_after_each_marker(self):
        from make_video import slide_times
        md = "[slide 1]\nA: aaaa\n[slide 2]\nB: aaaaaaaaaaaa\n"
        self.assertEqual(slide_times(md, 2, 16.0), [4.0, 12.0])

    def test_no_markers_means_equal_split(self):
        from make_video import slide_times
        self.assertEqual(slide_times("A: hi\nB: yo\n", 4, 8.0), [2.0, 2.0, 2.0, 2.0])

    def test_speech_before_first_marker_goes_to_slide_1(self):
        from make_video import slide_times
        self.assertEqual(slide_times("A: aaaa\n[slide 2]\nB: aaaa\n", 2, 10.0), [5.0, 5.0])


class VideoTest(unittest.TestCase):
    def test_builds_mp4_as_long_as_audio(self):
        d = Path(tempfile.mkdtemp())
        for i, color in enumerate(["red", "blue"], 1):
            subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", f"color={color}:s=320x180",
                            "-frames:v", "1", d / f"deck.{i:03}.png"], check=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=d=3", d / "a.mp3"], check=True)
        (d / "s.md").write_text("[slide 1]\nA: one\n[slide 2]\nB: two\n")
        subprocess.run([sys.executable, SCRIPT, d, d / "a.mp3", d / "s.md", d / "o.mp4"], check=True)
        self.assertAlmostEqual(probe(d / "o.mp4"), 3.0, delta=0.3)


if __name__ == "__main__":
    unittest.main()
