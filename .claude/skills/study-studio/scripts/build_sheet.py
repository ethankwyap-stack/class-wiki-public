#!/usr/bin/env python3
"""Notes-sheet JSON -> a printable 2-sided letter page, as a draft Ethan copies out by hand.

Usage: build_sheet.py <in.json> <out.html> [--root <project-root>]

JSON: {"title", "class", "sections": [{"head", "why": "weak|missed|tested|core", "source", "items": [str]}]}
Sections come most important first; side 1 fills before side 2. Over MAX_WORDS exits 1: cut, then rebuild.
"""
import argparse, html, json, os, sys
from pathlib import Path

MAX_WORDS = 800  # ponytail: rough handwriting capacity of 2 letter sides; tune if his sheets come out half empty
BADGE = {"weak": "weak spot", "missed": "missed", "tested": "on a test"}
CSS = """@page{size:letter;margin:0}
*{box-sizing:border-box}
body{margin:0;background:#d9d9d4;color:#111;font:10pt/1.3 ui-sans-serif,system-ui,-apple-system,sans-serif}
.tip{max-width:8.5in;margin:24px auto 0;padding:0 16px;font-size:11pt}
.side{width:8.5in;height:11in;margin:24px auto;padding:.45in;background:#fff;box-shadow:0 2px 12px #0003;overflow:hidden;
columns:2;column-gap:.3in;column-rule:1px solid #ccc}
.top{column-span:all;display:flex;justify-content:space-between;align-items:baseline;border-bottom:2px solid #111;
margin-bottom:8px;padding-bottom:4px;font-size:11pt}
section{break-inside:avoid;margin-bottom:8px}
h2{font-size:10.5pt;margin:0 0 2px}
ul{margin:0;padding-left:14px}
.b{font-size:9pt;font-weight:400;border:1px solid #111;border-radius:3px;padding:0 3px;margin-left:4px}
a{font-size:9pt;color:#555}
@media print{body{background:#fff}.tip{display:none}.side{margin:0;box-shadow:none;break-after:page}}
@media screen and (max-width:8.5in){.side{zoom:.45}}"""  # screen only: a letter page IS 8.5in wide and would shrink in print too


def block(s, out_dir, root):
    href = os.path.relpath(root / s["source"], out_dir)
    badge = f'<span class="b">{BADGE[s["why"]]}</span>' if s.get("why") in BADGE else ""
    items = "".join(f"<li>{html.escape(i)}</li>" for i in s.get("items") or [])
    return (f'<section><h2>{html.escape(s["head"])}{badge}</h2><ul>{items}</ul>'
            f'<a href="{html.escape(href)}">{html.escape(Path(s["source"]).stem)}</a></section>')


def words(s):
    return len(" ".join([s["head"], *(s.get("items") or [])]).split())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--root", default=".")
    a = ap.parse_args()

    data = json.loads(Path(a.src).read_text())
    secs = data.get("sections") or []
    if not secs:
        sys.exit(f"no sections in {a.src}")
    for i, s in enumerate(secs):
        if not s.get("source"):
            sys.exit(f"section {i + 1} has no source (every block must cite a wiki page)")
    total = sum(map(words, secs))
    if total > MAX_WORDS:
        sys.exit(f"{total} words, limit {MAX_WORDS}: too much to copy onto one sheet. Cut the least important, then rebuild.")

    out, root = Path(a.out).resolve(), Path(a.root).resolve()
    sides, n = [[], []], 0
    for s in secs:  # in order: the most important end up on side 1
        sides[n > total / 2].append(block(s, out.parent, root))
        n += words(s)
    title = html.escape(data.get("title") or "Notes sheet")
    top = f'<div class="top"><b>Name: ______________________________</b><span>{title}</span></div>'
    page = (f'<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{title}</title><style>{CSS}</style></head><body>"
            f'<p class="tip">Draft: copy this by hand onto your sheet. Writing it out is the studying. '
            f"{total} words · print it to see the real size.</p>"
            f'<div class="side">{top}{"".join(sides[0])}</div>'
            f'<div class="side"><div class="top"><b>Side 2</b><span>{title}</span></div>{"".join(sides[1])}</div>'
            "</body></html>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)
    print(out)


if __name__ == "__main__":
    main()
