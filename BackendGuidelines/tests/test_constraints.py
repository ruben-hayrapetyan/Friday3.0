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
