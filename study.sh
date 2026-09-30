#!/bin/bash
# Usage: ./study.sh <class-slug> <kind> [topic]     e.g. ./study.sh mat-19a cards "limits"
# One /study command, headless. The site's "Make" buttons run this (one job at a time, after ingests).
# kind: daily quiz cards slides audio video map report table sheet exam. report/exam/sheet need judgment: Opus.
set -uo pipefail
cd "$(dirname "$0")"
CLASS="${1:?usage: ./study.sh <class-slug> <kind> [topic]}" KIND="${2:?kind}" TOPIC="${3:-}"
MODEL=sonnet; case $KIND in report|exam|sheet) MODEL=opus ;; esac
echo "== Making $KIND for $CLASS${TOPIC:+ ($TOPIC)} on $MODEL"
# prompt on stdin: --allowedTools takes many values and would swallow it
# Bash tool timeout 2 min by default: audio/video need ~1 s of work per 1 s of sound
BASH_DEFAULT_TIMEOUT_MS=3600000 BASH_MAX_TIMEOUT_MS=3600000 claude -p --model "$MODEL" --permission-mode acceptEdits \
  --allowedTools "Read Write Edit Glob Grep Bash(python3 .claude/skills/study-studio/scripts/*) Bash(npx -y @marp-team/marp-cli@4 *) Bash(npx -y markmap-cli@0.18 *)" \
  <<< "Use the study-studio skill (.claude/skills/study-studio/SKILL.md): /study $KIND $CLASS $TOPIC
You run headless from the site: nobody can answer questions, so use the defaults and finish.
You are already inside ./study.sh: never run ./study.sh or ask to. Do the skill's steps yourself.
Run every command in the foreground and wait for it (audio and video take minutes): never run_in_background, or the job ends before the file exists." | tail -5
