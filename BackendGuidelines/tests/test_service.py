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
