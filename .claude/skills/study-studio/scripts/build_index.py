#!/usr/bin/env python3
"""studio/<class>/index.html: every generated output, newest first, one click away.

Usage: build_index.py <class-slug> [--root <project-root>]
"""
import argparse, html
from datetime import datetime
from pathlib import Path

KINDS = {".html", ".pdf", ".mp3", ".mp4", ".md"}
PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{cls} studio</title><style>
:root{{--bg:#07090f;--ink:#e8ecf4;--dim:#8a93a8;--line:#1c2233;--glow:#3b6cff}}
@media (prefers-color-scheme:light){{:root{{--bg:#f6f7fb;--ink:#10131c;--dim:#5a6275;--line:#dde1ea}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:ui-sans-serif,system-ui,-apple-system,sans-serif}}
body::before{{content:"";position:fixed;inset:-30vh -20vw auto;height:70vh;pointer-events:none;
background:radial-gradient(closest-side,color-mix(in srgb,var(--glow) 28%,transparent),transparent)}}
main{{position:relative;max-width:760px;margin:0 auto;padding:48px 16px}}
h1{{font-family:ui-serif,Georgia,serif;font-weight:500;font-size:clamp(32px,6vw,52px);margin:0 0 28px}}
a{{display:flex;justify-content:space-between;gap:16px;padding:14px 0;border-top:1px solid var(--line);color:inherit;text-decoration:none}}
a:hover span:first-child{{color:var(--glow)}}
.k{{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--dim);white-space:nowrap}}
</style></head><body><main><div class="k">{cls} · studio</div><h1>Study outputs</h1>
{rows}</main></body></html>
"""


def is_source_md(p):  # a slides/audio script: its built .html/.pdf/.mp3 is listed instead
    return p.suffix == ".md" and any(p.with_suffix(x).exists() for x in (".html", ".pdf", ".mp3"))


def listed(p):
    return (p.is_file() and p.suffix in KINDS and p.name != "index.html" and "frames" not in p.parts
            and not is_source_md(p))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cls")
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    d = Path(a.root) / "studio" / a.cls
    files = [p for p in d.rglob("*") if listed(p)]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    rows = "\n".join(
        f'<a href="{html.escape(p.relative_to(d).as_posix())}"><span>{html.escape(p.relative_to(d).as_posix())}</span>'
        f'<span class="k">{p.relative_to(d).parts[0]} · {datetime.fromtimestamp(p.stat().st_mtime):%b %d}</span></a>'
        for p in files) or "<p>Nothing yet. Try /study quiz.</p>"
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text(PAGE.format(cls=html.escape(a.cls), rows=rows))
    print(d / "index.html")


if __name__ == "__main__":
    main()
