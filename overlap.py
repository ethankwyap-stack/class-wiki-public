"""Find wiki pages that mostly repeat each other, so ingest can merge them.  python3 overlap.py <class>"""
import re, sys
from itertools import combinations
from pathlib import Path

CUTOFF = 0.20  # ponytail: word-set Jaccard. On the real PSC 001 wiki, 0.20+ = a couple of pairs on one topic, under 0.15 = unrelated. Embeddings would be smarter but cost a model call


def words(p):  # words of 5+ letters from the body; the "> Sources/Raw/Updated" header is on every page, so it is skipped
    body = "\n".join(l for l in p.read_text(errors="replace").splitlines() if not l.startswith(">"))
    return set(re.findall(r"[a-z]{5,}", body.lower()))


def overlaps(folder, cutoff=CUTOFF):  # [(page, page, score)] most alike first
    w = {p: words(p) for p in sorted(Path(folder).glob("*.md"))}
    out = [(a, b, len(w[a] & w[b]) / len(w[a] | w[b])) for a, b in combinations(w, 2) if w[a] | w[b]]
    return sorted((t for t in out if t[2] >= cutoff), key=lambda t: -t[2])


if __name__ == "__main__":
    for a, b, s in overlaps(Path("wiki") / sys.argv[1]):
        print(f"overlap {s:.0%}: {a.name} + {b.name}")
