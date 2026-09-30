# Class Wiki: Astro-Han LLM Wiki + NotebookLM-style study tools

## Context
Ethan wants a Karpathy-style LLM Wiki for his classes (lectures go in, a linked study wiki comes out and keeps improving).
We use the existing skill **Astro-Han/karpathy-llm-wiki** (MIT, 2,357 stars, pushed Jul 23 2026, 7 open issues) as the base.
It already does ingest, query, lint, and fact-checking (`scripts/check_evidence.py`, stdlib only, no network).
On top of it we add NotebookLM features he likes: slides, audio overview, visual outputs, quizzes, reports.
Plus fix 3 (quizzes + exam prep from real exam dates) and fix 5 (cheap model for ingest).
Hard rule: $0 cost, no new accounts, no API keys. All output generation runs through his local `claude` CLI and local tools.

## Layout (new folder `~/class-wiki`)
```
~/class-wiki/
  CLAUDE.md                      # schema: classes, conventions, which model per job
  raw/<class>/                   # immutable sources (upstream rule)
  wiki/<class>/  index.md log.md # upstream layout, untouched
  studio/<class>/                # our generated outputs (slides, audio, quizzes...)
  inbox/                         # drop lecture transcripts here
  .claude/skills/
    karpathy-llm-wiki/           # upstream, copied unmodified (easy to update later)
    study-studio/                # OUR skill: all NotebookLM features
      SKILL.md
      templates/quiz.html  templates/flashcards.html
      scripts/*.py + tests/
```
Upstream stays unmodified. All our changes live in `study-studio` + `CLAUDE.md`, so a future upstream update is a plain re-copy.

## Phase 0: Vet upstream in Docker (security rule)
1. `git clone` into scratchpad. Read `SKILL.md`, `references/*`, `scripts/check_evidence.py` (already seen: imports only re, sys, dataclasses, pathlib).
2. Run its tests inside Docker: `docker run --rm -v <clone>:/w -w /w python:3.12-slim python -m unittest discover tests` (or pytest if it needs it).
3. Pass → copy into `~/class-wiki/.claude/skills/karpathy-llm-wiki/`.

## Phase 1: Base wiki + fix 5 (cheap ingest)
- `~/class-wiki/CLAUDE.md`: class list (start with **MAT 19A**), topic dir names, "ingest and lint on Sonnet; outputs that need judgment (exam prep, reports) on Opus".
- `ingest.sh <class>`: headless batch ingest of everything in `inbox/`, runs `claude -p --model sonnet` (plus low effort flag if the CLI supports one; check `claude --help` at build time). Moves each file to `raw/<class>/` via the upstream flow, then runs `check_evidence.py`.
- Lecture source: `~/lecture-notes` only keeps transcripts in browser localStorage. Small add there: a **"Save .md" button** that downloads `lecture-<class>-<date>.md`. `ingest.sh` also picks up `~/Downloads/lecture-*.md`. (Reuse the existing transcript + timestamps output in `~/lecture-notes/app.js`.)

## Phase 2: study-studio skill (NotebookLM features)
One skill, one command each. Every output is grounded: it reads only `wiki/<class>/` pages and cites them, same rule as upstream Query.

| Command | NotebookLM match | How ($0) | Output |
|---|---|---|---|
| `/study quiz <class> [topic]` | Quizzes | Claude writes quiz JSON (MCQ + short answer, each with cited page + explanation); `build_quiz.py` injects it into `templates/quiz.html` | one self-contained `.html`, opens offline |
| `/study cards <class>` | Flashcards | same JSON→HTML pattern, with simple spaced repetition (Leitner boxes) saved in localStorage | `.html` |
| `/study slides <class> [topic]` | Slide decks | Claude writes Marp markdown; `npx @marp-team/marp-cli` → PDF + HTML | `.pdf`, `.html` |
| `/study audio <class> [topic]` | Audio Overview | Claude writes a 2-host podcast script (≈8-12 min); `make_audio.py` voices each line with **Kokoro-82M** (Apache-2.0, local, ~330 MB, vetted in Docker first), 2 voices, ffmpeg joins → mp3. Fallback: macOS `say` | `.mp3` + script `.md` |
| `/study video <class> [topic]` | Video Overview | reuse slides PDF + audio; ffmpeg timed slideshow | `.mp4` |
| `/study map <class>` | Mind map | Claude writes nested markdown outline; `npx markmap-cli` → interactive zoomable HTML | `.html` |
| `/study report <class> <kind>` | Reports | kinds: `study-guide`, `briefing`, `faq`, `timeline`, `glossary` | `.md` (optionally a styled `.html`) |
| `/study table <class> <question>` | Data tables / visual structured output | comparison/formula tables as HTML, charts via inline SVG | `.html` |
| `/study exam <class>` | (fix 3, beyond NotebookLM) | reads real exam dates from course-planner, builds exam-prep pack for the next exam: topics covered since last exam, weak spots, practice quiz, 1-page cheat sheet | folder of the above |

Shared options on every command: `--audience` (e.g. "explain like I'm new"), `--length short|normal|long`, `--focus "<topic>"` (NotebookLM's "customize").

### Fix 3 details
- After each ingest, `ingest.sh` auto-runs `/study quiz` for that lecture (5 questions) → `studio/<class>/quizzes/`.
- `exam_dates.py`: `GET https://course-planner-5dtj.onrender.com/api/deadlines` with the key from `~/course-planner/.app-key` (read at runtime, never copied). Picks the next item whose title looks like midterm/final. Handles Render's 30-60 s cold start with one retry.

### Extra improvements (my picks)
- **Weak-spot tracking:** quiz/flashcard pages keep a local score per wiki page; a "Copy results" button → paste back → `/study exam` focuses on low scores.
- **Studio index:** `studio/<class>/index.html` lists every generated output with date, so everything is one click away (NotebookLM's "Studio" panel).
- **Viewer:** plain files work anywhere. Optional: Obsidian (free) opens `~/class-wiki` as a vault with graph view. No setup needed beyond "Open folder as vault".

## Critical files
- New: `~/class-wiki/CLAUDE.md`, `~/class-wiki/ingest.sh`, `~/class-wiki/.claude/skills/study-studio/{SKILL.md, templates/*.html, scripts/build_quiz.py, scripts/make_audio.py, scripts/exam_dates.py, tests/}`
- Copied unmodified: `~/class-wiki/.claude/skills/karpathy-llm-wiki/**`
- Small edit: `~/lecture-notes/app.js` + `index.html` (Save .md button), then Ethan deploys with `vercel --prod --yes`.

## Test first (per his rules)
- `python3 -m unittest` in `study-studio/tests/`, written and shown failing before each script:
  - `build_quiz.py`: JSON in → HTML contains every question, every cited page link, no network URLs.
  - `exam_dates.py`: fake deadlines list → picks the next midterm; no key in output.
  - `make_audio.py`: 2-line script → mp3 exists and duration > 0 (ffprobe).
- `WORKS.md` prove-lines for each `/study` command.

## Verification (end to end)
1. Ingest 1 real MAT 19A lecture transcript → wiki pages created, `check_evidence.py` shows 0 evidence errors.
2. Run each `/study` command on MAT 19A → open every output: quiz answers work offline, slides PDF opens, mp3 plays with 2 distinct voices, mind map zooms.
3. `/study exam MAT 19A` → names the Oct 16 midterm from course-planner.
4. Run `/greenlight` on `~/class-wiki` once all phases pass.

## Phases (Ethan gates each one)
0 Vet → 1 Base wiki + ingest → 2a Quiz + cards + reports → 2b Slides + map + table → 2c Audio + video (Kokoro vet) → 2d Exam prep + studio index. Stop after each for his OK.
