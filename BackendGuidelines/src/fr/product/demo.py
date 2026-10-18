"""`fr-demo`: the app flow on invented sample data, printed as text. Nothing touches your real tasks or calendar.

  uv run fr-demo                 # estimates, a few recorded lengths, three schedules, a pick
  uv run fr-demo --llm "No work after 11pm, gym MWF 7-8:30am"   # also parse constraints with Claude (needs the claude CLI)
"""
from __future__ import annotations

import argparse
import tempfile
from collections import defaultdict
from datetime import datetime, timedelta

from .service import Engine

NOW = datetime(2026, 10, 19, 8, 0)  # a Monday


def sample() -> tuple[list[dict], list[dict]]:
    def t(i, title, bucket, due=None, progress=0, done=False):
        d = dict(id=f"demo-{i}", title=title, horizon="shortTerm", bucket=bucket, isDone=done, progress=progress)
        if due:
            d["dueDate"] = due
        return d
    todos = [t(1, "CS 2110 A4", "assignments", "2026-10-22T23:59:00"),
             t(2, "MATH 2940 problem set 7", "assignments", "2026-10-23T23:59:00", progress=1),
             t(3, "ENGL 1170 reading: Beloved ch. 4-6", "readings", "2026-10-21T09:00:00"),
             t(4, "PHYS 2213 lab report", "assignments", "2026-10-27T23:59:00"),
             t(5, "ENGL 1170 essay draft", "assignments", "2026-10-30T23:59:00"),
             t(6, "email advisor about research", "emails")]
    events = []
    for d in range(14):
        day = NOW.date() + timedelta(days=d)
        if day.weekday() in (0, 2, 4):
            events.append(dict(title="CS 2110 lecture", start=f"{day}T10:10:00", end=f"{day}T11:00:00", isAllDay=False))
            events.append(dict(title="MATH 2940 lecture", start=f"{day}T13:25:00", end=f"{day}T14:15:00", isAllDay=False))
        if day.weekday() in (1, 3):
            events.append(dict(title="PHYS 2213 discussion", start=f"{day}T11:15:00", end=f"{day}T12:05:00", isAllDay=False))
    return todos, events


def show(opt: dict, titles: dict[str, str], days: int = 5) -> None:
    print(f"\n  Option {opt['option']}: {opt['label']} - {opt['summary']}")
    by_day = defaultdict(list)
    for b in opt["blocks"]:
        by_day[b["start"][:10]].append(b)
    for day in sorted(by_day)[:days]:
        wd = datetime.fromisoformat(day).strftime("%a %d")
        items = ", ".join(f"{b['start'][11:]}-{b['end'][11:]} {titles[b['task_id']][:22]}" for b in by_day[day])
        print(f"    {wd}: {items}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="fr-demo")
    ap.add_argument("--llm", help="constraint text to parse with Claude Sonnet 5.5 (via the claude CLI)")
    a = ap.parse_args(argv)
    todos, events = sample()
    titles = {t["id"]: t["title"] for t in todos}
    with tempfile.TemporaryDirectory() as d:
        eng = Engine(d, steps=200_000)
        print("1. Your preliminary estimates: A4 2 h, problem set 3 h, reading 1 h, lab report 2 h, essay 4 h")
        for tid, m in zip(["demo-1", "demo-2", "demo-3", "demo-4", "demo-5"], [120, 180, 60, 120, 240]):
            eng.set_estimate(tid, m, at="2026-10-01T09:00")
        p0 = eng.predict(todos, NOW)
        print("   Friday plans with:", {titles[k][:18]: v["plan_minutes"] for k, v in p0.items()})
        print("2. Four past CS assignments you timed: each took about 1.6x your estimate")
        for k in range(4):
            past = dict(id=f"past-{k}", title=f"CS 2110 A{k}", bucket="assignments", isDone=True)
            start = datetime(2026, 9, 8, 9, 0) + timedelta(days=7 * k)
            eng.set_estimate(past["id"], 120, at=start.isoformat(timespec="minutes"))
            eng.record_actual(past, 190 + 10 * (k % 2), at=(start + timedelta(days=2, hours=12)).isoformat(timespec="minutes"))
        p1 = eng.predict(todos, NOW)
        a4 = p1["demo-1"]
        print(f"   CS 2110 A4: you said 2 h; Friday now expects {a4['p50']} min (p80 {a4['p80']} min, "
              f"from {a4['similar_recorded']} similar tasks)")
        q = eng.questions(todos, NOW)
        print("3. Friday would ask:", [x["title"] for x in q["estimates"]] or "nothing", "| lengths of:",
              [x["title"] for x in q["actuals"]] or "nothing")
        if a.llm:
            r = eng.parse_constraints(a.llm, todos, events, NOW)
            print("4. Parsed:", [c["paraphrase"] for c in r.get("constraints", [])], "questions:", r.get("questions"),
                  "unsupported:", r.get("unsupported"))
            if r.get("ok"):
                eng.confirm_constraints(r["pending_id"], [c["index"] for c in r["constraints"]])
        out = eng.plan(todos, events, NOW)
        print("5. Three schedules (first five days):")
        for opt in out["options"]:
            show(opt, titles)
        r = eng.pick(out["plan_id"], 1)
        print(f"\n6. You picked option 1; Friday learned from {r['picks']} pick(s).")


if __name__ == "__main__":
    main()
