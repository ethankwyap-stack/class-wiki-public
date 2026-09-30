#!/usr/bin/env python3
"""Quiz/flashcard JSON -> one self-contained offline HTML file.

Usage: build_quiz.py <in.json> <out.html> [--kind quiz|cards] [--root <project-root>]

Every item needs a "source" (project-root-relative wiki page); it becomes a
link relative to the output file. JSON shapes: see ../SKILL.md.
"""
import argparse, html as htmllib, json, os, random, re, sys
from pathlib import Path
from urllib.parse import quote

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
KINDS = {"quiz": ("questions", "quiz.html"), "cards": ("cards", "flashcards.html")}  # kind -> (JSON key, template)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--kind", choices=list(KINDS), default="quiz")
    ap.add_argument("--root", default=".")
    a = ap.parse_args()

    data = json.loads(Path(a.src).read_text())
    key, template = KINDS[a.kind]
    items = data.get(key) or []
    if not items:
        sys.exit(f"no {key} in {a.src}")
    out = Path(a.out).resolve()
    for i, item in enumerate(items):
        if not item.get("source"):
            sys.exit(f"item {i + 1} has no source (every item must cite a wiki page)")
        if item.get("type") == "mcq":  # models put the right answer first too often
            right = item["choices"][item["answer"]]
            pairs = list(zip(item["choices"], item.get("why") or [""] * len(item["choices"])))
            random.shuffle(pairs)  # "why" = why each choice is wrong: it moves with its choice
            item["choices"], item["why"] = map(list, zip(*pairs))
            item["answer"] = item["choices"].index(right)
        item["href"] = os.path.relpath(Path(a.root).resolve() / item["source"], out.parent)
        if item.get("section"):  # the site opens the page at that heading
            item["href"] += "?sec=" + quote(item["section"])

    # JSON inside <script>: escape "<" so content can never close the tag.
    blob = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    html = (TEMPLATES / template).read_text()
    out.parent.mkdir(parents=True, exist_ok=True)
    html = re.sub(r"<title>.*?</title>", lambda _: f"<title>{htmllib.escape(data.get('title') or 'Study')}</title>", html, count=1)
    out.write_text(html.replace("/*DATA*/null", blob))
    print(out)


if __name__ == "__main__":
    main()
