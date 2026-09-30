# WORKS.md — Class Wiki

Prove-lines. Each is a thing you do and what you should see.

- **Ingest**: put a transcript in `inbox/` → `./ingest.sh mat-19a` → new pages in `wiki/mat-19a/`, rows in `wiki/index.md`, an entry in `wiki/log.md`, lint ends `0 evidence error(s)`.
- **Quiz**: `/study quiz mat-19a` → `.html` opens offline; click an answer → green/red + explanation + source link; "Copy results" copies per-page scores. Test: `test_build_quiz`.
- **Cards**: `/study cards mat-19a` → click to flip, Again/Got it moves boxes; reload keeps progress; a missed card is due again at once.
- **Slides**: `/study slides mat-19a` → `.pdf` + `.html`, dark theme, math renders, last slide lists sources.
- **Audio**: `/study audio mat-19a` → `.mp3` with two different voices. Test: `test_make_audio` (Kokoro in Docker + `say` fallback, duration > 1 s).
- **Video**: `/study video mat-19a` → `.mp4`, slides change with the talk, length = audio length. Test: `test_make_video`.
- **Map**: `/study map mat-19a` → `.html` mind map, zoom and fold work offline.
- **Report**: `/study report mat-19a study-guide` → `.md` with a cited page after each section.
- **Table**: `/study table mat-19a "compare the limit laws"` → `.html` table with sources, no network URLs.
- **Exam**: `/study exam mat-19a` → folder named for the next exam (Midterm Exam 1, 2026-10-16 as of Sep 24) with plan.md, practice quiz, cards, cheat-sheet.md. Test: `test_exam_dates` (key never in output; 401 message).
- **Studio index**: `studio/mat-19a/index.html` lists every output newest first. Test: `test_build_index`.
- **Site**: open http://localhost:4323 → wiki index; click an article → it renders; its `.md` links stay in the site, Raw links open the lecture; menu shows `<class> studio` once a studio index exists; `/CLAUDE.md` gives 404. Test: `test_serve`.

- **Classes**: home → "New class" → type `PHY 9A` → Add → opens its page; card shows on home. Test: `test_add_class`.
- **Upload**: class page → drop a PDF or AirDropped iPhone photo (HEIC) → "Reading your sources…" → a few minutes later new wiki pages, originals under Sources. Tests: `test_upload_then_auto_ingest`, `test_prepare_inbox`.
- **YouTube**: paste a link → Add → page with on-screen notes + transcript. Non-YouTube link → "Only YouTube links". Test: `test_youtube_link`.
- **Failed file**: shows ✗ + "Retry failed". Test: `test_retry_failed`.
- **Math**: `$\lim_{x \to 2}$` in a wiki page shows as real math.

## Proved 2026-09-25 (scratch copy, bare launchd-like env, real Claude)
- New class PHY 9A made; iPhone HEIC board photo + PDF → 2 pages + 2 quizzes in 130 s, lint 0 evidence errors, math renders.
- YouTube h_Rf_2OeSJU (4:55) failed on old yt-dlp → upgraded → Retry → 50 frames + captions → page "The Limit of a Function", 0 evidence errors.
- Writes without the header or with a foreign Host → 403. `claude -p` runs from a launchd job.

## Proved 2026-09-24 (made-up test lecture, scratch copy of the project)
- ingest.sh: 50 s, 1 page `wiki/mat-19a/limits.md`, index + log updated, 5-question quiz, lint 0/0/0.
- quiz, cards, map, table, slides (html), exam quiz + cards, studio index: opened in Chrome with network blocked → 0 errors, 0 requests.
- slides pdf + html, map, table, report (7 citations), exam (real Midterm Exam 1 2026-10-16 from course-planner) all built.
- video: 6 slides + 80 s Kokoro mp3 (Docker, no fallback) → 80.1 s mp4, slide 4 on screen at 0:40.
- NOT CHECKED: that the two Kokoro voices sound different (needs ears); a real MAT 19A transcript.

- **Study tools buttons**: class page → Study tools → click Flashcards → "Making: Flashcards" → a minute later a new deck in "Open study outputs". Test: `test_make_study_output`.
- **Weak spots**: answer quiz questions on the site (opened from "Open study outputs") → class page shows "Weak spots" with right/total per page; `studio/<class>/scores.json` grows. Test: `test_quiz_scores_saved_per_page`.
- **Stop**: click Flashcards → "Making: Flashcards  Stop" → click Stop → the row goes away, the log says `##### cancelled`, no `claude -p` left running. Test: `test_cancel_study_output`.
- **Ask Claude chat**: class page → "Ask Claude" (bottom right) → ask "What is a function?" → an answer from the wiki with the page cited, in a few seconds. Runs `claude -p` on the claude.ai plan: the child gets no `ANTHROPIC_*` vars, and `--safe-mode` skips CLAUDE.md and hooks. Test: `test_chat_uses_plan_not_api_key`. Proved 2026-09-26 on the live site (2.7 s, cited `what-is-a-function.md`).
- **Quiz/cards aim at weak spots**: with `studio/<class>/scores.json`, about half of a new quiz or deck comes from the weakest pages (study-studio SKILL.md quiz step 1). Prompt rule only; no test.
- **Recall / summary**: open a wiki page → "Recall from memory" → page hides → type what you remember → "Check with Claude" → feedback + the page comes back; the answer counts in Weak spots. Test: `test_grade_typed_answer_and_recall`. Proved 2026-09-26 live (8.6 s, PSC recall graded wrong with a missed-ideas list).
- **Pre-test**: a page with no scores opens with "Test yourself first" (3 questions from its quizzes) → "Show answers and the page". Test: `test_pretest_questions_from_existing_quizzes`. Seen in headless Chrome 2026-09-26.
- **Typed quiz answers + retry**: short question → type → Claude grades; a miss comes back once as "Try again"; the source link opens the page at the section. Tests: `test_typed_answers_graded_and_retried`, `test_source_links_to_section`, `test_source_link_to_section`.
- **Cards**: flip does nothing until you type a guess; your guess shows above the back.
- **Quiz me**: chat → tick "Quiz me" → Send empty → Claude asks → answer → graded, next question, scores.json grows. Test: `test_quiz_me_chat_saves_scores`. Proved live 2026-09-26.
- **Re-read warning**: open a page, leave, open it again without a recall → "Try recall first" note.
- **Help nudge**: a weak spot under 50% after 10+ answers shows "Ask for help now". Rule only; no test.
- **New-situation quizzes + challenge**: a new quiz uses new examples, not the lecture's numbers; the last 2 questions say "Challenge" in gold with a Hint button. Test: `test_challenge_label_and_hint` (the new-example rule is prompt only).
- **Missed questions**: miss a quiz question → class page "Missed questions" shows it, your answer, the answer, and the section link; get it right in a later quiz → it goes away. Test: `test_missed_questions_list`.
- **Section flash**: a source link opens the page and the whole section (heading to next heading) flashes yellow, then fades. Seen in headless Chrome 2026-09-26 (4 elements, stops before See Also).
- **Redesign (2026-09-26, preview branch)**: class page has tabs Wiki / Sources / Study / Progress (`#/c/<slug>/<tab>`); Study lists every output as a card with type chips (All, Quizzes, Flashcards...); a card opens the quiz/deck/slides inside the site (`#/view/<path>`); every inner page has a Back button and breadcrumb. Tests: `test_outputs_listed_by_kind_with_titles`, `test_page_title_is_the_deck_title`. Seen in headless Chrome, light and dark.
- **Score on the card**: finish a quiz opened from the Study tab → its card shows `7/10` (green 80%+, red under 50%; `3/10 done` while unfinished). Kept in `studio/<class>/results.json`. Tests: `test_quiz_run_score_shown_on_card`, `test_quiz_sends_its_tally_for_the_card`.
- **Delete**: hover a card, source or wiki row → ✕ → confirm → the item (all files of one card; a source with its original PDF) moves to `.trash/<time>/`; a wiki page also loses its row in `wiki/index.md` and its scores. Refuses other paths. Tests: `test_delete_moves_to_trash_and_tidies`, `test_delete_refuses_other_paths`. Undo: move the file back from `.trash/`.
- **Sources fold**: Sources tab → "Your sources ▾" closes and opens the list.
- **Syllabus in the wiki**: class cards and the class page show the next exam (days, % of grade). The Deadlines tab lists the syllabus items, flags the biggest grade inside 14 days ("Study for this first"), and Progress marks weak spots when an exam is 14 days or less away. Study → "Quiz: next exam" / "Flashcards: next exam" (`--exam next`, pages after the last exam). Ask Claude gets the syllabus. Data = planner, cached in `.planner-cache.json` (refreshed every 30 min, page loads never wait on Render). Tests: `test_syllabus_comes_from_planner_by_class_name`, `test_syllabus_missing_is_quiet`, `test_chat_knows_the_syllabus`.
- **Calendar**: top right "Calendar" → month grid of all classes' deadlines (exams bold, class colors, ← Today → to move). Test: `test_calendar_has_every_class_past_and_future`.
- **Site search + no repeats**: home page search box finds wiki pages in every class (test: `test_search_wiki_across_all_classes`). `python3 overlap.py psc-001` lists pages on the same topic (tests: `tests/test_overlap.py`). Ingest merges into existing pages instead of writing a repeat (prompt in `ingest.sh`; NOT run end to end: needs a real ingest).
- NOT CHECKED: `--exam next` end to end (a real headless quiz run); a click-through in a real browser by Ethan.
- **Daily review + Quiz tab**: each morning a short quiz per class from due, new and missed pages, never a repeated question, 15 min at most (tests: `test_daily_pick.py`, `test_review_boxes`, `test_daily_queued_once_a_day_per_class_with_pages`, `test_class_detail_shows_todays_daily_quiz`). Real run 2026-09-26: `./study.sh psc-001 daily` → 6 questions, about 9 min, all new situations. Quiz tab ticks lectures/topics → `--pages` (test: `test_page_raw_links`, `test_study_topic_fits_many_pages`). NOT CHECKED: the 5 am timer on a real morning; a click-through by Ethan.
- **Phone over Tailscale**: https://<your-mac>.<tailnet>.ts.net:4323 (tailnet only). From the tailnet URL: `/` 200, `/api/classes` 200, `/serve.py` 404, a write without `X-Class-Wiki` 403. Tests: `test_own_tailnet_name_allowed`, `test_tailnet_name_from_cli`. Ethan opened it on his phone 2026-09-26: works.
- **Past test questions**: a Google-Doc-style PDF (39 typed words + a Canvas screenshot with 2 questions) → `prepare_inbox.py` kept the typed text and added `## Text in pictures` (both questions, every choice, the green "Correct Answer" marks) → real `ingest.sh psc-001` in a scratch copy put both under `## Past questions` on the correlation page, with only the marked answers; no wrong choice written anywhere; 0 evidence errors. `daily_pick` put that page first among new pages (`tested`). Site: "On a test" pill + Quiz tab "Past test concepts" button (screenshots). Tests: `test_pdf_with_pictures_keeps_its_text_and_adds_what_claude_reads_in_the_pictures`, `test_tested_counts_bullets_under_past_questions`, `test_new_pages_with_past_questions_come_first`. NOT CHECKED: a quiz made from the button (a real headless quiz run); Ethan's own Canvas upload.
