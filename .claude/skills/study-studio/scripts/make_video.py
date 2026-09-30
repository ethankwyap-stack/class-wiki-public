#!/usr/bin/env python3
"""Slide PNGs + podcast mp3 -> .mp4 (timed slideshow)

Usage: make_video.py <slides-dir> <audio.mp3> <script.md> <out.mp4>

<slides-dir> holds deck.001.png, deck.002.png, ... (marp --images png).
"[slide N]" lines in the script say which slide is on screen; each slide stays
up in proportion to the spoken characters after its marker. No markers = equal split.
"""
import re, subprocess, sys, tempfile
from pathlib import Path

from make_audio import parse

MARK = re.compile(r"^\s*\[slide\s+(\d+)\]", re.I)


def slide_times(md, n, total):
    # ponytail: characters approximate speaking time; per-line TTS timings if sync drifts badly
    chars = [0] * n
    cur = 0
    for line in md.splitlines():
        m = MARK.match(line)
        if m:
            cur = min(max(int(m.group(1)) - 1, 0), n - 1)
        else:
            chars[cur] += sum(len(text) for _, text in parse(line))  # same A:/B: rule as the audio
    if not any(chars[1:]):
        return [total / n] * n
    return [total * c / sum(chars) for c in chars]


def main():
    slides_dir, audio, script, out = map(Path, sys.argv[1:5])
    pngs = sorted(slides_dir.glob("*.png"))
    if not pngs:
        sys.exit(f"no .png slides in {slides_dir}")
    total = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", audio],
                                 capture_output=True, text=True, check=True).stdout)
    times = slide_times(script.read_text(), len(pngs), total)
    with tempfile.TemporaryDirectory() as d:
        lst = Path(d) / "list.txt"
        # concat demuxer ignores the last duration unless the last file is repeated
        lst.write_text("".join(f"file '{p.resolve()}'\nduration {t:.3f}\n" for p, t in zip(pngs, times) if t > 0)
                       + f"file '{pngs[-1].resolve()}'\n")
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-i", audio,
                        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p", "-r", "30",
                        "-c:v", "libx264", "-c:a", "aac", "-t", f"{total:.3f}", out], check=True)
    print(out)


if __name__ == "__main__":
    main()
