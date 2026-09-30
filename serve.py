#!/usr/bin/env python3
"""Local Class Wiki site: http://localhost:4323 (127.0.0.1 only).

Reads: only wiki/, raw/, studio/, site/. A plain .md link redirects into the viewer (?raw=1 = the file).
Writes: add a class, upload files, add a YouTube link. Every upload queues `ingest.sh <class>`.
Usage: serve.py [port]
"""
import glob, json, os, queue, re, shutil, signal, subprocess, sys, threading, time
from datetime import date, datetime, timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / ".claude/skills/study-studio/scripts"))
import daily_pick  # noqa: E402


def tailnet_name():  # this Mac's own Tailscale name, so `tailscale serve` (phone) passes the Host guard
    cli = shutil.which("tailscale") or "/usr/local/bin/tailscale"  # launchd PATH lacks /usr/local/bin
    try:
        r = subprocess.run([cli, "status", "--json"], capture_output=True, text=True, timeout=10)
        return {json.loads(r.stdout)["Self"]["DNSName"].rstrip(".")} - {""} if r.returncode == 0 else set()
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return set()


HOSTS = {"localhost", "127.0.0.1"} | tailnet_name()
PUBLIC = {"wiki", "raw", "studio", "site"}
UPLOADS = {".pdf", ".txt", ".md", ".jpg", ".jpeg", ".png", ".heic", ".heif"}
GDOC = re.compile(r"/document/d/([\w-]{20,})")  # a Google Doc's ID; prepare_inbox.py downloads it as a PDF
YOUTUBE = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
MAX_UPLOAD = 500 * 2**20
MAX_JSON = 64 * 2**10
INGEST = [str(ROOT / "ingest.sh")]
STUDY = [str(ROOT / "study.sh")]
# answer-only (no tools, no MCP, no CLAUDE.md/hooks); prompt on stdin
CLAUDE = ["claude", "-p", "--model", "sonnet", "--safe-mode", "--tools", "", "--strict-mcp-config", "--no-session-persistence"]
GRADE = {  # /api/grade kinds (desirable difficulties, PSC 001)
    "answer": "Grade Ethan's typed answer to a quiz question. Right = he has the key idea of the expected answer; wording, "
              "form and order may differ. Do not require shown work or every step: a correct short answer is right. "
              "Right but missing a small part the question asked for: still right, name the missing part in one line. "
              "If he showed steps and one is wrong, say which.\n"
              "Write math as plain text (x^2 - 16, 4x - 4x = 0), never $ or LaTeX: this page cannot show it.\n"
              "QUESTION: {q}\nEXPECTED ANSWER: {a}",
    "recall": "Ethan closed the wiki page below and wrote everything he remembers (blank-page recall). List the key ideas he "
              "missed or got wrong, most important first. Right = he got at least about 70% of the key ideas.",
    "summary": "Ethan wrote a summary of the wiki page below. It should be organized as question, evidence, conclusion, in his own "
               "words (not copied). Say what is missing, wrong, or just copied. Right = accurate, organized, and in his own words.",
}
QUIZ_ME = """
QUIZ ME MODE: do not lecture. Ask ONE question at a time, mostly from the weakest pages in these scores
(page: right/total): {scores}. Pages above 80% right: ask harder questions (apply it, explain why). Pages below 50%:
ask basic questions, or about a page it builds on. Wait for Ethan's try before you explain. After you grade a try,
add one line exactly "SCORE: wiki/{slug}/<page>.md right" or "... wrong", then ask the next question.
Never reuse the lecture's own numbers or examples: put each idea in a new situation, and ask it in different ways
(apply it, explain why, find the mistake, compare, predict). Each question gives every fact it needs.
After 3 right in a row, give one challenge problem: several steps, or two ideas mixed, or "why"/"what if".
Ethan asking you a question: answer it briefly, then continue the quiz."""
SYLLABUS_ME = "Use the syllabus for questions like what to study this week: big grade weights and near dates first."
INTERVALS = [1, 2, 4, 8, 16, 32]  # days until a page comes back, by review box (Leitner)
KINDS = {"daily", "quiz", "cards", "slides", "audio", "video", "map", "report", "table", "sheet", "exam"}  # /study commands


class Ingester:
    """One job at a time (index.md and log.md are shared). A job queued twice runs once more at most.
    Job = (slug,) for ingest.sh, or (slug, kind, topic) for study.sh."""

    def __init__(self, root):
        self.root, self.q, self.running, self.queued, self.proc = root, queue.Queue(), None, set(), None
        self.lock = threading.Lock()
        threading.Thread(target=self.loop, daemon=True).start()

    def add(self, *job):
        with self.lock:
            if job not in self.queued:
                self.queued.add(job)
                self.q.put(job)

    def state(self, slug):
        return ("running" if self.running == (slug,) else
                "queued" if (slug,) in self.queued else "idle")

    def cancel(self, *job):  # waiting: drop it; running: stop it and everything it started (claude, docker)
        with self.lock:
            self.queued.discard(job)
            if self.running == job and self.proc:
                os.killpg(self.proc.pid, signal.SIGTERM)

    def jobs(self, slug):  # study jobs running or waiting for this class: (slug, kind, topic)
        return [j for j in [self.running, *self.queued] if j and j[0] == slug and len(j) > 1]

    def making(self, slug):
        return [j[1] for j in self.jobs(slug)]

    def loop(self):
        while True:
            job = self.q.get()
            with self.lock:
                if job not in self.queued:  # cancelled while waiting
                    continue
                self.queued.discard(job)
                self.running = job
            (self.root / "inbox" / job[0]).mkdir(parents=True, exist_ok=True)
            with open(self.root / "inbox" / job[0] / ".ingest.log", "a") as log:
                log.write(f"\n##### {datetime.now():%b %d %H:%M} {' '.join(job[1:2]) or 'ingest'}\n")
                log.flush()
                with self.lock:  # own process group, so cancel can stop the whole tree
                    self.proc = subprocess.Popen((STUDY if len(job) > 1 else INGEST) + list(job), cwd=self.root,
                                                 stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                if self.proc.wait() < 0:
                    log.write("##### cancelled\n")
            with self.lock:
                self.running = self.proc = None


class Handler(SimpleHTTPRequestHandler):
    classes_lock = threading.Lock()  # add_class reads then rewrites classes.json
    scores_lock = threading.Lock()  # same for studio/<class>/scores.json

    def __init__(self, *a, ingester, **k):
        self.ingester = ingester
        super().__init__(*a, **k)

    @property
    def root(self):
        return Path(self.directory)

    def local(self):  # DNS rebinding guard: only answer to our own host name
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        return host in HOSTS

    def do_GET(self):
        if not self.local():
            return self.send_error(403)
        url = urlsplit(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path.startswith("/api/class/"):
            return self.class_detail(url.path.rsplit("/", 1)[1])
        if url.path in self.GETS:
            return self.send_json(getattr(self, self.GETS[url.path])(q))
        if url.path == "/api/search":
            return self.search(q.get("class", ""), q.get("q", "").strip().lower(), q.get("in") == "wiki")
        if url.path == "/":
            self.path = "/site/index.html"
        self.serve_file(url)

    GETS = {"/api/classes": "class_cards", "/api/calendar": "calendar", "/api/questions": "pretest"}

    def class_cards(self, q):
        return [{**c, "pages": len(list((self.root / "wiki" / c["slug"]).glob("*.md"))),
                 "next": next_up(coming(self.root, c["name"])), "daily": daily_state(self.root, c["slug"])}
                for c in classes(self.root)]

    def calendar(self, q):  # every class's syllabus items, for the month grid
        return [{**i, "class": c["slug"], "name": c["name"], "idx": n}
                for n, c in enumerate(classes(self.root)) for i in syllabus(self.root, c["name"])]

    def pretest(self, q):  # questions already written for this page, no Claude call
        page = q.get("page", "")
        if page in daily_pick.not_tested(self.root, page.split("/")[1] if page.count("/") == 2 else ""):
            return []
        qs = [x for f in sorted((self.root / "studio").glob("*/quizzes/*.json")) for x in json.loads(f.read_text()).get("questions", [])]
        return [x for x in qs if x.get("source") == page and not x.get("challenge")][:3]

    def serve_file(self, url):
        rel = Path(self.translate_path(self.path)).relative_to(self.directory)  # translate_path strips ../
        if not rel.parts or rel.parts[0] not in PUBLIC:
            return self.send_error(404)
        if rel.suffix == ".md" and "raw=1" not in url.query:
            self.send_response(302)
            sec = parse_qs(url.query).get("sec", [""])[0]  # quiz source link to one section
            self.send_header("Location", "/#/" + rel.as_posix() + ("#" + quote(sec) if sec else ""))
            return self.end_headers()
        super().do_GET()

    def do_POST(self):
        # CSRF guard: a custom header forces a CORS preflight, which this server never answers
        if not self.local() or self.headers.get("X-Class-Wiki") != "1":
            return self.send_error(403)
        url = urlsplit(self.path)
        size = int(self.headers.get("Content-Length") or 0)
        if url.path == "/api/upload":
            return self.upload_request(url, size)
        if size > MAX_JSON:
            return self.fail(413, "Too big")
        body = read_json(self.rfile, size)
        if body is None:
            return self.fail(400, "Bad JSON")
        route = self.POSTS.get(url.path)
        if not route:
            return self.fail(404, "Not found")
        s = lambda k: str(body.get(k, ""))  # noqa: E731
        route(self, body, s)

    POSTS = {  # path -> (handler, JSON body, body field as text)
        "/api/classes": lambda h, b, s: h.add_class(s("name").strip()),
        "/api/link": lambda h, b, s: h.add_link(s("class"), s("url").strip()),
        "/api/retry": lambda h, b, s: h.retry(s("class")),
        "/api/study": lambda h, b, s: h.study(s("class"), s("kind"), s("topic").strip()),
        "/api/cancel": lambda h, b, s: h.cancel(s("class"), b.get("kind")),
        "/api/chat": lambda h, b, s: h.chat(s("class"), b.get("messages"), b.get("mode") == "quiz"),
        "/api/grade": lambda h, b, s: h.grade(s("class"), s("source"), s("kind"), b),
        "/api/delete": lambda h, b, s: h.delete(s("class"), s("path")),
        "/api/score": lambda h, b, s: h.score(s("class"), s("source"), b.get("ok") is True, b),
    }

    def upload_request(self, url, size):
        if size > MAX_UPLOAD:
            return self.fail(413, "Too big")
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        self.upload(q.get("class", ""), q.get("name", ""), size)

    def cancel(self, slug, kind):  # study jobs only: a half-done ingest would leave the wiki half-written
        for j in self.ingester.jobs(slug):
            if j[1] == kind:
                self.ingester.cancel(*j)
        self.send_json({"ok": True})

    def retry(self, slug):
        if not find_class(self.root, slug):
            return self.fail(404, "No such class")
        inbox = self.root / "inbox" / slug
        for f in (inbox / "failed").glob("*"):
            f.rename(unique(inbox / f.name))
        self.ingester.add(slug)
        self.send_json({"ok": True})

    def study(self, slug, kind, topic):
        if not find_class(self.root, slug):
            return self.fail(404, "No such class")
        if kind not in KINDS:
            return self.fail(400, "Unknown study tool")
        self.ingester.add(slug, kind, topic[:3000])  # Quiz tab: --pages with every ticked page
        self.send_json({"ok": True})

    def score(self, slug, source, ok, b={}):  # quiz + flashcard answers; /study exam reads them for weak spots
        if not find_class(self.root, slug):
            return self.fail(404, "No such class")
        if not page_of(slug, source):
            return self.fail(400, "Bad source")
        run = b.get("run")  # this quiz's tally so far, shown on its Study card
        if run:
            out, tally = str(run.get("out", "")).lstrip("/"), quiz_tally(run)
            if not tally or not out.startswith(f"studio/{slug}/") or ".." in out:
                return self.fail(400, "Bad run")
            self.update_json(self.root / "studio" / slug / "results.json", lambda m: m.__setitem__(out, tally))
        self.save_score(slug, source, ok)
        if b.get("q"):  # missed list: a wrong question stays until a later right answer
            self.update_json(self.root / "studio" / slug / "missed.json", lambda m: mark_missed(m, source, ok, b))
        self.send_json({"ok": True})

    def update_json(self, f, change):
        with self.scores_lock:
            m = scores(f)
            change(m)
            f.write_text(json.dumps(m, indent=1))

    def delete(self, slug, path):  # an output (all its files), a source (and its original) or a wiki page. Moved to .trash/, not erased
        r, parts = self.root.resolve(), Path(path).parts  # resolved: /var is /private/var on a Mac
        p = (r / path).resolve()
        if not find_class(r, slug):
            return self.fail(404, "No such class")
        if not deletable(r, slug, parts, p):
            return self.fail(400, "Cannot delete that")
        files = files_of(parts[0], p)
        to_trash(r, files)
        st = r / "studio" / slug
        if parts[0] == "wiki":  # no dead rows or scores left behind
            drop_index_row(r / "wiki" / "index.md", f"{slug}/{p.name})")
            self.update_json(st / "scores.json", lambda m: m.pop(path, None))
            self.update_json(st / "missed.json", lambda m: [m.pop(q) for q in [q for q, e in m.items() if e.get("source") == path]])
        if parts[0] == "studio":
            self.update_json(st / "results.json", lambda m: [m.pop(f.relative_to(r).as_posix(), None) for f in files])
        self.send_json({"deleted": [f.name for f in files]})

    def save_score(self, slug, source, ok):
        f = self.root / "studio" / slug / "scores.json"
        with self.scores_lock:
            s = scores(f)
            e = s.setdefault(source, {"right": 0, "total": 0})
            e["right"] += ok
            e["total"] += 1
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(s, indent=1))
            rf = f.parent / "review.json"  # the daily quiz's due dates
            m = scores(rf)
            review(m, source, ok, date.today())
            rf.write_text(json.dumps(m, indent=1))

    def grade(self, slug, source, kind, b):  # typed quiz answer, blank-page recall, or summary -> one Claude call
        if not find_class(self.root, slug):
            return self.fail(404, "No such class")
        text = str(b.get("text", "")).strip()[:8000]
        if not page_of(slug, source) or kind not in GRADE or not text:
            return self.fail(400, "Bad request")
        p = self.root / source
        page = p.read_text(errors="replace") if p.exists() else ""
        prompt = GRADE[kind].format(q=str(b.get("question", ""))[:2000], a=str(b.get("answer", ""))[:2000]) + f"""
First line exactly "VERDICT: right" or "VERDICT: wrong". Then short feedback{"" if kind == "answer" else " (markdown, math in $...$)"}, talking to Ethan as "you".
If wrong, say what to go back and learn. A mistake is a signal to learn, not a failure.

WIKI PAGE ({source}):
{page}

ETHAN WROTE:
{text}"""
        r = ask(prompt)
        if isinstance(r, tuple):
            return self.fail(*r)
        m = re.match(r"\s*VERDICT:\s*(right|wrong)\s*", r, re.I)
        self.send_json({"ok": bool(m) and m[1].lower() == "right", "feedback": r[m.end():].strip() if m else r})

    def chat(self, slug, messages, quiz=False):  # one question = one `claude -p` on Ethan's plan
        if not find_class(self.root, slug):
            return self.fail(404, "No such class")
        if not isinstance(messages, list) or not messages:
            return self.fail(400, "No question")
        r = ask(self.chat_prompt(slug, messages, quiz))
        if isinstance(r, tuple):
            return self.fail(*r)
        if quiz:  # Claude marks each graded try with a SCORE line: save it, hide it
            r = self.take_scores(slug, r)
        self.send_json({"answer": r})

    def take_scores(self, slug, r):
        for src, ok in re.findall(r"^SCORE:\s*(\S+)\s+(right|wrong)\s*$", r, re.M | re.I):
            if page_of(slug, src):
                self.save_score(slug, src, ok.lower() == "right")
        return re.sub(r"^SCORE:.*\n?", "", r, flags=re.M | re.I).strip()

    def chat_prompt(self, slug, messages, quiz):
        wiki ="\n\n".join(f"=== {p.relative_to(self.root).as_posix()}\n{p.read_text(errors='replace')}"
                            for p in sorted((self.root / "wiki" / slug).glob("*.md")))
        talk = "\n".join(f"{'User' if m.get('role') == 'user' else 'Assistant'}: {m.get('text', '')}"
                         for m in messages[-20:] if isinstance(m, dict))
        return f"""You help Ethan, a UC Davis student, study this class. Answer from the class wiki below.
Cite the wiki page you used, e.g. (wiki/{slug}/limits.md). If the wiki does not cover it, say so first,
then give a short general answer marked "Not from your notes". Be short and clear. Math in $...$.
{QUIZ_ME.format(slug=slug, scores=json.dumps(scores(self.root / "studio" / slug / "scores.json"))) if quiz else ""}
{f"Never quiz Ethan on these pages (not on his tests; answer questions about them normally): {', '.join(sorted(skip))}" if quiz and (skip := daily_pick.not_tested(self.root, slug)) else ""}
SYLLABUS (from his course planner; today is {date.today().isoformat()}):
{syllabus_text(coming(self.root, find_class(self.root, slug)["name"]))}
{SYLLABUS_ME}
CLASS WIKI:
{wiki[:300000]}

CONVERSATION:
{talk}
Assistant:"""

    def add_class(self, name):
        slug = slugify(name, 40)
        if not slug:
            return self.fail(400, "Class name needs letters or numbers")
        with self.classes_lock:
            cs = classes(self.root)
            if slug in {c["slug"] for c in cs}:
                return self.fail(409, "Class already exists")
            for d in ["wiki", "raw", "studio", "inbox"]:
                (self.root / d / slug).mkdir(parents=True, exist_ok=True)
            (self.root / "classes.json").write_text(json.dumps(cs + [{"slug": slug, "name": name}], indent=1))
        self.send_json({"slug": slug})

    def upload(self, slug, name, size):
        if not find_class(self.root, slug):
            return self.fail(404, "No such class")
        name = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(name).name).lstrip(".")
        if Path(name).suffix.lower() not in UPLOADS:
            return self.fail(400, "Only PDF, photo, .txt or .md files")
        dest = unique(self.root / "inbox" / slug / name)
        with open(dest, "wb") as f:
            left = size
            while left:
                chunk = self.rfile.read(min(left, 2**20))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        self.ingester.add(slug)
        self.send_json({"saved": dest.name})

    def add_link(self, slug, link):
        if not find_class(self.root, slug):
            return self.fail(404, "No such class")
        u = urlsplit(link)
        host = u.hostname or ""
        kind = ("youtube" if host in YOUTUBE else
                "gdoc" if host == "docs.google.com" and GDOC.match(u.path) else None)
        if u.scheme not in {"http", "https"} or not kind:
            return self.fail(400, "Only YouTube or Google Docs links")
        dest = unique(self.root / "inbox" / slug / f"{datetime.now():%Y%m%d-%H%M%S}-{kind}.url")
        dest.write_text(link)
        self.ingester.add(slug)
        self.send_json({"saved": dest.name})

    def class_detail(self, slug):
        c = find_class(self.root, slug)
        if not c:
            return self.fail(404, "No such class")
        r, inbox = self.root, self.root / "inbox" / slug
        self.send_json({
            **c,
            "pages": [{"path": p.relative_to(r).as_posix(), "title": title(p), "raw": raw_links(p), "tested": daily_pick.tested(p)}
                      for p in sorted((r / "wiki" / slug).glob("*.md"))],
            "daily": daily(r, slug),
            "sources": [{"path": p.relative_to(r).as_posix(), "title": title(p), "original": original(p)}
                        for p in sources(r, slug)],
            "pending": sorted(p.name for p in inbox.glob("*") if p.is_file() and not p.name.startswith(".")),
            "failed": sorted(p.name for p in (inbox / "failed").glob("*")),
            "studio": (r / "studio" / slug / "index.html").exists(),
            "outputs": outputs(r, slug),
            "coming": (soon := coming(r, c["name"])),
            "focus": focus(soon),
            "results": scores(r / "studio" / slug / "results.json"),
            "ingest": self.ingester.state(slug),
            "making": self.ingester.making(slug),
            "weak": [{"path": p, "title": title(r / p) if (r / p).exists() else p, **e}
                     for p, e in sorted(scores(r / "studio" / slug / "scores.json").items(),
                                        key=lambda x: x[1]["right"] / x[1]["total"])
                     if p not in daily_pick.not_tested(r, slug)][:5],
            "log": tail(inbox / ".ingest.log", 30),
        })

    def search(self, slug, q, wiki=False):  # full text, case-insensitive; one snippet around the first hit. No class + wiki = every class's wiki (home search)
        if slug or not wiki:
            if not find_class(self.root, slug):
                return self.fail(404, "No such class")
        cs = [find_class(self.root, slug)] if slug else classes(self.root)
        hits = []
        for c in cs:
            for p in (sorted((self.root / "wiki" / c["slug"]).glob("*.md")) if wiki else sources(self.root, c["slug"])) if q else []:
                text = p.read_text(errors="replace")
                i = text.lower().find(q)
                if i >= 0:
                    snippet = " ".join(text[max(0, i - 60):i + len(q) + 60].split())
                    hits.append({"path": p.relative_to(self.root).as_posix(), "title": title(p), "snippet": snippet, "class": c["name"]})
        self.send_json(hits)

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def fail(self, status, message):
        self.send_json({"error": message}, status)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")  # new ingests show up on reload
        super().end_headers()

    def log_message(self, *a):
        pass


def ask(prompt):
    """One `claude -p` on Ethan's claude.ai plan -> answer text, or (status, error) on failure."""
    # ponytail: env without ANTHROPIC_* so a stray API key can never bill per question; CLAUDE* vars break the child's login
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "CLAUDE"))}
    try:
        r = subprocess.run(CLAUDE, input=prompt, capture_output=True, text=True, env=env, cwd="/tmp", timeout=180)
    except subprocess.TimeoutExpired:
        return 504, "Claude took too long. Try again."
    if r.returncode or not r.stdout.strip():
        return 502, (r.stderr or r.stdout).strip()[-300:] or "Claude stopped without an answer. Try again."
    return r.stdout.strip()


def page_of(slug, source):
    return re.fullmatch(rf"wiki/{re.escape(slug)}/[\w.-]+\.md", source)


def classes(root):
    f = root / "classes.json"
    return json.loads(f.read_text()) if f.exists() else []


def scores(f):  # {wiki page: {right, total}}
    return json.loads(f.read_text()) if f.exists() else {}


def find_class(root, slug):
    return next((c for c in classes(root) if c["slug"] == slug), None)


def sources(root, slug):  # one .md per source; originals (PDFs) sit in files/
    return sorted((root / "raw" / slug).glob("*.md"))


def norm(label):
    return re.sub(r"[^a-z0-9]", "", label.lower())  # "MAT 19A" == "mat-19a"


def coming(root, name):  # this class's syllabus items from today on, by date
    return [i for i in syllabus(root, name) if i["days"] >= 0]


def syllabus(root, name):  # this class's syllabus items, past too, by date. Read from the cache file: never waits on Render
    try:
        rows = json.loads((root / ".planner-cache.json").read_text())["deadlines"]
    except (OSError, ValueError, KeyError):
        return []
    out = []
    for i in rows:
        try:
            days = (date.fromisoformat(i["due_date"]) - date.today()).days
        except (KeyError, ValueError):
            continue
        if norm(i.get("course_label", "")) == norm(name):
            out.append({**{k: i.get(k) for k in ("title", "type", "weight_pct", "due_date")}, "days": days})
    return sorted(out, key=lambda i: i["due_date"])


def next_up(items):  # class card: the next exam, else the next thing
    return next((i for i in items if i["type"] == "exam"), items[0] if items else None)


def focus(items):  # what to study for first: biggest grade weight inside 2 weeks (ties: soonest), else the next exam
    near = [i for i in items if i["days"] <= 14]
    return max((i for i in near if i["weight_pct"]), key=lambda i: i["weight_pct"], default=None) \
        or next((i for i in near if i["type"] == "exam"), None)


def syllabus_text(items):
    return "\n".join(f"{i['due_date']} (in {i['days']} days) {i['type']}: {i['title']}"
                     + (f", weight {i['weight_pct']:g}%" if i["weight_pct"] else "") for i in items) or "(nothing from the planner)"


def review(m, page, ok, today):  # spaced repetition by wiki page: right = wait longer (once a day), wrong = back tomorrow
    e = m.setdefault(page, {"box": 0})
    if not ok:
        e["box"] = 0
    elif e.get("up") != today.isoformat():
        e["box"], e["up"] = min(e["box"] + 1, len(INTERVALS) - 1), today.isoformat()
    e["due"] = (today + timedelta(days=INTERVALS[e["box"]])).isoformat()


def daily(root, slug):  # today's daily quiz, if made: {path, n, min} (+ done, for the home card)
    f = root / "studio" / slug / "daily" / f"{date.today()}.json"
    if not f.with_suffix(".html").exists():
        return None
    qs = scores(f).get("questions", [])
    path = f.with_suffix(".html").relative_to(root).as_posix()
    run = scores(root / "studio" / slug / "results.json").get(path, {})
    return {"path": path, "n": len(qs), "min": daily_pick.minutes(qs)} | ({"done": True} if run and run["done"] >= run["of"] else {})


def queue_daily(root, ingester, today, tried):  # one daily quiz per class, once a day (study.sh daily makes none if nothing is due)
    for c in classes(root):
        s = c["slug"]
        if tried.get(s) != today and any((root / "wiki" / s).glob("*.md")) \
                and not (root / "studio" / s / "daily" / f"{today}.html").exists():
            tried[s] = today
            exam = next((i for i in coming(root, c["name"]) if i["type"] == "exam"), None)
            ingester.add(s, "daily", f"--exam-in {exam['days']}" if exam else "")


def daily_loop(root, ingester):  # from 5 am, checked every 10 min: a Mac asleep at 5 makes it when it wakes
    tried = {}
    while True:
        if datetime.now().hour >= 5:
            queue_daily(root, ingester, date.today(), tried)
        time.sleep(600)


def raw_links(p):  # the sources a wiki page was written from, from its "> Raw:" line
    head = p.read_text(errors="replace")[:3000]
    return re.findall(r"\]\(\.\./\.\./(raw/[^)\s]+)\)", next((l for l in head.splitlines() if l.startswith("> Raw:")), ""))


def refresh_planner(root):  # every 30 min, in the background. A failure keeps the old cache
    import exam_dates
    while True:
        try:
            (root / ".planner-cache.json").write_text(json.dumps({"at": time.time(), "deadlines": exam_dates.fetch()}))
        except (SystemExit, OSError, ValueError, KeyError) as e:  # fetch() exits with a message on 401 / no network
            print("planner:", e, flush=True)
        time.sleep(1800)


PRIMARY = [".html", ".mp4", ".mp3", ".pdf", ".md"]  # which file of one output opens first
LABEL = {".pdf": "PDF", ".md": "Text", ".mp3": "Audio", ".mp4": "Video", ".html": "Page"}


def outputs(root, slug):  # the Study tab: one item per output (its other files beside it), newest first
    d, groups = root / "studio" / slug, {}
    for p in d.rglob("*"):
        if is_output(p):
            groups.setdefault(p.with_suffix(""), []).append(p)
    out = [output_card(root, d, sorted(files, key=lambda f: PRIMARY.index(f.suffix))) for files in groups.values()]
    return sorted(out, key=lambda o: -o["mtime"])


def is_output(p):  # video frames and the folder's index page are parts, not outputs
    return p.is_file() and p.suffix in PRIMARY and p.name != "index.html" and "frames" not in p.parts


def output_title(files):  # the page's <title>, else its markdown heading, else the file name
    f = files[0]
    if f.suffix == ".html":
        t = re.search(r"<title>(.*?)</title>", f.read_text(errors="replace")[:2000])
        if t and t.group(1):
            return t.group(1)
    md = next((x for x in files if x.suffix == ".md"), None)
    return title(md) if md else f.stem


def output_card(root, d, files):  # files: the one to open first, then the others
    f = files[0]
    return {"kind": f.relative_to(d).parts[0], "path": f.relative_to(root).as_posix(), "title": output_title(files),
            "date": f"{datetime.fromtimestamp(f.stat().st_mtime):%b %d}", "mtime": f.stat().st_mtime,
            "also": [{"path": x.relative_to(root).as_posix(), "label": LABEL[x.suffix]} for x in files[1:]]}


def read_json(f, size):  # the request body, or None if it is not JSON
    try:
        return json.loads(f.read(size) or b"{}")
    except ValueError:
        return None


def quiz_tally(run):  # {right, done, of} as ints, or None if any is missing or not a number
    try:
        return {k: int(run[k]) for k in ("right", "done", "of")}
    except (KeyError, TypeError, ValueError):
        return None


def mark_missed(m, source, ok, b):
    q = str(b["q"])[:1000]
    if ok:
        m.pop(q, None)
    else:
        m[q] = {k: str(b.get(k, ""))[:2000] for k in ("answer", "text", "section")} | {"source": source}


def daily_state(root, slug):  # home card: "ready", "done" or None
    d = daily(root, slug)
    if not d:
        return None
    return "done" if d.get("done") else "ready"


def deletable(r, slug, parts, p):  # only a file of this class in wiki/raw/studio, never a folder's index.html
    return (len(parts) >= 3 and parts[0] in ("wiki", "raw", "studio") and parts[1] == slug and ".." not in parts
            and p.is_file() and p.name != "index.html" and p.is_relative_to(r / parts[0] / slug))


def siblings(folder, stem):
    return [f for f in folder.glob(glob.escape(stem) + ".*") if f.is_file()]


def files_of(area, p):  # everything that goes with one item
    if area == "studio":  # one card = html + json + pdf + ...
        return siblings(p.parent, p.stem)
    if area == "raw":  # the source and its original PDF
        return [p] + siblings(p.parent / "files", p.stem)
    return [p]


def to_trash(r, files):
    trash = r / ".trash" / f"{datetime.now():%Y%m%d-%H%M%S}"
    for f in files:
        (trash / f.relative_to(r)).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(f, trash / f.relative_to(r))


def drop_index_row(idx, link):
    if idx.exists():
        idx.write_text("".join(l for l in idx.read_text().splitlines(True) if link not in l))


def original(p):
    f = next(p.parent.glob(f"files/{glob.escape(p.stem)}.*"), None)
    return f and f.relative_to(p.parents[2]).as_posix()


def slugify(text, n):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:n]


def title(p):
    with open(p, errors="replace") as f:
        for line in f:
            if line.startswith("# "):
                return line[2:].strip()
    return p.stem


def tail(p, n):  # the log only grows: read its end, not the whole file
    if not p.exists():
        return []
    with open(p, "rb") as f:
        f.seek(max(0, p.stat().st_size - 16384))
        return f.read().decode(errors="replace").splitlines()[-n:]


def unique(p):
    """p, or p-1, p-2, ... if it exists (never overwrite). Makes the parent folder."""
    p.parent.mkdir(parents=True, exist_ok=True)
    base, n = p, 1
    while p.exists():
        p = base.with_name(f"{base.stem}-{n}{base.suffix}")
        n += 1
    return p


def make_server(root, port, ingester=None):
    root = Path(root)
    return ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=str(root), ingester=ingester or Ingester(root)))


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 4323
    print(f"Class Wiki on http://localhost:{port}", flush=True)
    threading.Thread(target=refresh_planner, args=(ROOT,), daemon=True).start()
    ingester = Ingester(ROOT)
    threading.Thread(target=daily_loop, args=(ROOT, ingester), daemon=True).start()
    make_server(ROOT, port, ingester).serve_forever()
