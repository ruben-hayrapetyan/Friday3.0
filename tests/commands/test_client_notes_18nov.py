"""A client's notes, 18 Nov (Friday Notes.pdf), Wednesday 18 Nov 2026 in New York.

- Pace, Push for today: "8 items change · edit article draft 11.02 h late", add scripts Sun 29 Nov 17:00 → Mon 30 Nov
  19:30, DLI reading into Tue 1 Dec. "If this is a push pace, why is everything getting pushed back?" The preview's
  solve was compared with the saved plan however old; one made before the day turned over (the 3:30 nightly) had a
  horizon a day shorter, and work leaning as late as its pacing allows spread into the new day. And the draft, late
  before and after, was said as the pace's doing.
- Inbox: "Keep edit article draft where you locked it? Locked at Wed 10:15, it makes other work 164h 15m later." for
  an overdue draft locked at 10:15 today, with nothing else late in the plan. "Its overdue tho… also is friday really
  planning 164 hours ahead?" The lock's cost was two quick estimates compared, the estimate's own misses summed over
  every item, the locked one too.
"""

import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from friday.commands import decisions
from friday.core.time import parse_local, parse_utc, to_utc
from friday.engine.cpsat_deadlines import FIXED_EFFORT
from friday.planner import service
from tests.commands.helpers import TZ, App, new_app

# The week as a quick sweep found it: the plan has only the draft late, the quick estimate with the lock had t8 late.
TASKS = [
    ("t0", 240, "2026-11-29T12:00"), ("t1", 90, "2026-11-21T09:00"), ("t2", 300, "2026-11-22T23:59"),
    ("t3", 480, "2026-11-22T12:00"), ("t4", 180, "2026-11-20T09:00"), ("t5", 90, "2026-11-25T09:00"),
    ("t6", 480, "2026-11-27T12:00"), ("t7", 600, "2026-11-29T09:00"), ("t8", 600, "2026-11-23T09:00"),
    ("t9", 300, "2026-11-22T09:00"), ("t10", 180, "2026-11-27T23:59"), ("t11", 120, "2026-11-29T23:59"),
    ("t12", 240, "2026-11-19T12:00"),
]  # fmt: skip
CLASSES = [(20, "14:00", "16:00"), (21, "14:00", "16:00"), (22, "10:00", "16:00"), (25, "10:00", "17:00"),
           (27, "10:00", "17:00"), (30, "10:00", "17:00")]  # fmt: skip


@pytest.fixture(autouse=True)
def same_plan_each_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """The deadline fallback by effort, not seconds: on a busy machine it stopped sooner and left t8 8.5 h late."""
    monkeypatch.setenv(FIXED_EFFORT, "1")


def overdue_draft(app: App) -> int:
    """Due last night, locked at 10:15 today: 11.02 h late, as the client's preview said."""
    draft = app.do("add", title="edit article draft", duration_min=45, due="2026-11-17T23:59")["item"]["id"]
    app.full("pin", payload={"id": draft, "start": "2026-11-18T10:15", "end": "2026-11-18T11:00"}, provisional=False)
    return draft


def report(app: App) -> dict:
    return json.loads(app.table("plans")[-1]["report"])


def asked(app: App, kind: str) -> list[dict]:
    return [d for d in app.do("status")["decisions"] if d["kind"] == kind]


# A lock that makes work late


def test_a_locked_overdue_draft_isnt_said_to_make_work_late_when_nothing_else_is(tmp_path: Path) -> None:
    app = new_app(tmp_path, now="2026-11-18T09:00", horizon_days=14)
    draft = overdue_draft(app)
    for title, minutes, due in TASKS:
        app.do("add", title=title, duration_min=minutes, due=due)
    for day, start, end in CLASSES:
        app.do("add", title="class", when="fixed", start=f"2026-11-{day}T{start}", end=f"2026-11-{day}T{end}")
    message = app.do("replan")["message"]
    assert report(app)["late_hours"] == {str(draft): 11.02}  # nothing late but the draft
    assert "to decide" not in message
    assert asked(app, "lock") == []  # was "it makes other work 8h 30m later"
    assert [i["item_id"] for i in asked(app, "late")[0]["items"]] == [draft]  # the draft itself is still asked about


def snapshot(*pins: NS) -> NS:
    return NS(
        pins=list(pins),
        now_utc=1000,
        items=[
            NS(id=1, title="edit article draft"),
            NS(id=2, title="lab writeup"),
            NS(id=3, title="essay"),
            NS(id=4, title="reading"),
        ],
        settings={"planner": NS(lock_conflict_tolerance=1)},
    )


def lock(pin_id: int, item_id: int, start: int = 1100, end: int = 1145) -> NS:
    return NS(id=pin_id, item_id=item_id, kind="locked", start_utc=start, end_utc=end)


@pytest.fixture
def estimates(monkeypatch: pytest.MonkeyPatch) -> dict:
    """quick_late made to give these: "with" for the plan's input, "freed" with every lock let go, and by pin id."""
    given: dict = {}
    monkeypatch.setattr(service, "build_input", lambda snapshot: "with")
    monkeypatch.setattr(service, "with_pins_preferred", lambda ids: lambda inp: "freed" if ids is None else min(ids))
    monkeypatch.setattr(service, "quick_late", lambda inp, with_fallback: given[inp])
    return given


def plan(late: dict[int, float]) -> NS:
    return NS(report={"late_hours": late}, stage_values={"deadlines": 1})


def test_the_cost_is_the_plans_lateness_not_the_estimates(estimates: dict) -> None:
    # The estimate with the lock had essay 150 h late; the plan (the solve) has it on time. Let go, the estimate has
    # lab writeup on time.
    estimates.update({"with": (900, {1: 11.02, 2: 3.0, 3: 150.0}), "freed": (100, {1: 11.02}), 7: (100, {1: 11.02})})
    (conflict,) = service.lock_conflicts(snapshot(lock(7, 1)), plan({1: 11.02, 2: 3.0}))
    assert conflict["extra_late_hours"] == 3.0  # was 153.0, the essay's 150 h the estimate's own
    assert conflict["later"] == [{"title": "lab writeup", "hours": 3.0}]


def test_the_locked_work_itself_isnt_other_work(estimates: dict) -> None:
    # Let go, the draft goes first (1.25 h sooner) and lab writeup with it: only lab writeup's is other work's.
    estimates.update({"with": (900, {}), "freed": (100, {}), 7: (100, {1: 9.77, 2: 1.75})})
    (conflict,) = service.lock_conflicts(snapshot(lock(7, 1)), plan({1: 11.02, 2: 3.0}))
    assert conflict["extra_late_hours"] == 1.25  # was 2.5, the draft's own 1.25 h in it
    assert conflict["itself_hours"] == 0


def test_a_lock_whose_work_would_get_as_much_later_itself_isnt_asked_about(estimates: dict) -> None:
    # Let go, lab writeup is 22.5 h sooner and the overdue draft 22.5 h later: nothing saved, not asked.
    estimates.update({"with": (900, {}), "freed": (100, {}), 7: (100, {1: 33.52, 2: 10.0})})
    assert service.lock_conflicts(snapshot(lock(7, 1)), plan({1: 11.02, 2: 32.5})) == []


def test_nothing_late_but_the_locked_work_asks_nothing(estimates: dict) -> None:
    estimates.update({"with": (900, {1: 11.02, 3: 164.25}), "freed": (100, {1: 11.02}), 7: (100, {1: 11.02})})
    assert service.lock_conflicts(snapshot(lock(7, 1)), plan({1: 11.02})) == []


def test_a_lock_that_has_passed_isnt_asked_about(estimates: dict) -> None:
    estimates.update({"with": (900, {}), "freed": (100, {}), 7: (100, {1: 11.02})})
    assert service.lock_conflicts(snapshot(lock(7, 1, start=900, end=945)), plan({1: 11.02, 2: 3.0})) == []


@pytest.mark.parametrize(
    ("later", "itself", "said"),
    [
        ([("lab writeup", 3.0)], 0, "it makes lab writeup finish 3h later."),
        ([("lab writeup", 8.5), ("essay", 0.5)], 0, "it makes lab writeup finish 8h 30m later and essay 30 min later."),
        ([("lab writeup", 8.5), ("essay", 2), ("reading", 1)], 0,
         "it makes lab writeup finish 8h 30m later, and 2 other things later too."),
        ([("lab writeup", 22.5)], 21.0,
         "it makes lab writeup finish 22h 30m later. Let go, it would finish 21h later itself."),
    ],
)  # fmt: skip
def test_a_locks_cost_names_the_work_it_makes_later(later: list, itself: float, said: str) -> None:
    conflict = {"extra_late_hours": sum(h for _, h in later), "itself_hours": itself,
                "later": [{"title": t, "hours": h} for t, h in later]}  # fmt: skip
    assert decisions.lock_cost(conflict) == said
    assert "other work" not in said


def test_a_plan_saved_before_the_work_was_named_still_reads() -> None:
    assert decisions.lock_cost({"extra_late_hours": 2.5}) == "it makes other work 2h 30m later."


# What a pace changes


def week(app: App) -> None:
    app.do("add", title="add scripts", duration_min=150, due="2026-12-01T23:59")
    app.do("add", title="DLI reading", duration_min=360, due="2026-12-02T23:59")
    app.do("add", title="problem set", duration_min=240, due="2026-11-24T23:59")
    app.do("add", title="lab writeup", duration_min=180, due="2026-11-20T23:59")
    app.do("add", title="project report", duration_min=480, due="2026-11-30T23:59")
    app.do("add", title="read papers", duration_min=300, due="2026-11-27T23:59")
    app.do("add", title="practice piano", every="mon,tue,wed,thu,fri,sat,sun", duration_min=30)
    app.do("add", text="learn spanish 3h a week")
    for day in range(18, 31):
        if day % 7 not in (0, 1):
            app.do("add", title="class", when="fixed", start=f"2026-11-{day}T13:00", end=f"2026-11-{day}T15:00")


def test_push_for_today_isnt_said_to_move_work_into_the_day_that_came_into_view(tmp_path: Path) -> None:
    """The plan was made at 3:30, before the day turned over: its two weeks ended Monday 30 Nov. At 9:15 the
    preview's solve had Tuesday 1 Dec too, and work spread into it was said as Push's doing."""
    app = new_app(tmp_path, now="2026-11-18T03:30", horizon_days=14)
    week(app)
    app.do("replan")
    app.at("2026-11-18T09:15")
    changes = app.full("pace", payload={"name": "Push", "for_days": 1}, preview="full", provisional=False).changes
    assert changes is not None
    titles = [b.title for b in changes.added] + [m["title"] for m in changes.moved]
    assert "DLI reading" not in titles  # was "added" on Tue 1 Dec
    days = {m["after"][0][0][:10] for m in changes.moved if m["after"]} | {b.start[:10] for b in changes.added}
    assert "2026-12-01" not in days
    assert len(set(titles)) <= 3  # was 9 items: add scripts, problem set, project report, piano, …


def test_a_preview_says_what_was_late_without_it(tmp_path: Path) -> None:
    app = new_app(tmp_path, now="2026-11-18T09:00", horizon_days=7)
    overdue_draft(app)
    app.do("add", title="lab writeup", duration_min=120, due="2026-11-20T23:59")
    app.do("replan")
    changes = app.full("pace", payload={"name": "Push", "for_days": 1}, preview="full", provisional=False).changes
    assert changes is not None
    assert changes.late_hours == {"edit article draft": 11.02}
    assert changes.late_hours_before == {"edit article draft": 11.02}  # late already: not the pace's doing


def test_a_preview_doesnt_plan_again_what_was_done_before_now(tmp_path: Path) -> None:
    """Planned blocks that have passed count as done: the plan the preview starts from has none before now, and
    yesterday's practice came back "added" at 9:15, hours late."""
    app = new_app(tmp_path, now="2026-11-18T03:30", horizon_days=7)
    app.do("add", title="practice piano", every="mon,tue,wed,thu,fri,sat,sun", duration_min=30)
    app.do("add", title="lab writeup", duration_min=120, due="2026-11-20T23:59")
    app.do("replan")
    first = min(parse_utc(b["start_utc"]) for b in app.table("blocks"))
    app.now_utc = first + 60  # an hour after the first practice began: it's done
    assert app.now_utc < to_utc(parse_local("2026-11-19T04:00"), TZ)
    changes = app.full("pace", payload={"name": "Push", "for_days": 1}, preview="full", provisional=False).changes
    assert changes is not None
    assert changes.late_hours == {}
    assert [b.title for b in changes.added] == []
