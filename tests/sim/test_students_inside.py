"""Glass box: the parts the Cornell students are made of, each on its own: a term's calendars (sim/cornell.py), the
stand-in Google and AI (sim/fakes.py), the first evening's routines and repeats (sim/first_evening.py), the weeks
lived before today (sim/history.py) and the plan judged as a student reads it (sim/judge.py)."""

import json
import random
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from friday.core.time import parse_local, to_utc
from friday.sim.cornell import ZONE, Meeting, Routine, Student, Work, term
from friday.sim.fakes import ScriptedClient, event, repeated, until_of
from friday.sim.first_evening import add_routines, import_repeats
from friday.sim.history import hand_in_or_drop, typed_early, work_the_plan
from friday.sim.judge import judge

MONDAY = date(2026, 10, 19)


class Script:
    """Stands in for a `do`: answers the queries it was given, records every command."""

    def __init__(self, answers: dict[str, Any] | None = None) -> None:
        self.answers, self.calls = answers or {}, []

    def __call__(self, command: str, /, **payload: Any) -> Any:
        self.calls.append((command, payload))
        answer = self.answers.get(command)
        return answer(**payload) if callable(answer) else answer

    def said(self, command: str) -> list[dict[str, Any]]:
        return [p for c, p in self.calls if c == command]


def student(**fields: Any) -> Student:
    return Student("sam", "Sam", "a test student", "light", **({"meetings": ()} | fields))


# sim/cornell.py


def test_a_meeting_that_ends_early_stops_on_its_last_day_in_the_calendar_and_its_rule() -> None:
    seminar = Meeting("Seminar", "MWF", "10:00", "11:00", until=2)  # last meets this Wednesday
    sample = term(student(meetings=(seminar,)), MONDAY)
    instances = sample.google.calendars_by_id["classes@g"]
    days = sorted(e["start"]["dateTime"][:10] for e in instances)
    assert days[-2:] == ["2026-10-19", "2026-10-21"] and len(days) == 4 * 3 + 2  # four weeks back, then Mon and Wed
    # 23:59 on Wednesday in New York, in UTC
    assert sample.google.rules["m0"] == "FREQ=WEEKLY;BYDAY=MO,WE,FR;UNTIL=20261022T035900Z"


def test_a_weekly_meeting_without_an_end_repeats_four_weeks_each_way() -> None:
    sample = term(student(meetings=(Meeting("Lab", "R", "14:00", "16:00"),)), MONDAY)
    assert len(sample.google.calendars_by_id["classes@g"]) == 9 and sample.google.rules["m0"] == "FREQ=WEEKLY;BYDAY=TH"


def test_only_canvas_and_homework_work_is_on_a_calendar() -> None:
    work = (Work("PS 1", 2, 3), Work("Worksheet", 3, 1, via="homework"), Work("Typed", 4, 1, via="typed"))
    sample = term(student(work=work), MONDAY)
    assert [e["summary"] for e in sample.google.calendars_by_id["canvas@g"]] == ["PS 1"]
    assert [e["summary"] for e in sample.google.calendars_by_id["homework@g"]] == ["Worksheet due"]
    assert not any("Typed" in json.dumps(events) for events in sample.google.calendars_by_id.values())


# sim/fakes.py


def test_an_until_with_a_time_is_that_moment_and_a_dates_is_the_end_of_that_day() -> None:
    assert until_of("FREQ=WEEKLY;UNTIL=20261022T035900Z") == datetime(2026, 10, 22, 3, 59, tzinfo=UTC)
    assert until_of("FREQ=DAILY;UNTIL=20261030;BYDAY=MO") == datetime(2026, 10, 31, tzinfo=UTC)


def test_an_event_at_new_york_times_keeps_its_clock_time_after_the_clocks_go_back() -> None:
    assert event("a", "Lecture", "2026-10-20T10:00", "2026-10-20T11:00")["start"]["dateTime"].endswith("-04:00")
    after = event("b", "Lecture", "2026-11-10T10:00", "2026-11-10T11:00")
    assert datetime.fromisoformat(after["start"]["dateTime"]) == datetime(2026, 11, 10, 15, 0, tzinfo=UTC)


def test_a_weekly_repeat_stays_at_its_clock_time_across_the_change() -> None:
    times = repeated(event("w", "Office hours", "2026-10-27T15:00", "2026-10-27T16:00"), "FREQ=WEEKLY", times=2)
    assert [t["start"]["dateTime"] for t in times] == ["2026-10-27T15:00:00-04:00", "2026-11-03T15:00:00-05:00"]


def strict(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "additionalProperties": False, "properties": properties}


def asked(text: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {"messages": [{"content": [{"text": text}]}], "output_config": {"format": {"schema": schema}}}


def test_the_scripted_ai_answers_settings_test_ok_and_a_quick_add_line_with_its_title() -> None:
    ai = ScriptedClient({})
    reply = ai.messages.create(**asked("hello?", strict({"ok": {"type": "boolean"}})))
    assert json.loads(reply.content[0].text) == {"ok": True} and reply.usage.input_tokens == 900
    line = ai.messages.create(**asked("lunch with Ana", strict({"title": {"type": "string"}})))
    assert json.loads(line.content[0].text) == {"title": "lunch with Ana"} and len(ai.calls) == 2


def test_the_scripted_ai_refuses_a_schema_anthropic_would_refuse() -> None:
    loose = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    with pytest.raises(ValueError, match="Anthropic would refuse this schema"):
        ScriptedClient({}).create(**asked("hello?", loose))


# sim/first_evening.py


def test_routines_of_a_set_length_and_any_time_give_just_their_length() -> None:
    do = Script()
    lunch = Routine("Lunch", ("11:30", "14:00"))
    laundry = Routine("Laundry", minutes=60, preset="Chore", every="week")
    add_routines(do, student(routines=(lunch, laundry)))
    assert do.said("series_add") == [
        {"title": "Lunch", "preset": "Routine", "every": "day", "min_min": 30, "ideal_min": 45, "max_min": 45,
         "release_offset_min": 7 * 60 + 30, "due_offset_min": 10 * 60},
        {"title": "Laundry", "preset": "Chore", "every": "week", "duration_min": 60},
    ]  # fmt: skip


def test_repeats_are_imported_with_their_tags_and_none_waiting_means_no_import() -> None:
    lecture = Meeting("CS 2110 - LEC 001", "MWF", "10:10", "11:00", plain="CS 2110 Lecture", tag="CS 2110")
    waiting = [{"batch": "b1", "title": "CS 2110 Lecture"}, {"batch": "b2", "title": "Yoga"}]
    do = Script({"calendar_repeats": waiting})
    import_repeats(do, student(meetings=(lecture,)))
    assert do.said("repeats_import") == [
        {"repeats": [{"batch": "b1", "area": "CS 2110"}, {"batch": "b2", "area": None}]}
    ]
    nothing = Script({"calendar_repeats": []})
    import_repeats(nothing, student())
    assert [c for c, _ in nothing.calls] == ["calendar_repeats"]


# sim/history.py


def test_with_no_canvas_work_next_week_nothing_is_typed_in_early() -> None:
    do = Script()
    typed_early(SimpleNamespace(student=student(work=(Work("Last week", -3, 1),)), monday=MONDAY, do=do))
    assert do.calls == []


def test_a_block_for_work_already_finished_is_not_done_again() -> None:
    block = {"item_id": 1, "key": "k1", "start": "2026-10-19T09:00", "end": "2026-10-19T10:00"}
    do = Script({"plan": {"blocks": [block]}, "item": {"item": {"status": "done", "amount": "fixed"}}})
    life = SimpleNamespace(do=do, rng=random.Random(0))
    assert work_the_plan(life, MONDAY) == {"k1": ("not_done", 0.0)}  # type: ignore[arg-type]
    assert [c for c, _ in do.calls] == ["plan", "item"]


def overdue(n: int, **fields: Any) -> dict[str, Any]:
    base = {"id": n, "status": "todo", "due": "2026-10-19T23:59", "firmness": "hard", "when": "window",
            "amount": "fixed", "duration_min": 120}  # fmt: skip
    return base | fields


def test_work_more_than_a_day_overdue_is_handed_in_when_half_done_else_dropped() -> None:
    items = [
        overdue(1),  # worked an hour of two: handed in
        overdue(2),  # worked half an hour: dropped
        overdue(3, due="2026-10-20T20:00"),  # less than a day overdue
        overdue(4, firmness="soft"),
        overdue(5, when="fixed"),
        overdue(6, amount="elastic"),
        overdue(7, status="done"),
        overdue(8, due=None),
    ]
    do = Script({"items": items})
    life = SimpleNamespace(do=do, now=to_utc(parse_local("2026-10-21T12:00"), ZONE.key), worked={1: 60, 2: 30})
    hand_in_or_drop(life)  # type: ignore[arg-type]
    assert do.said("done") == [{"id": 1, "actual_min": 60}] and do.said("drop") == [{"id": 2}]


# sim/judge.py


def item(n: int, title: str, **fields: Any) -> dict[str, Any]:
    base = {"id": n, "title": title, "amount": "fixed", "remaining_min": 120, "due": None, "firmness": "hard",
            "status": "todo", "when": "window", "release": None}  # fmt: skip
    return base | fields


def block(n: int, title: str, start: str, end: str) -> dict[str, Any]:
    return {"item_id": n, "title": title, "start": f"2026-10-{start}", "end": f"2026-10-{end}"}


def test_a_plan_is_judged_sitting_by_sitting_as_a_student_reads_it() -> None:
    items = [
        item(1, "essay", remaining_min=240, due="2026-10-21T12:00"),
        item(2, "quick fix"),
        item(3, "marathon", remaining_min=240, due="2026-10-30T12:00"),
        item(4, "reading", amount="open", remaining_min=None),
        item(5, "Lunch", amount="elastic", release="2026-10-19T11:00", due="2026-10-19T14:00"),
        item(6, "Dinner", amount="elastic", release="2026-10-20T17:00", due="2026-10-20T21:00"),
        item(7, "forgotten", due="2026-10-22T23:59"),
        item(8, "far off", due="2026-11-30T23:59"),
    ]
    plan = {
        "blocks": [
            block(1, "essay", "19T09:00", "19T10:00"),
            block(1, "essay", "19T10:00", "19T11:00"),  # back to back: one sitting
            block(1, "essay", "21T11:00", "21T13:00"),  # an hour past its due
            block(2, "quick fix", "20T08:00", "20T08:30"),  # a scrap of two hours' work
            block(3, "marathon", "20T13:00", "20T17:00"),
            block(3, "marathon", "27T13:00", "27T14:00"),  # after the week: not judged
            block(4, "reading", "20T20:00", "20T21:00"),
            block(5, "Lunch", "19T12:15", "19T12:45"),
            block(99, "gone", "19T15:00", "19T16:00"),
        ]
    }
    verdict = judge(plan, items, datetime(2026, 10, 26))
    assert [(s.start.hour, s.end.hour) for s in verdict.sittings[1]] == [(9, 11), (11, 13)]
    assert [s.title for s in verdict.scraps] == ["quick fix"] and [s.title for s in verdict.marathons] == ["marathon"]
    assert [(m.title, m.minutes, m.inside, m.start) for m in verdict.meals] == [
        ("Lunch", 30, True, "12:15"),
        ("Dinner", 0, True, None),
    ]
    assert verdict.summary() == {
        "late": {"essay": 1.0},
        "scraps": 1,
        "marathons": 1,
        "busiest_day_h": 4.5,
        "median_margin_h": -1.0,
        "tight": 1,
        "open_h": 1.0,
        "unplanned": ["forgotten"],
    }


def test_an_empty_plan_has_no_busiest_day_and_no_margin() -> None:
    summary = judge({"blocks": []}, [], datetime(2026, 10, 26)).summary()
    assert summary["busiest_day_h"] == 0.0 and summary["median_margin_h"] is None and summary["unplanned"] == []
