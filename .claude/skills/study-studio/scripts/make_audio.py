#!/usr/bin/env python3
"""Two-host podcast script (.md) -> .mp3

Usage: make_audio.py <script.md> <out.mp3> [--engine kokoro|say]

Script lines that start with "A:" or "B:" are spoken; everything else is ignored.
kokoro: local Kokoro-82M inside Docker (no network). say: macOS built-in voices (fallback).
"""
import argparse, json, re, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODELS = (HERE.parents[3] / ".models").resolve()  # ~/class-wiki/.models (resolve: Docker needs a real path)
IMAGE = "class-wiki-tts:1"
VOICES = {"kokoro": {"A": "af_heart", "B": "am_michael"}, "say": {"A": "Samantha", "B": "Daniel"}}


def parse(md):
    lines = []
    for line in md.splitlines():
        m = re.match(r"^\s*\**([AB])\**\s*:\s*(.+)", line)
        if m:
            lines.append((m.group(1), re.sub(r"[*_`#]", "", m.group(2)).strip()))
    return lines


def kokoro(lines, wav):
    if subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode:
        subprocess.run(["docker", "build", "-q", "-t", IMAGE, HERE.parent / "docker"], check=True)
    v = VOICES["kokoro"]
    subprocess.run(["docker", "run", "--rm", "-i", "--network", "none",
                    "-v", f"{MODELS}:/models:ro", "-v", f"{wav.parent}:/out", IMAGE],
                   input=json.dumps([[v[s], t] for s, t in lines]), text=True, check=True)
    (wav.parent / "out.wav").rename(wav)


def say(lines, wav):
    tmp = wav.parent
    parts = []
    for i, (s, t) in enumerate(lines):
        p = tmp / f"{i:04}.aiff"
        subprocess.run(["say", "-v", VOICES["say"][s], "-o", p, t], check=True)
        parts.append(p)
    (tmp / "list.txt").write_text("".join(f"file '{p}'\n" for p in parts))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", tmp / "list.txt", wav], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("out")
    ap.add_argument("--engine", choices=["kokoro", "say"], default="kokoro")
    a = ap.parse_args()

    lines = parse(Path(a.script).read_text())
    if not lines:
        sys.exit("no 'A:' / 'B:' lines in script")
    engine = a.engine
    if engine == "kokoro" and not (shutil.which("docker") and (MODELS / "voices-v1.0.bin").is_file()):
        print("Docker or Kokoro model missing; falling back to macOS say", file=sys.stderr)
        engine = "say"
    with tempfile.TemporaryDirectory() as d:
        wav = Path(d) / "all.wav"
        (kokoro if engine == "kokoro" else say)(lines, wav)
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-b:a", "128k", out], check=True)
    print(out)


if __name__ == "__main__":
    main()
