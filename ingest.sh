#!/bin/bash
# Usage: ./ingest.sh <class-slug>     e.g. ./ingest.sh mat-19a
# Converts inbox/<class>/ uploads (pdf, photos, YouTube links) to .md with prepare_inbox.py, then
# ingests inbox/<class>/*.md and ~/Downloads/lecture-<class>-*.md into wiki/<class>/,
# one file at a time on Sonnet, then lints. Quizzes: press Quiz on the Study tab.
set -uo pipefail
cd "$(dirname "$0")"
CLASS="${1:?usage: ./ingest.sh <class-slug>, e.g. mat-19a}"
SKILL=.claude/skills/karpathy-llm-wiki
CLAUDE=(claude -p --model sonnet --effort low --permission-mode acceptEdits)

# One ingest at a time, from the site or by hand: wiki/index.md and wiki/log.md are shared.
LOCK=inbox/.ingest.lock
until mkdir "$LOCK" 2>/dev/null; do
  pid=$(cat "$LOCK/pid" 2>/dev/null)
  if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then rm -rf "$LOCK"; continue; fi  # holder died
  echo "Another ingest is running. Waiting..."; sleep 15
done
echo $$ > "$LOCK/pid"
trap 'rm -rf "$LOCK"' EXIT

mkdir -p "inbox/$CLASS"
python3 prepare_inbox.py "$CLASS"
OUT=$(mktemp)

shopt -s nullglob
files=(inbox/"$CLASS"/*.md ~/Downloads/lecture-"$CLASS"-*.md)
[ ${#files[@]} -eq 0 ] && { echo "Nothing to ingest. Put files in inbox/$CLASS/ or ~/Downloads/lecture-$CLASS-*.md"; exit 0; }

for f in "${files[@]}"; do
  echo "== Ingesting $f"
  # ponytail: one claude call per file, serial on purpose (upstream: index/log are shared state)
  # prompt goes on stdin: --allowedTools/--add-dir take many values and would swallow it
  if "${CLAUDE[@]}" --allowedTools "Read Write Edit Glob Grep" \
      --add-dir "$(dirname "$f")" <<< "Use the karpathy-llm-wiki skill ($SKILL/SKILL.md) to Ingest the class source at $f.
Topic directory: $CLASS (raw/$CLASS/, wiki/$CLASS/). Follow CLAUDE.md in this folder.
The source is a lecture transcript, PDF text, photo transcription, video notes or a set of test questions: Source = the URL in the file if it has one, else the file name, Published = the date in the file name if it has one, else Unknown.
Save the raw file with the text unchanged. Then triage and compile as the skill says.
Past questions: if the source is test, quiz, homework or practice questions (Canvas, an old exam), do not make a page per question or one page for the whole test, and never write an answer choice as a fact unless the source marks it correct. For each question, find the concept it tests and add it to that concept's page (create a page per concept if none covers it, e.g. exponent rules, adding fractions, factoring: questions on different skills go to different pages) under a '## Past questions' section: one top-level '- ' bullet per question with the question in short, how it is asked (definition, apply to a new case, find the mistake, compare, calculate), and the correct answer only if the source marks it; cite this source. Graded work (his own answers plus a score, maybe on another page: match the part numbers): an answer with full points is correct; for a part that lost points write 'Ethan got this wrong', never his answer as a fact. Write every other fact of the page from teaching sources only.
No repeats: before you create a wiki page, grep wiki/$CLASS/ for its key terms. If a page already covers the concept, Update that page (merge the new facts, add this source to its Sources and Raw lines). Create a page only for a concept no page has. Never restate a fact another page holds: link to that page. Update wiki/index.md and wiki/log.md.
Last line of your answer: WIKI_PAGES: <comma-separated wiki/$CLASS/*.md paths you created or updated>, or WIKI_PAGES: none" \
      | tee "$OUT" && grep -q "WIKI_PAGES:" "$OUT"; then
    mv "$f" "inbox/done/$CLASS/"  # no auto-quiz: one per file piled up repeats; quizzes come from the Study tab
  else
    echo "!! Ingest failed for $f (moved to inbox/$CLASS/failed/, use Retry)"
    mkdir -p "inbox/$CLASS/failed" && mv "$f" "inbox/$CLASS/failed/"
  fi
done

echo "== Lint"
python3 overlap.py "$CLASS"  # pages that share many words: merge them by hand or in the next ingest
python3 "$SKILL/scripts/check_evidence.py" . | tail -15
