"""At least so many hours of sleep a night, as a rule (27 Oct: "I tried adding I want at least 7 hours of sleep per
night as a rule but it didn't work. I thought that there was some sleep penalty"). The test nights: bed 11:30pm, up
7:30am, and a deadline may push an hour past bedtime. Monday 2026-10-19 in New York."""

from pathlib import Path

import pytest

from friday.commands.claude import proposals
from friday.core.rule_text import read, sentence, spec
from friday.planner.contradictions import against
from friday.planner.service import replan
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=3)


def crunch(app: App) -> int:
    """Work that fits only by working past bedtime: 3.5 h due 7am Tuesday, with 9am–9pm taken."""
    app.do("add", title="busy", when="fixed", start="2026-10-19T09:00", end="2026-10-19T21:00")
    return app.do("add", text="essay due tue 07:00 ~3.5h")["item"]["id"]


def ends(app: App, item: int) -> list[str]:
    return [b["end"] for b in app.do("plan")["blocks"] if b["item_id"] == item]


def in_the_night(app: App, item: int, night_from: str) -> list[tuple[str, str]]:
    """Its blocks between `night_from` Monday and 7:30am Tuesday, when you wake."""
    blocks = [(b["start"], b["end"]) for b in app.do("plan")["blocks"] if b["item_id"] == item]
    return [(s, e) for s, e in blocks if s < "2026-10-20T07:30" and e > f"2026-10-19T{night_from}"]


@pytest.mark.parametrize(
    ("text", "hours", "days", "strength"),
    [
        ("I want at least 7 hours of sleep per night", 7, None, "Prefer"),  # as you typed it
        ("at least 7 hours of sleep", 7, None, "Prefer"),
        ("sleep at least 7 hours", 7, None, "Prefer"),
        ("never less than 7h of sleep", 7, None, "Always"),
        ("7+ hours of sleep minimum", 7, None, "Prefer"),
        ("dont let work cut my sleep below 6.5 hours", 6.5, None, "Prefer"),
        ("seven and a half hours of sleep", 7.5, None, "Prefer"),
        ("7-8 hrs of sleep a night", 7, None, "Prefer"),
        ("I need 8h of sleep on school nights", 8, ("mon", "tue", "wed", "thu", "sun"), "Prefer"),
        ("always get 8 hours of sleep on weekends", 8, ("sat", "sun"), "Always"),
        ("make sure I get my 8 hours of shut-eye", 8, None, "Prefer"),
        ("really want 7.5 hrs sleep", 7.5, None, "Strongly"),
    ],
)
def test_a_night_s_sleep_is_read_as_a_rule(text: str, hours: float, days: tuple | None, strength: str) -> None:
    r, said = read(text)
    assert r is not None and (r.kind, r.amount, r.days, said) == ("sleep_min", hours, days, strength)


@pytest.mark.parametrize(
    "text",
    [
        "no more than 9 hours of sleep",  # a cap on sleep isn't something Friday plans
        "bed by 11",  # a bedtime is the sleep setting (read as the end of work)
        "if I get less than 6 hours of sleep go easy the next day",  # a condition: Claude's
        "sleep in on weekends",
    ],
)
def test_what_isn_t_a_sleep_minimum_isn_t_read_as_one(text: str) -> None:
    r, _ = read(text)
    assert r is None or r.kind != "sleep_min"


def test_it_says_itself_back_and_becomes_the_planner_s_rule() -> None:
    r, _ = read("8 hours of sleep on school nights")
    assert r is not None and sentence(r) == "At least 8 h of sleep a night on school nights"
    rule = spec(r, "Always", "mine", [], [])
    assert (rule["type"], rule["params"]) == ("sleep_min", {"hours": 8.0, "price": "forbid", "days": list(r.days)})
    assert spec(r, "Prefer", "mine", [], [])["params"]["price"] == 40.0


def test_without_it_a_deadline_takes_the_hour_past_bedtime(app: App) -> None:
    essay = crunch(app)
    replan(app.conn, app.now_utc)
    assert max(ends(app, essay)) == "2026-10-20T00:30"


def test_always_keeps_the_night_and_the_work_is_late_instead(app: App) -> None:
    """8 h from 7:30am is 11:30pm: nothing past bedtime, though the essay is late for it."""
    essay = crunch(app)
    app.do("rule_add", text="at least 8 hours of sleep", strength="Always")
    replan(app.conn, app.now_utc)
    assert in_the_night(app, essay, "23:30") == []
    assert app.do("status")["late"]  # the rest goes after you wake


def test_a_longer_night_than_your_bedtime_gives_ends_the_day_earlier(app: App) -> None:
    """8.5 h before 7:30am is 11pm: work stops half an hour before bedtime."""
    essay = crunch(app)
    app.do("rule_add", text="never less than 8.5 hours of sleep", strength="Always")
    replan(app.conn, app.now_utc)
    assert in_the_night(app, essay, "23:00") == []


def test_only_the_nights_named(app: App) -> None:
    """On Saturday nights only: Monday's deadline still takes the hour past bedtime."""
    essay = crunch(app)
    app.do("rule_add", text="always 8 hours of sleep on saturdays", strength="Always")
    replan(app.conn, app.now_utc)
    assert max(ends(app, essay)) == "2026-10-20T00:30"


def test_your_sentence_adds_the_rule_and_the_rules_list_says_it(app: App) -> None:
    app.do("rule_add", text="I want at least 7 hours of sleep per night")
    said = [r["sentence"] for r in app.do("rules")]
    assert "At least 7 h of sleep a night" in said


def test_two_sleep_minimums_overlap_and_the_longer_counts() -> None:
    a = spec(read("at least 7 hours of sleep")[0], "Prefer", "seven", [], [])
    b = spec(read("at least 8 hours of sleep")[0], "Prefer", "eight", [], [])
    (found,) = against(a, [b])
    assert found.overlap and "the longer one" in found.why


def test_claude_may_set_bedtimes_and_only_the_nights_named_change(app: App) -> None:
    answer = {
        "actions": [{"command": "settings_set", "input": {"key": "sleep", "value": {"mon": {"bedtime": "23:00"}}}}]
    }
    (action,) = proposals(answer, ("settings_set",)).actions
    assert action.error is None
    app.do("settings_set", key="sleep", value={"mon": {"bedtime": "23:00"}})
    sleep = app.do("settings")["sleep"]
    assert sleep["mon"]["bedtime"] == "23:00" and sleep["tue"]["bedtime"] == "23:30"
    assert sleep["mon"]["wake"] == "07:30"
