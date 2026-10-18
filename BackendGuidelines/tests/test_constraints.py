"""Typed constraints compile into the engine's own vocabulary, and the engine honours the hard ones."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from fr.core.evaluate import check
from fr.core.generate import cornell_semester
from fr.engines.prepare import prepare
from fr.product import constraints as C
from fr.samplers.tiered import tiered


def _plan(sc, steps=(20_000, 40_000)):
    p = sc.build()
    pr = prepare(p)
    r = tiered(pr.c, pr.owner, steps=steps, seed=1)
    return p, pr.c.plan_from_owner(r.owner)


def _work_minutes(p, plan, pred):
    g = p.grid
    return [(k, s) for k, slots in plan.items() for s in slots if s < g.S and pred(g.slots[s])]


def test_parse_reply_validates_and_rejects_bad_times():
    reply = {"constraints": [{"kind": "sleep", "bedtime": "00:30", "wake": "08:00"},
                             {"kind": "avoid_time", "start": "23:00", "end": "07:00", "strength": "hard"}],
             "unsupported": [], "questions": []}
    parsed = C.Parse.model_validate(reply)
    assert [c.kind for c in parsed.constraints] == ["sleep", "avoid_time"]
    with pytest.raises(ValidationError):
        C.Parse.model_validate({"constraints": [{"kind": "avoid_time", "start": "11pm"}]})
    with pytest.raises(ValidationError):
        C.Parse.model_validate({"constraints": [{"kind": "teleport"}]})


def test_hard_avoid_window_is_never_used():
    sc = cornell_semester(0)
    c = C.AvoidTime(start="21:00", end="09:00", strength="hard")
    sc2, notes = C.apply(sc, [c])
    assert not notes
    p, plan = _plan(sc2)
    assert check(p, plan) == []
    late = _work_minutes(p, plan, lambda sl: sl.local_minute >= 21 * 60 or sl.local_minute < 9 * 60)
    assert late == []


def test_hard_avoid_scoped_to_a_course_and_a_day():
    sc = cornell_semester(1)
    c = C.AvoidTime(days=["sat", "sun"], strength="hard", target=C.Target(courses=["CS1"]))
    sc2, _ = C.apply(sc, [c])
    p, plan = _plan(sc2)
    hits = _work_minutes(p, plan, lambda sl: sl.weekday in (5, 6))
    assert not [k for k, _ in hits if p.items[k].area == "CS1"]
    assert [k for k, _ in hits if p.items[k].area != "CS1"]  # other work still uses weekends


def test_sleep_moves_the_protected_core():
    sc = cornell_semester(2)
    sc2, _ = C.apply(sc, [C.SleepC(bedtime="21:30", wake="06:00")])
    assert sc2.settings.sleep.bedtime == (21 * 60 + 30,) * 7
    assert sc2.settings.sleep.wake == (360,) * 7
    late, _ = C.apply(sc, [C.SleepC(nights=["fri"], bedtime="02:00")])
    assert late.settings.sleep.bedtime[4] == 26 * 60 and late.settings.sleep.bedtime[3] == sc.settings.sleep.bedtime[3]
    p, plan = _plan(sc2)
    margin = sc2.settings.sleep.margin
    assert not _work_minutes(p, plan, lambda sl: sl.local_minute >= 21 * 60 + 30 + margin or sl.local_minute < 360)


def test_commitment_blocks_time_and_session_limits_hold():
    sc = cornell_semester(3)
    cs = [C.Commitment(title="gym", days=["mon", "wed", "fri"], start="07:00", end="08:30"),
          C.SessionLength(max_hours=1.5, target=C.Target(kinds=["assignment"])),
          C.OneSitting(target=C.Target(kinds=["reading"]))]
    sc2, notes = C.apply(sc, cs)
    assert not notes
    p, plan = _plan(sc2)
    assert check(p, plan) == []
    gyms = [f for f in p.fixed if f.title == "gym"]
    assert gyms and all((f.start % 1440) == 420 for f in gyms)
    for k, it in p.items.items():
        if it.preset == "assignment":
            assert it.max_chunk == 6
        if it.preset == "reading":
            assert it.shape == "one_sitting"


def test_finish_early_hard_moves_due_and_order_adds_a_dependency():
    sc = cornell_semester(4)
    before = {s.id: s.due for s in sc.specs if s.preset == "assignment"}
    sc2, _ = C.apply(sc, [C.FinishEarly(days=1, strength="hard", target=C.Target(kinds=["assignment"]))])
    after = {s.id: s.due for s in sc2.specs if s.preset == "assignment"}
    assert all(after[i] == before[i] - 1440 for i in before)
    sc3, notes = C.apply(sc, [C.Order(first="prelim 1 prep", then="prelim 2 prep")])
    assert not notes
    p2 = [s for s in sc3.specs if s.title == "prelim 2 prep"][0]
    p1 = [s for s in sc3.specs if s.title == "prelim 1 prep"][0]
    assert any(d[0] == p1.id for d in p2.deps)
    _, notes = C.apply(sc, [C.Order(first="problem set", then="prelim 2 prep")])
    assert notes  # ambiguous: many problem sets


def test_soft_constraints_become_rules_that_build():
    sc = cornell_semester(5)
    cs = [C.PreferTime(start="09:00", end="13:00", strength="strong", target=C.Target(energy=["deep"])),
          C.DailyLimit(hours=6, strength="medium"), C.KeepFree(days=["sun"], hours=4),
          C.Pacing(style="batch_by_course"), C.FinishEarly(days=2), C.Buffer(event_kind="class", after_min=15),
          C.AvoidTime(days=["fri"], start="18:00", strength="mild")]
    sc2, _ = C.apply(sc, cs)
    assert sc2.settings.buffers["class"][1] == 15
    p, plan = _plan(sc2)
    assert check(p, plan) == []
    names = {r.name for r in p.rules}
    assert {"user:0:prefer_time:outside", "user:1:daily_limit", "user:2:keep_free", "user:3:pacing",
            "user:4:finish_early", "user:6:avoid_time"} <= names


def _friday_tasks():
    from fr.product import adapter

    def t(i, title, due, bucket="assignments"):
        return dict(id=f"id-{i}", title=title, horizon="shortTerm", bucket=bucket, isDone=False, isStarred=False,
                    createdAt="2026-10-15T12:00:00Z", progress=0, dueDate=due)
    todos = [t(1, "Chem HW 5 evens", "2026-10-23T23:59:00"), t(2, "Chem Probelm set 7 odds", "2026-10-24T23:59:00"),
             t(3, "Chem make study guide", "2026-10-23T23:59:00"), t(4, "Psych pedagogy statement", "2026-10-24T23:59:00"),
             t(5, "Chem lab report", "2026-10-22T23:59:00"), t(6, "Chem chapter 8", "2026-10-22T23:59:00", "readings")]
    return adapter, adapter.tasks_from(todos)


def test_task_types_come_from_titles_and_exclusions_leave_tasks_out():
    from datetime import datetime

    adapter, tasks = _friday_tasks()
    assert [t.type for t in tasks] == ["problem_set", "problem_set", "other", "other", "lab", "reading"]
    sc, _ = adapter.scenario(datetime(2026, 10, 19, 8, 0), tasks, {t.id: 180 for t in tasks}, [])
    c = C.AvoidTime(days=["mon", "tue"], strength="hard", target=C.Target(exclude_types=["problem_set"]))
    sc2, notes = C.apply(sc, [c])
    assert not notes
    p, plan = _plan(sc2)
    assert check(p, plan) == []
    early = _work_minutes(p, plan, lambda sl: sl.weekday in (0, 1))
    assert early and all("type:problem_set" in p.items[k].tags for k, _ in early)  # only problem sets on Mon/Tue


def test_one_sitting_soft_strengths_set_which_tasks_split_first():
    from datetime import datetime

    adapter, tasks = _friday_tasks()
    sc, _ = adapter.scenario(datetime(2026, 10, 19, 8, 0), tasks, {t.id: 180 for t in tasks}, [])
    reply = {"constraints": [
        {"kind": "one_sitting", "strength": "mild", "target": {"types": ["problem_set"]}},
        {"kind": "one_sitting", "strength": "medium", "target": {"exclude_types": ["problem_set"]}}]}
    sc2, _ = C.apply(sc, C.Parse.model_validate(reply).constraints)
    cost = {s.title: s.chunk_cost for s in sc2.specs}
    assert cost["Chem HW 5 evens"] == cost["Chem Probelm set 7 odds"] == C.SITTING["mild"]
    assert cost["Chem make study guide"] == cost["Chem lab report"] == C.SITTING["medium"]
    assert C.OneSitting(target=C.Target()).strength == "hard"  # replies from before strengths still mean never split


def test_exam_focus_holds_other_work_until_after_the_exam_and_buffers_replace_defaults():
    from datetime import datetime

    from fr.product import adapter, clock

    now = datetime(2026, 10, 19, 8, 0)

    def t(i, title, due):
        return dict(id=f"x{i}", title=title, bucket="assignments", isDone=False, dueDate=due)
    tasks = adapter.tasks_from([t(1, "Chem make study guide", "2026-10-22T18:00:00"),
                                t(2, "CS essay draft", "2026-10-25T23:59:00"),
                                t(3, "Math HW 9", "2026-10-21T23:59:00"),
                                t(4, "Psych write-up", "2026-10-23T09:00:00")])
    exam = dict(title="Chem 2090 Exam 2", start="2026-10-22T19:30:00", end="2026-10-22T21:00:00", isAllDay=False)
    sc, ids = adapter.scenario(now, tasks, {x.id: 180 for x in tasks}, [exam])
    sc2, notes = C.apply(sc, [C.ExamFocus(days_before=3), C.Buffer(event_kind="class", after_min=15)])
    rel = {ids[s.id]: s.release for s in sc2.specs if s.id in ids}
    end = clock.to_minutes(datetime(2026, 10, 22, 21, 0))
    assert rel["x2"] == end  # other course, due Sunday: after the exam
    assert rel["x1"] < end and rel["x3"] < end  # the exam's own course, and work due before the exam, stay
    assert rel["x4"] < end  # due 12 h after it with 3 h to do: no room after, so it may run through
    assert notes == ["Before Chem 2090 Exam 2: 1 other tasks wait until after it"]
    assert sc2.settings.buffers["class"] == (0, 15)  # the user's buffer replaces Friday's 10 minutes before classes


def test_priority_sets_what_gives_way_first():
    from datetime import datetime

    from fr.product import adapter

    def t(i, title, bucket):
        return dict(id=f"p{i}", title=title, bucket=bucket, isDone=False, dueDate="2026-10-22T23:59:00")
    tasks = adapter.tasks_from([t(1, "Chem HW 6", "assignments"), t(2, "Chem chapter 8", "readings")])
    sc, ids = adapter.scenario(datetime(2026, 10, 19, 8, 0), tasks, {x.id: 60 for x in tasks}, [])
    reply = {"constraints": [{"kind": "priority", "level": "high", "target": {"kinds": ["assignment"]}},
                             {"kind": "priority", "level": "low", "target": {"types": ["reading"]}}]}
    sc2, _ = C.apply(sc, C.Parse.model_validate(reply).constraints)
    imp = {ids[s.id]: s.importance for s in sc2.specs if s.id in ids}
    assert imp == {"p1": 5, "p2": 1}
