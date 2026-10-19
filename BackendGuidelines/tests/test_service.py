"""The app contract: Friday-shaped data in, three valid plans out; estimates, actual lengths, constraints and picks
are stored in the sidecar file and change what comes out. The LLM is replaced by a fixed parse here."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta

from fr.product import adapter
from fr.product.constraints import Parse
from fr.product.parse import Result
from fr.product.service import Engine

NOW = datetime(2026, 10, 19, 8, 0)  # a Monday


def _todos():
    def t(i, title, bucket, due=None, done=False, progress=0):
        d = dict(id=f"00000000-0000-0000-0000-00000000000{i}", title=title, horizon="shortTerm", bucket=bucket,
                 isDone=done, isStarred=False, createdAt="2026-10-15T12:00:00Z", progress=progress)
        if due:
            d["dueDate"] = due
        return d
    return [t(1, "CS 2110 A4", "assignments", "2026-10-22T23:59:00"),
            t(2, "MATH 2940 problem set 7", "assignments", "2026-10-23T23:59:00", progress=1),
            t(3, "ENGL 1170 reading: Beloved ch. 4-6", "readings", "2026-10-21T09:00:00"),
            t(4, "PHYS 2213 lab report", "assignments", "2026-10-27T23:59:00"),
            t(5, "email advisor about research", "emails"),
            t(6, "CS 2110 A3", "assignments", "2026-10-15T23:59:00", done=True)]


def _events():
    out = []
    for d in range(14):
        day = NOW.date() + timedelta(days=d)
        if day.weekday() in (0, 2, 4):
            out.append(dict(title="CS 2110 lecture", start=f"{day}T10:10:00", end=f"{day}T11:00:00", isAllDay=False))
        if day.weekday() == 1:
            out.append(dict(title="club meeting", start=f"{day}T19:00:00", end=f"{day}T20:00:00", isAllDay=False))
    out.append(dict(title="Fall break", start=f"{NOW.date()}T00:00:00", end=f"{NOW.date()}T23:59:00", isAllDay=True))
    return out


def _fake_parser(reply: dict):
    return lambda text, ctx: Result(Parse.model_validate(reply), reply, None, 0.0, 0.0, 1)


def test_adapter_reads_todo_list_tasks():
    tasks = adapter.tasks_from(_todos())
    assert [t.title for t in tasks][-1] == "email advisor about research"  # done task dropped
    by = {t.title: t for t in tasks}
    assert by["CS 2110 A4"].course == "CS 2110" and by["CS 2110 A4"].kind == "pset" and by["CS 2110 A4"].hard
    assert by["ENGL 1170 reading: Beloved ch. 4-6"].kind == "reading"
    assert by["PHYS 2213 lab report"].kind == "lab"
    assert by["email advisor about research"].kind == "email" and by["email advisor about research"].due is None
    assert by["MATH 2940 problem set 7"].progress == 0.25
    utc = adapter.local("2026-10-20T03:59:00Z")  # Todo List writes UTC; the engine plans in local wall time
    assert utc == datetime(2026, 10, 20, 3, 59) + (utc - datetime(2026, 10, 20, 3, 59))


def test_three_valid_options_and_pick_learning(tmp_path):
    eng = Engine(tmp_path, steps=60_000)
    out = eng.plan(_todos(), _events(), NOW)
    assert len(out["options"]) == 3 and out["options"][0]["label"] == "recommended"
    dt = datetime.fromisoformat
    lecture = [(dt(e["start"]), dt(e["end"])) for e in _events() if not e["isAllDay"]]
    for opt in out["options"]:
        assert opt["valid"] and not opt["late_tasks"]
        spans = sorted((dt(b["start"]), dt(b["end"])) for b in opt["blocks"])
        assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:]))  # no overlaps
        for s, e in spans:  # never on top of a timed event
            assert all(e <= ls or s >= le for ls, le in lecture)
    r = eng.pick(out["plan_id"], 2)
    assert r["picks"] == 1
    assert json.loads((tmp_path / "engine.json").read_text())["choices"][0]["chosen"] == 2


def test_recorded_lengths_move_predictions(tmp_path):
    eng = Engine(tmp_path)
    todos = _todos()
    a4 = todos[0]["id"]
    eng.set_estimate(a4, 120)
    before = eng.predict(todos, NOW)[a4]
    assert before["p50"] == 120  # no history: the estimate is the prediction
    for k in range(6):  # this student's CS problem sets take twice their estimate
        t = dict(id=f"past-{k}", title=f"CS 2110 A{k}", bucket="assignments", isDone=True)
        eng.set_estimate(t["id"], 120, at=f"2026-09-{10 + k:02d}T12:00")
        eng.record_actual(t, 240, at=f"2026-09-{11 + k:02d}T12:00")
    after = eng.predict(todos, NOW)[a4]
    assert after["p50"] > 180 and after["similar_recorded"] == 6
    q = eng.questions(todos, NOW, min_saving=0.0)
    assert any(x["task_id"] == todos[5]["id"] for x in q["actuals"])  # the finished A3 was never timed
    # at most two "how long did it take?" questions a week (E024)
    done = [dict(id=f"untimed-{k}", title=f"MATH 2940 PS{k}", bucket="assignments", isDone=True) for k in range(4)]
    assert len(eng.questions(todos + done, NOW)["actuals"]) == 2
    eng.mark_asked(done[0]["id"])
    eng.mark_asked(done[1]["id"])
    assert eng.questions(todos + done, NOW)["actuals"] == []


def test_constraints_need_confirmation_and_then_bind(tmp_path):
    reply = {"constraints": [{"kind": "avoid_time", "start": "18:00", "end": "08:00", "strength": "hard",
                              "paraphrase": "No work between 6pm and 8am."},
                             {"kind": "prefer_time", "start": "08:00", "end": "12:00", "strength": "mild",
                              "paraphrase": "Mornings are best."}],
             "unsupported": [], "questions": []}
    eng = Engine(tmp_path, steps=60_000, parser=_fake_parser(reply))
    r = eng.parse_constraints("no work in the evening, mornings are best", _todos(), _events(), NOW)
    assert r["ok"] and [c["hard"] for c in r["constraints"]] == [True, False]
    assert eng.list_constraints() == []  # nothing applies before the user says yes
    eng.confirm_constraints(r["pending_id"], [0])
    assert [c["kind"] for c in eng.list_constraints()] == ["avoid_time"]
    out = eng.plan(_todos(), _events(), NOW)
    for opt in out["options"]:
        for b in opt["blocks"]:
            s, e = datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"])
            assert s.hour >= 8 and (e.hour < 18 or (e.hour == 18 and e.minute == 0))
    eng.remove_constraint(eng.list_constraints()[0]["id"])
    assert eng.list_constraints() == []


def test_server_round_trip(tmp_path):
    p = subprocess.Popen([sys.executable, "-m", "fr.product.serve", "--data", str(tmp_path), "--no-warmup",
                          "--steps", "40000"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    assert json.loads(p.stdout.readline())["ready"]
    for i, (m, params) in enumerate([("hello", {}), ("plan", dict(todos=_todos(), events=_events(), now=NOW.isoformat())),
                                     ("nope", {})]):
        p.stdin.write(json.dumps(dict(id=i, method=m, params=params)) + "\n")
        p.stdin.flush()
        reply = json.loads(p.stdout.readline())
        assert reply["id"] == i
        if m == "plan":
            assert len(reply["result"]["options"]) == 3
        if m == "nope":
            assert reply["error"]["type"] == "ValueError"
    p.stdin.close()
    p.wait(timeout=30)


def test_soft_one_sitting_means_fewer_sessions(tmp_path):
    reply = {"constraints": [{"kind": "one_sitting", "strength": "strong", "paraphrase": "Do things in one go."}],
             "unsupported": [], "questions": []}
    todos = [t for t in _todos() if not t["isDone"]]

    def sessions(eng):
        for t in todos:
            eng.set_estimate(t["id"], 400)  # long enough that the plan splits them unless told not to
        out = eng.plan(todos, _events(), NOW)
        return len(out["options"][0]["blocks"])

    before = sessions(Engine(tmp_path / "a", steps=60_000))
    eng = Engine(tmp_path / "b", steps=60_000, parser=_fake_parser(reply))
    r = eng.parse_constraints("I like to do things in one go", todos, _events(), NOW)
    assert r["constraints"][0]["hard"] is False
    eng.confirm_constraints(r["pending_id"], [0])
    assert sessions(eng) < before


def test_cushion_stays_near_your_estimate_until_lengths_are_recorded(tmp_path):
    from fr.product.service import CUSHION_ESTIMATE, CUSHION_GUESS

    eng = Engine(tmp_path)
    todos = _todos()
    a4, lab = todos[0]["id"], todos[3]["id"]  # hard deadlines
    eng.set_estimate(a4, 120)
    p = eng.predict(todos, NOW)
    assert p[a4]["plan_minutes"] == round(120 * CUSHION_ESTIMATE)  # 2 h -> 2 h 30 m, not p95's ~6 h 35 m
    assert p[lab]["plan_minutes"] <= round(p[lab]["p50"] * CUSHION_GUESS) + 1


def test_overload_is_explained_and_every_due_date_is_a_deadline(tmp_path):
    from fr.product import adapter

    todos = _todos()
    reading = adapter.tasks_from(todos)[2]
    assert reading.type == "reading" and not reading.hard  # no p95 cushion for a reading...
    sc, _ = adapter.scenario(NOW, [reading], {reading.id: 60}, [])
    assert sc.specs[0].firmness == "hard"  # ...but its due date is still a deadline
    eng = Engine(tmp_path, steps=40_000)
    for t in todos:
        eng.set_estimate(t["id"], 1200)  # 20 h each: far more than fits before Thursday
    out = eng.plan(todos, _events(), NOW)
    assert out["notes"] and out["notes"][0].startswith("More is due than fits")
    assert not Engine(tmp_path / "light", steps=40_000).plan(todos, _events(), NOW)["notes"]


def test_parts_of_a_set_go_one_after_the_other():
    from fr.product import adapter

    def t(i, title):
        return dict(id=f"p{i}", title=title, bucket="assignments", isDone=False, dueDate="2026-10-23T23:59:00")
    tasks = adapter.tasks_from([t(1, "Chem Problem set 7 odds"), t(2, "Chem Probelm set 7 evens"), t(3, "Math HW 8")])
    sc, ids = adapter.scenario(NOW, tasks, {x.id: 120 for x in tasks}, [])
    by = {ids[s.id]: s for s in sc.specs if s.id in ids}
    assert by["p2"].deps == ((by["p1"].id, 1.0, 0),)  # evens waits for odds
    assert by["p3"].deps == () and by["p1"].deps == ()  # another course is not tied
    assert any(r["type"] == "late_tasks" for r in sc.extra_rules)


def test_an_overloaded_week_does_urgent_work_first(tmp_path):
    # a 12 h report and six 1 h quizzes, all due tonight, and one 2 h task due at 3 pm: the 3 pm task goes first
    def t(i, title, due="2026-10-19T23:59:00"):
        return dict(id=f"o{i}", title=title, bucket="assignments", isDone=False, dueDate=due)
    todos = ([t(0, "PHYS 2213 big project report"), t(9, "CATC quant strategy", "2026-10-19T15:00:00")]
             + [t(i, f"CS 2110 quiz {i}") for i in range(1, 7)])
    eng = Engine(tmp_path, steps=40_000)
    eng.set_estimate("o0", 12 * 60)
    eng.set_estimate("o9", 120)
    for i in range(1, 7):
        eng.set_estimate(f"o{i}", 60)
    out = eng.plan(todos, _events(), NOW)
    assert out["notes"][0].startswith("More is due than fits")
    for opt in out["options"]:
        assert opt["valid"]
        first = min(b["start"] for b in opt["blocks"] if b["task_id"] == "o9")
        assert first < "2026-10-19T12:00"  # not left for later in the week
        assert "o9" not in opt["late_tasks"]


def test_far_off_work_waits_and_lunch_fits_every_day(tmp_path):
    from fr.product import adapter

    assert adapter.release(0, 30 * 1440, 15) == (30 - 8) * 1440  # 15 min due in a month: from a week (and a day) before
    assert adapter.release(0, 3 * 1440, 600) == 0  # due soon: now
    reply = {"constraints": [{"kind": "daily_break", "title": "Lunch", "minutes": 15, "travel_min": 10,
                              "start": "11:30", "end": "14:30", "paraphrase": "Lunch every day."}],
             "unsupported": [], "questions": []}
    eng = Engine(tmp_path, steps=60_000, parser=_fake_parser(reply))
    r = eng.parse_constraints("15 minute lunch each day, 10 minutes to get there", _todos(), _events(), NOW)
    eng.confirm_constraints(r["pending_id"], [0])
    todos = _todos() + [dict(id="far", title="Sprint classes", bucket="assignments", isDone=False,
                             dueDate="2026-11-17T23:59:00")]
    out = eng.plan(todos, _events(), NOW)
    for opt in out["options"]:
        assert not [b for b in opt["blocks"] if b["task_id"] == "far"]  # not this fortnight's work
        lunches = [b for b in opt["blocks"] if b["task_id"] == "break:Lunch"]
        days = {b["start"][:10] for b in lunches}
        assert len(days) >= 13  # one a day (today's window is still ahead at 08:00)
        for b in lunches:
            assert "11:30" <= b["start"][11:16] and b["end"][11:16] <= "14:30"


def test_an_overloaded_week_suggests_the_least_important_events_to_skip(tmp_path, monkeypatch):
    from fr.product import adapter, events

    def rater(titles):
        out = {events.key(t): events.fallback(t) for t in titles}
        out[events.key("club meeting")] = dict(level="likely", reason="your own club")
        return out
    evs = _events() + [dict(title="CS 2110 office hours", start="2026-10-19T14:00:00", end="2026-10-19T16:00:00",
                            isAllDay=False)]
    eng = Engine(tmp_path, steps=40_000, rater=rater)
    todos = [dict(id=f"o{i}", title=f"PHYS 2213 lab report {i}", bucket="assignments", isDone=False,
                  dueDate="2026-10-20T23:59:00") for i in range(4)]
    for t in todos:
        eng.set_estimate(t["id"], 8 * 60)  # 32 h of labs by tomorrow night: more than fits
    eng.plan(todos, evs, NOW)
    r = eng.suggest_skips(evs, NOW)
    titles = [x["title"] for x in r["suggestions"]]
    assert r["deadline"] and titles[0] == "CS 2110 office hours"  # optional first, the most time freed first
    assert r["until"] >= r["deadline"]  # until the late work is done, not just to the deadline
    assert "club meeting" in titles and "CS 2110 lecture" not in titles  # likely after optional; classes never
    eng.decide_event("CS 2110 office hours", "2026-10-19T14:00", "skip")
    eng.decide_event("club meeting", "2026-10-20T19:00", "keep")
    assert eng.suggest_skips(evs, NOW)["suggestions"] == []
    seen = {}
    real = adapter.scenario
    monkeypatch.setattr(adapter, "scenario", lambda now, t, m, e, *a: seen.setdefault("e", e) and real(now, t, m, e, *a))
    eng.plan(todos, evs, NOW)
    assert not [e for e in seen["e"] if e["title"] == "CS 2110 office hours"]  # skipped: no longer blocks time
    eng.decide_event("CS 2110 office hours", "2026-10-19T14:00", "unskip")
    assert eng.s["skipped"] == []


def test_keep_can_be_undone(tmp_path):
    eng = Engine(tmp_path, rater=lambda titles: {})
    eng.decide_event("Chess Club", "2026-10-23T18:00", "keep")
    assert eng.s["kept_titles"] == ["Chess Club"] and eng.s["event_ratings"]["chess club"]["level"] == "required"
    eng.decide_event("Chess Club", "2026-10-23T18:00", "unkeep")
    assert eng.s["kept_events"] == [] and eng.s["kept_titles"] == [] and "chess club" not in eng.s["event_ratings"]


def test_one_timed_task_does_not_double_every_estimate(tmp_path):
    eng = Engine(tmp_path)
    todos = _todos()
    eng.set_estimate(todos[0]["id"], 720)
    eng.set_estimate(todos[3]["id"], 240)
    done = dict(id="catc", title="CATC quant strategy", bucket="assignments", isDone=True)
    eng.set_estimate("catc", 60)
    eng.record_actual(done, 128)  # took twice the estimate, once
    p = eng.predict(todos, NOW)
    assert p[todos[0]["id"]]["p50"] == 720 and p[todos[3]["id"]]["p50"] == 240


def test_prep_is_due_at_its_quiz_and_never_planned_after(tmp_path):
    from fr.product import adapter

    quiz = dict(title="Math 1920 Quiz 2", start="2026-10-20T13:25:00", end="2026-10-20T14:15:00", isAllDay=False)
    todos = [dict(id="prep", title="Math prep for quiz", bucket="assignments", isDone=False,
                  dueDate="2026-10-20T23:59:00"),
             dict(id="big", title="PHYS 2213 lab report", bucket="assignments", isDone=False,
                  dueDate="2026-10-20T12:00:00")]
    tasks = adapter.tasks_from(todos)
    sc, ids = adapter.scenario(NOW, tasks, {t.id: 300 for t in tasks}, _events() + [quiz])
    spec = next(s for s in sc.specs if ids.get(s.id) == "prep")
    assert spec.hard_window and adapter.local(quiz["start"]) and spec.due == adapter.clock.to_minutes(
        adapter.local(quiz["start"]))  # due when the quiz starts, not at midnight
    eng = Engine(tmp_path, steps=40_000)
    eng.set_estimate("prep", 20 * 60)  # far more prep than fits before the quiz
    eng.set_estimate("big", 120)
    out = eng.plan(todos, _events() + [quiz], NOW)
    for opt in out["options"]:
        assert opt["valid"]
        assert all(b["end"] <= "2026-10-20T13:25" for b in opt["blocks"] if b["task_id"] == "prep")  # none after
        d = next(d for d in opt["late_detail"] if d["task_id"] == "prep")
        assert d["expires"] and d["hours_late"] is None and 0 < d["placed_h"] < d["need_h"]  # as much as fits
    assert eng.predict(todos, NOW)["prep"]["expires"]
    eng.set_expires("big", True)  # anything can be marked pointless if late
    assert eng.predict(todos, NOW)["big"]["expires"]


def test_no_late_rule():
    from fr.product import constraints as C

    reply = {"constraints": [{"kind": "no_late", "target": {"titles": ["study guide"]}}]}
    assert C.Parse.model_validate(reply).constraints[0].kind == "no_late"
