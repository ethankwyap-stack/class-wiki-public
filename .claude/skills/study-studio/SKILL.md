---
name: study-studio
description: "NotebookLM-style study outputs from the class wiki: quiz, flashcards, slides, 2-host audio overview, video overview, mind map, reports, tables, and exam prep from real exam dates. Triggers: '/study <command> <class>', 'make a quiz for', 'flashcards for', 'slides for', 'podcast/audio overview', 'mind map', 'study guide', 'exam prep', 'cheat sheet'."
---

# Study Studio

Turns `wiki/<class>/` into study material. Project root = `~/class-wiki` (where CLAUDE.md lives).
Scripts: `.claude/skills/study-studio/scripts/` (call it `$S` below). Run every command from the project root.

## Grounding rule (every command)

- Read `wiki/index.md`, then only `wiki/<class>/*.md` pages. Never use raw/ directly and never add facts from your own knowledge.
- Every question, card, slide, script segment, and report section cites the wiki page it came from (project-root-relative path, e.g. `wiki/mat-19a/limits.md`).
- A topic the wiki does not cover: say so and stop. Do not fill the gap from memory.
- `[topic]` or `--focus "<topic>"` narrows to pages about that topic (search the index and full text, synonyms included).
- `--pages a.md,b.md` narrows to exactly those pages (ingest.sh uses this).
- Not tested: pages named in the class's `"not_tested"` list in `classes.json` (e.g. how-to-study advice) are never used for quiz, daily, cards, sheet or exam, and never count as weak spots. Other outputs (slides, audio, map, report) may use them.
- Test scope: a class page named `*-test-scope.md` (e.g. `wiki/psc-001/unit-1-test-scope.md`, the instructor's study guide) sets what the test asks and how deep. Quiz, daily, cards, sheet and exam read it first and ask only at that depth: a general term listed (e.g. "transmitters") = ask what it is and how it works, never the specific examples under it that the guide does not list; locations only where the guide says so; never ask to recall a researcher's name that is not on the guide (naming the study in the question stem is fine). A guide topic the wiki has no page for: say so in the output.

## Options (all commands)

- `--audience "<who>"`: tone and depth, e.g. "explain like I'm new", "exam cram". Default: a UC Davis student taking the class.
- `--length short|normal|long`: quiz 5/10/20 questions; cards 10/25/50; slides 6/12/20; audio ~4/8/12 min (~130 spoken words per minute).
- `--focus "<topic>"`: same as `[topic]`.
- `--exam next` (quiz, cards and sheet): scope to the next exam, as in exam step 2. Run `python3 $S/exam_dates.py <class>` (may take 60 s; never print `~/course-planner/.app-key`). No `next` exam: say so and stop.
  Pages = lectures after `previous.due_date` up to today (all pages if no previous exam). Put the exam name in the title, e.g. "Midterm 1 practice". Weak spots come first as usual.

## Output paths

`studio/<class>/<kind>/<YYYY-MM-DD>-<slug>.<ext>`, slug = topic or `all`. Kinds: daily, quizzes, cards, slides, audio, video, maps, reports, tables, sheets, exam.
After any command, run `python3 $S/build_index.py <class>` and give Ethan the output path(s) plus `studio/<class>/index.html`.

## Commands

### quiz — `/study quiz <class> [topic]`
1. Write `studio/<class>/quizzes/<date>-<slug>.json`:
   `{"title", "class", "questions": [{"type":"mcq","q","choices":[...],"why":[...],"answer":<0-based index>,"explain","source","section"} | {"type":"short","q","answer","explain","source","section","challenge"?,"hint"?}]}`
   `section` = the exact `## ` heading text on the source page the answer comes from (the source link opens the page there).
   About half mcq, half short. Short = recall: Ethan types the answer and Claude grades it, so keep `answer` to one clear idea. Wrong choices must be plausible mistakes, not jokes. `why` = one line per choice, same order: for a wrong choice, the mistake that leads to it and why it fails (Ethan sees it when he picks it); `""` for the right one. Test understanding, not trivia.
   New situations, not chopped-up notes: find the concepts on each page, then write NEW examples for them. Never reuse the
   lecture's own numbers, names, or examples (a coffee shop lecture → ask about a gym, a food truck, a phone plan). Ask each
   concept a different way: apply it, explain why, find the mistake in a wrong answer, compare two ideas, predict what changes.
   Each question gives every fact it needs (no "in the lecture..."). `source` + `section` still point to where the concept is taught.
   Challenge: the last 2 questions (1 for `--length short`) are `"type":"short","challenge":true` with a one-line `hint` that
   does not give the answer. Several steps, or two concepts mixed (from two pages if you can), or a "why"/"what if" question.
   Weak spots: if `studio/<class>/scores.json` exists, about half the questions come from the in-scope pages with the lowest right/total (see exam step 3). No file, or no scored page in scope: spread evenly.
   Past questions: a page with a `## Past questions` section was on a real test (Canvas, old exams). Give each such in-scope
   page at least one question, more than an untested page, and ask it the way the teacher did (each bullet says how it was
   asked: definition, apply, find the mistake, compare, calculate), in a new situation. Never copy or lightly reword a past question. A bullet that says 'Ethan got this wrong': ask that concept first.
   Difficulty ramp (pages with 5+ answers): above 80% right → harder questions (apply it to a new case, explain why). Below 50% → basic definition questions, plus questions from the pages it builds on (its See Also links). Too hard is an undesirable difficulty.
2. `python3 $S/build_quiz.py <json> studio/<class>/quizzes/<date>-<slug>.html --kind quiz`
3. Keep the JSON next to the HTML (it is the source; rebuild the page from it any time).

### daily — `/study daily <class>` (the site makes one each morning)
Spaced repetition: a page comes back just before Ethan would forget it. Not a random quiz, and never padded.
1. `python3 $S/daily_pick.py <class>`, plus `--exam-in N` if the command has it (the site adds it when an exam is near: new pages come faster). `NOTHING DUE` → say so and stop: write no file.
   JSON: `concepts` (today's question slots), `due` (pages he has seen, due today), `new` (pages never tested; ones with past test questions first), `missed` (questions he got wrong), `avoid` (every question ever asked on these pages), `tested` (picked pages that were on a real test).
   A concept = one `## ` heading on a wiki page. `concepts` gives each page's least-asked headings, so every concept on a page gets its turn.
2. Write `studio/<class>/daily/<today>.json`, same format and rules as quiz (new situations, half mcq/half short), title "Daily review · <Mon D>":
   - Exactly one question per `concepts` entry, testing THAT heading's idea, with its `source` and `section` copied exactly. Never two questions on one concept. A `missed` slot: the idea of its `q`, asked a NEW way.
   - No repeats: never reuse or lightly reword a question in `avoid`. New situation, new angle (apply, why, find the mistake, compare, predict).
   - `tested` pages (a `## Past questions` section): ask them the way the teacher did, as in quiz step 1.
   - Mix the pages; do not group questions by page. Last question: a challenge that joins two pages, if there are 2+. It uses the slot of one of the two concepts (its `section`) and builds on another listed one; it is not an extra question.
   - Only what is due. Fewer questions is fine; never add one to fill time.
3. `python3 $S/daily_pick.py <class> --check <json>`: over 15 minutes → drop the least important `new` questions; "two questions test one concept" → rewrite one onto an unused concept from the list. Check again until it passes.
4. `python3 $S/build_quiz.py <json> studio/<class>/daily/<today>.html --kind quiz`, then build_index.py.

### cards — `/study cards <class> [topic]`
Same as quiz (weak spots, difficulty ramp) with `{"title","class","cards":[{"front","back","source"}]}`, `--kind cards`, into `cards/`. One fact per card. Front = question or term (in a new situation when it can be, as for quiz), back ≤ 25 words.
Progress (Leitner boxes) is kept in the browser, per deck title: re-running with the same title keeps progress.

### slides — `/study slides <class> [topic]`
1. Write `studio/<class>/slides/<date>-<slug>.md`: start with the contents of `templates/slides-header.md`, then slides split by `---`.
   One idea per slide, ≤ 6 bullets, math in `$...$`. Last slide: "Sources" listing the wiki pages.
2. `npx -y @marp-team/marp-cli@4 <md> --pdf --allow-local-files` and `npx -y @marp-team/marp-cli@4 <md> --html`.

### audio — `/study audio <class> [topic]`
1. Write the script `studio/<class>/audio/<date>-<slug>.md`: a `# Title` line, then only lines starting `A:` (host who explains) or `B:` (curious host who asks, pushes back, sums up).
   Natural talk, short turns, no stage directions, spell out math in words ("x squared", not `x^2`). End with a 3-point recap. Put `[slide N]` lines in only when a video will be made from it.
   After the dialogue, a `## Sources` list (not spoken).
2. `python3 $S/make_audio.py <script.md> studio/<class>/audio/<date>-<slug>.mp3` (Kokoro in Docker, ~1 s of work per 1 s of audio; falls back to macOS `say` if Docker is down). Tell Ethan how long it will take before running a long one.

### video — `/study video <class> [topic]`
1. Make slides (above) and an audio script with `[slide N]` markers that match the slide numbers.
2. `npx -y @marp-team/marp-cli@4 <slides.md> --images png --allow-local-files -o studio/<class>/video/frames/<slug>/deck.png`
3. make_audio.py for the mp3, then `python3 $S/make_video.py studio/<class>/video/frames/<slug> <mp3> <script.md> studio/<class>/video/<date>-<slug>.mp4`

### map — `/study map <class> [topic]`
Write `studio/<class>/maps/<date>-<slug>.md` as a nested heading/bullet outline (class → topics → concepts → key facts, ≤ 8 words per node, link nodes to wiki pages with relative links `../../../wiki/<class>/<page>.md`).
Then `npx -y markmap-cli@0.18 <md> --no-open --offline -o studio/<class>/maps/<date>-<slug>.html`.

### report — `/study report <class> <kind>`
No kind given: `study-guide`. Kinds: `study-guide` (key ideas, worked examples, common mistakes), `briefing` (1 page, most important points first), `faq` (10-20 Q&A), `timeline` (lecture-by-lecture what was covered), `glossary` (term → 1-line definition).
Write `studio/<class>/reports/<date>-<kind>.md`. Cite a page after each section. Use **Opus** judgment here: if running on a smaller model, say so.

### table — `/study table <class> "<question>"`
No question given: a formula and definition sheet for the whole class.
Answer with a comparison/formula table as one self-contained `studio/<class>/tables/<date>-<slug>.html` (same dark style as the quiz template: copy its `:root` and body CSS). Add a source column or footnotes. Charts: inline SVG only. No network URLs.

### sheet — `/study sheet <class> [topic]`
A DRAFT of the one double-sided letter notes sheet the exam allows. Ethan copies it out by hand (writing it is the studying), so pick what earns space; do not summarize everything.
1. Scope: `--exam next` as in exam step 2, else all pages (or the topic).
2. Rank what goes on, most important first: pages he gets wrong (`scores.json`, lowest right/total, `why:"weak"`), concepts in `missed.json` (`"missed"`), pages with `## Past questions` (`"tested"`), then the rest (`"core"`). Leave out what he gets right 80%+ of the time after 5+ answers: he already knows it.
3. Content: definitions, distinctions that get mixed up (A vs B), names and what they showed, steps, formulas. Terse phrases, not sentences. No examples from the lecture: he needs the rule, not the story.
4. Write `studio/<class>/sheets/<date>-<slug>.json`: `{"title","class","sections":[{"head","why","source","items":[...]}]}`, one section per concept, each citing its wiki page. Title: exam name + "notes sheet".
5. `python3 $S/build_sheet.py <json> studio/<class>/sheets/<date>-<slug>.html`. Too many words → drop the lowest-ranked sections (never shorten a weak one) and rebuild.

### exam — `/study exam <class>`
1. `python3 $S/exam_dates.py <class>` (may take 60 s: Render cold start). Never print or open `~/course-planner/.app-key`.
   Exit message about 401 → stop and tell Ethan the key has drifted. No `next` exam → say so and stop.
2. Scope = wiki pages whose lectures fall after `previous.due_date` (or all pages if none) up to today. Use the raw file dates in each page's Raw field.
3. Weak spots = lowest right/total pages in `studio/<class>/scores.json` (`{"wiki/<class>/<page>.md": {"right", "total"}}`, saved by the site from every quiz and flashcard answer). No file: ask Ethan to paste his quiz "Copy results" scores, or (headless) go without.
4. Build into `studio/<class>/exam/<next.due_date>-<next title slug>/`:
   - `plan.md`: exam name + date + days left, topics in scope, weak spots, a day-by-day plan to the exam date.
   - practice quiz (`--length long`, weighted to weak spots) and flashcards via build_quiz.py.
   - `cheat-sheet.md`: 1 page, formulas and definitions only.
   Use **Opus** judgment here.
