#!/usr/bin/env python3
"""What today's daily quiz covers, for one class (spaced repetition by wiki page).

  daily_pick.py <class> [--exam-in N] [--root DIR]  -> JSON {due, new, missed, avoid, tested}, or "NOTHING DUE" (exit 3)
  daily_pick.py <class> --check <quiz.json>    -> exit 1 if the quiz takes over 15 minutes

review.json ({page: {box, due, up}}) is written by serve.py from every quiz/card answer:
right = next box (longer wait), wrong = box 0 (back tomorrow). Never-scored pages are "new".
A page with a "## Past questions" section (the teacher tested it: Canvas, old exams) comes first among new pages.
"""
import json, re, sys
from datetime import date
from pathlib import Path

MAX_PAGES = 8  # ponytail: ~1-2 questions a page keeps a day near 15 min; raise if days end too short
NEW_PER_DAY = 3  # a backlog of new pages spreads over days instead of one huge quiz
MAX_MIN = 15
COST = {"mcq": 1, "short": 1.5}  # minutes; a challenge question takes 3


def load(f, empty):
    try:
        return json.loads(f.read_text())
    except (OSError, ValueError):
        return empty


def minutes(qs):
    return sum(3 if q.get("challenge") else COST.get(q.get("type"), 1.5) for q in qs)


def tested(p):  # how many past test/quiz questions a wiki page lists (top-level bullets under "## Past questions")
    parts = re.split(r"^## Past questions[ \t]*$", p.read_text(errors="replace"), maxsplit=1, flags=re.M)
    if len(parts) < 2:
        return 0
    section = re.split(r"^## ", parts[1], maxsplit=1, flags=re.M)[0]
    return len(re.findall(r"^[-*] ", section, re.M))


def due_pages(rel, review, today):  # seen before, due today or overdue; most overdue, then weakest, first
    due = [p for p in rel if p in review and review[p]["due"] <= today.isoformat()]
    return sorted(due, key=lambda p: (review[p]["due"], review[p]["box"]))


def new_rate(n_new, exam_in):  # exam_in: days to the next exam (new pages speed up to be seen a day early)
    if not exam_in:
        return NEW_PER_DAY
    return max(NEW_PER_DAY, -(-n_new // max(exam_in - 1, 1)))


def past_questions(st, pages):
    asked = set()
    for f in st.rglob("*.json"):
        d = load(f, {})
        if isinstance(d, dict):
            asked |= {q["q"] for q in d.get("questions", []) if q.get("source") in pages and q.get("q")}
    return asked


NOT_CONCEPT = {"overview", "see also", "past questions", "sources"}  # headings that are not a concept of their own


EXAMPLE = re.compile(r"^examples?\b|\bexamples?$", re.I)  # "Example: monogamy" only shows a concept already on the page


def concepts(p):  # a concept = one "## " heading; Overview only when the page has nothing else
    heads = [h.strip() for h in re.findall(r"^## (.+)$", p.read_text(errors="replace"), re.M)]
    return ([h for h in heads if h.lower() not in NOT_CONCEPT and not EXAMPLE.search(h)]
            or [h for h in heads if h.lower() == "overview"])


def times_asked(st):  # {(page, heading): how many questions have tested it}; every quiz records both
    n = {}
    for f in st.rglob("*.json"):
        d = load(f, {})
        for q in d.get("questions", []) if isinstance(d, dict) else []:
            k = (q.get("source"), q.get("section"))
            n[k] = n.get(k, 0) + 1
    return n


def not_tested(root, slug):  # classes.json "not_tested": pages kept in the wiki but never quizzed (e.g. study advice)
    c = next((c for c in load(root / "classes.json", []) if c.get("slug") == slug), {})
    return {f"wiki/{slug}/{n}" for n in c.get("not_tested", [])}


def pick(root, slug, today, exam_in=None):
    st = root / "studio" / slug
    skip = not_tested(root, slug)
    rel = [p.relative_to(root).as_posix() for p in sorted((root / "wiki" / slug).glob("*.md"))]
    rel = [p for p in rel if p not in skip]
    review = load(st / "review.json", {})
    due = due_pages(rel, review, today)[:MAX_PAGES]
    hits = {p: tested(root / p) for p in rel}
    new = sorted((p for p in rel if p not in review), key=lambda p: (-hits[p], (root / p).stat().st_mtime))
    new = new[:min(new_rate(len(new), exam_in), MAX_PAGES - len(due))]
    miss = [{"q": q, "answer": m.get("answer", ""), "source": m.get("source", "")}
            for q, m in load(st / "missed.json", {}).items() if m.get("source") not in skip]
    if not (due or new or miss):
        return None
    picked = set(due + new + [m["source"] for m in miss])
    avoid = {m["q"] for m in miss} | past_questions(st, picked)  # ask each idea a new way
    # One question per concept, never two on one: a missed question keeps its concept, every other
    # page gets its least-asked headings, so a page's concepts take turns instead of the easy one repeating.
    asked, used, slots = times_asked(st), set(), []
    for q, m in load(st / "missed.json", {}).items():
        k = (m.get("source", ""), m.get("section", ""))
        if k[0] not in skip and k not in used:
            used.add(k)
            slots.append({"source": k[0], "section": k[1], "why": "missed", "q": q})
    for why, pages, per in (("due", due, 1), ("new", new, 2)):
        for p in pages:
            free = [h for h in concepts(root / p) if (p, h) not in used]
            for h in sorted(free, key=lambda h: asked.get((p, h), 0))[:per]:  # stable: ties keep page order
                used.add((p, h))
                slots.append({"source": p, "section": h, "why": why, "asked": asked.get((p, h), 0)})
    slots.sort(key=lambda s: s["why"] == "missed")  # due and new first, missed last
    return {"due": due, "new": new, "missed": miss, "avoid": sorted(avoid), "concepts": slots,
            "tested": [p for p in due + new if hits[p]]}  # ask these in the teacher's style


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--check" in a:
        qs = load(Path(a[a.index("--check") + 1]), {}).get("questions", [])
        m = minutes(qs)
        print(f"{len(qs)} questions, about {m:g} min" + ("" if m <= MAX_MIN else f": over {MAX_MIN}, drop questions"))
        keys = [(q.get("source"), q.get("section")) for q in qs if q.get("section")]
        twice = sorted({f"{s} > {h}" for s, h in keys if keys.count((s, h)) > 1})
        for t in twice:
            print(f"two questions test one concept: {t}. Give each question a different concept from the list.")
        sys.exit(m > MAX_MIN or bool(twice))
    root = Path(a[a.index("--root") + 1]) if "--root" in a else Path.cwd()
    got = pick(root, a[0], date.today(), int(a[a.index("--exam-in") + 1]) if "--exam-in" in a else None)
    if not got:
        print("NOTHING DUE")
        sys.exit(3)
    print(json.dumps(got, indent=1))
