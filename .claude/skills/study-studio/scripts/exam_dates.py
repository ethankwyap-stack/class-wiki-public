#!/usr/bin/env python3
"""Next (and previous) exam for a class, from course-planner.

Usage: exam_dates.py <class-slug>      e.g. exam_dates.py mat-19a
Prints JSON: {"class", "today", "previous": item|null, "next": item|null}

The key is read from ~/course-planner/.app-key at runtime and only ever sent
as a request header. Never print it.
"""
import json, os, re, sys, time, urllib.error, urllib.request
from datetime import date
from pathlib import Path

URL = os.environ.get("EXAM_API_URL", "https://course-planner-5dtj.onrender.com/api/deadlines")
KEY_FILE = Path(os.environ.get("EXAM_KEY_FILE", Path.home() / "course-planner" / ".app-key"))
EXAM = re.compile(r"midterm|final(?! (project|paper|essay))|exam", re.I)


def norm(label):
    return re.sub(r"[^a-z0-9]", "", label.lower())  # "MAT 19A" == "mat-19a"


def is_exam_of(i, cls):
    return norm(i.get("course_label", "")) == norm(cls) and (i.get("type") == "exam" or bool(EXAM.search(i.get("title", ""))))


def pick(items, cls, today):
    exams = sorted((i for i in items if is_exam_of(i, cls)), key=lambda i: i["due_date"])
    past = [i for i in exams if i["due_date"] < today.isoformat()]
    future = [i for i in exams if i["due_date"] >= today.isoformat()]
    return {"class": cls, "today": today.isoformat(),
            "previous": past[-1] if past else None, "next": future[0] if future else None}


def fetch():
    req = urllib.request.Request(URL, headers={"x-app-key": KEY_FILE.read_text().strip()})
    for attempt in (1, 2):  # Render free tier cold start: 30-60 s, so one retry with a long timeout
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)["deadlines"]
        except urllib.error.HTTPError as e:
            if e.code == 401:
                sys.exit("401: ~/course-planner/.app-key no longer matches APP_KEY on Render. Ask Ethan to re-sync it.")
            if attempt == 2:
                sys.exit(f"course-planner answered HTTP {e.code}")
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == 2:
                sys.exit(f"course-planner unreachable: {getattr(e, 'reason', e)}")
        time.sleep(5)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    today = date.fromisoformat(os.environ["EXAM_TODAY"]) if os.environ.get("EXAM_TODAY") else date.today()
    print(json.dumps(pick(fetch(), sys.argv[1], today), indent=2))


if __name__ == "__main__":
    main()
