#!/usr/bin/env python3
"""Turn inbox/<class>/ uploads into markdown notes that ingest.sh can ingest.

.txt → .md · .pdf → pdftotext (Claude reads it if it is a scan, and reads its pictures, e.g. Canvas screenshots) · photos (HEIC too) → Claude
transcribes · .url (YouTube) → watch skill frames + transcript, Claude writes on-screen notes · .url (public Google
Doc) → downloaded as a PDF, then read like any PDF.
PDF originals go to raw/<class>/files/; photos are deleted once transcribed. A file that fails goes to inbox/<class>/failed/.
Usage: prepare_inbox.py <class-slug>
"""
import re, shutil, subprocess, sys, urllib.parse, urllib.request
from datetime import datetime
from pathlib import Path

from serve import slugify, unique

ROOT = Path(__file__).resolve().parent
IMAGES = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
WATCH = sorted(Path.home().glob(".claude/plugins/cache/claude-video/watch/*/skills/watch/scripts/watch.py"))


PRIVATE = (" Never copy a student ID number, email address or phone number (graded tests have them): write [removed]"
           " instead. Names may stay.")


def run_claude(prompt, root):
    # prompt on stdin: --allowedTools/--add-dir would swallow it (see CLAUDE.md Gotchas)
    subprocess.run(["claude", "-p", "--model", "sonnet", "--effort", "low", "--permission-mode", "acceptEdits",
                    "--allowedTools", "Read Write"], input=prompt, text=True, cwd=root,
                   capture_output=True, timeout=1800, check=True)


def run_watch(url, work):
    if not WATCH:
        raise RuntimeError("watch skill not installed")
    # YouTube often blocks video downloads for a while (fix: brew upgrade yt-dlp); captions still work
    for detail in ["efficient", "transcript"]:
        r = subprocess.run([sys.executable, WATCH[-1], url, "--detail", detail, "--out-dir", work],
                           capture_output=True, text=True, timeout=3600)
        if r.returncode == 0:
            return r.stdout
        print(f"   watch --detail {detail} failed: {r.stderr.strip().splitlines()[-1:]}", flush=True)
    raise RuntimeError("could not get this video (try: brew upgrade yt-dlp)")


def claude_notes(root, src, out, what):
    run_claude(f"Read {src.relative_to(root)}. It is {what} for a class. Transcribe ALL text exactly as written "
               "(equations in LaTeX, $...$), then describe any diagram or graph in one or two lines. "
               "No commentary." + PRIVATE + " Start with a '# ' heading: a short title that says what it shows "
               f"(e.g. '# Board: domain of square roots'). Write it to {out.relative_to(root)}", root)


def has_pictures(pdf):  # screenshots or scanned figures; tiny images (bullets, lines, logos) don't count
    rows = subprocess.run(["pdfimages", "-list", pdf], capture_output=True, text=True).stdout.splitlines()[2:]
    return any(int(r.split()[3]) >= 100 and int(r.split()[4]) >= 50 for r in rows if len(r.split()) > 4)


def picture_notes(root, src, out):
    run_claude(f"Read {src.relative_to(root)} (every page; 20 pages at a time if it is long). Its typed text is already "
               "saved. Transcribe ONLY the text inside its pictures and screenshots, exactly as written, page by page "
               "('Page N:'). For a test or quiz question: the question, every answer choice, and any mark that shows the "
               "right answer or the points. Describe a graph or diagram in one line. No other text. No text in any "
               f"picture: write 'None'.{PRIVATE} Write it to {out.relative_to(root)}", root)


def fetch_gdoc(doc_id):
    """(title, PDF bytes) of a Google Doc shared as 'Anyone with the link'. No login, no API key."""
    with urllib.request.urlopen(f"https://docs.google.com/document/d/{doc_id}/export?format=pdf", timeout=120) as r:
        name = re.search(r"filename\*=UTF-8''([^;]+)", r.headers.get("Content-Disposition", ""))
        return (urllib.parse.unquote(name.group(1)).removesuffix(".pdf") if name else doc_id), r.read()


def gdoc(src, cls, root):
    from serve import GDOC
    doc_id = GDOC.search(src.read_text()).group(1)  # the URL is rebuilt from the ID only: no other site is ever fetched
    title, pdf = fetch_gdoc(doc_id)
    if not pdf.startswith(b"%PDF"):  # a private doc answers with Google's sign-in page
        raise RuntimeError("Google Doc is not public. In the doc: Share → General access → Anyone with the link")
    name = re.sub(r'[/\\:*?"<>|]', "-", title).strip(" .")[:100] or doc_id
    pdf_path = unique(src.parent / f"{name}.pdf")
    pdf_path.write_bytes(pdf)
    shutil.move(src, unique(root / "inbox" / "done" / cls / src.name))
    convert(pdf_path, cls, root)


def keep(src, files):
    shutil.move(src, unique(files / src.name))  # iPhone reuses names like IMG_0001: never overwrite


def convert(src, cls, root):
    inbox, files = src.parent, root / "raw" / cls / "files"
    out = inbox / (src.stem + ".md")
    ext = src.suffix.lower()
    originals = [src]  # moved to raw/<class>/files/ only once the notes exist
    if ext == ".txt":
        src.rename(out)
        originals = []
    elif ext == ".pdf":
        text = subprocess.run(["pdftotext", "-layout", src, "-"], capture_output=True, text=True).stdout
        if len(text.split()) < 30:  # ponytail: fewer than 30 words = a scan, let Claude read the pages
            claude_notes(root, src, out, "a scanned PDF")
        else:
            out.write_text(f"# {src.stem}\n\n{text}")
            if has_pictures(src):  # typed text stays exact; Claude adds only what is inside the pictures
                pics = inbox / ".work" / (src.stem + "-pictures.md")
                pics.parent.mkdir(exist_ok=True)
                picture_notes(root, src, pics)
                out.write_text(out.read_text() + "\n\n## Text in pictures\n\n" + pics.read_text())
    elif ext in IMAGES:
        img = src
        if ext in {".heic", ".heif"}:  # iPhone photos: Claude can't read HEIC
            img = inbox / ".work" / (src.stem + ".jpg")
            img.parent.mkdir(exist_ok=True)
            subprocess.run(["sips", "-s", "format", "jpeg", src, "--out", img], check=True, capture_output=True)
        claude_notes(root, img, out, "a photo of class material (board, slide, notes or handout)")
        originals = []
        if out.exists():  # the notes are the source now: no photo clutter
            src.unlink()
    elif ext == ".url" and "docs.google.com" in src.read_text():
        return gdoc(src, cls, root)
    elif ext == ".url":
        out = youtube(src, root)
        originals = []
        shutil.move(src, unique(root / "inbox" / "done" / cls / src.name))
    if not out.exists():
        raise RuntimeError(f"no notes written for {src.name}")
    for f in originals:
        keep(f, files)


def youtube(src, root):
    url = src.read_text().strip()
    work = src.parent / ".work" / src.stem  # main() removes .work
    report = run_watch(url, work)
    title = re.search(r"\*\*Title:\*\* (.+)", report)
    title = title.group(1).strip() if title else src.stem
    transcript = report.split("## Transcript", 1)[-1] if "## Transcript" in report else "\n_No transcript._\n"
    (work / "report.md").write_text(report)
    notes = work / "notes.md"
    run_claude(f"Read {(work / 'report.md').relative_to(root)} and every frame image it lists. It is a class video. "
               "Write the on-screen content only: slide and board text exactly as shown, equations in LaTeX ($...$), "
               "one line per diagram, each with its t=MM:SS time. No summary of the talk (the transcript is kept "
               f"separately). Write it to {notes.relative_to(root)}", root)
    out = src.parent / f"{datetime.now():%Y-%m-%d}-youtube-{slugify(title, 60)}.md"
    out.write_text(f"# {title}\n\nSource: {url}\n\n## On-screen notes\n\n{notes.read_text()}\n"
                   f"## Transcript{transcript}")
    return out


def main(cls, root=ROOT):
    inbox = root / "inbox" / cls
    (root / "inbox" / "done" / cls).mkdir(parents=True, exist_ok=True)
    for src in sorted(inbox.iterdir()):
        if not src.is_file() or src.suffix == ".md" or src.name.startswith("."):
            continue
        print(f"== Converting {src.name}", flush=True)
        try:
            convert(src, cls, root)
        except Exception as e:
            print(f"!! {src.name}: {e}", flush=True)
            if src.exists():
                shutil.move(src, unique(inbox / "failed" / src.name))
    shutil.rmtree(inbox / ".work", ignore_errors=True)


if __name__ == "__main__":
    main(sys.argv[1])
