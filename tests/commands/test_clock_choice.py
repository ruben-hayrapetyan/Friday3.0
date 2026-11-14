"""Your clock (settings `clock`, Settings → Appearance → Clock): 12-hour unless you choose 24. Every sentence the
server writes for you follows it: a command's answer, a decision, your rules, a refusal, and the plan's notices,
which are saved with the plan and written again by the replan a change of clock brings."""

import re
from pathlib import Path

import pytest

from friday.core.items import FieldError
from friday.core.time import CLOCK, clock_time
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def clock(app: App, chosen: str) -> None:
    app.do("settings_set", key="clock", value=chosen)


def test_the_clock_is_12_hour_until_you_choose_and_only_the_two_clocks_are_taken(app: App) -> None:
    assert app.do("settings")["clock"] == "12h"
    clock(app, "24h")
    assert app.do("settings")["clock"] == "24h"
    with pytest.raises(FieldError, match="clock"):
        clock(app, "25h")
    assert app.do("settings")["clock"] == "24h"


def test_a_commands_answer_is_on_your_clock(app: App) -> None:
    app.do("add", text="essay due mon 17:00 ~4h")
    app.do("replan")
    clock(app, "24h")
    out = app.do("shove", range="09:00-17:00", decision="keep_must_dos")
    assert re.fullmatch(r"Cleared today \d\d:\d\d–\d\d:\d\d(; today \d\d:\d\d–\d\d:\d\d)*", out["message"]), out
    assert out["message"].endswith("–17:00")
    app.do("undo", command_id=app.results[-1].command_id)
    clock(app, "12h")
    out = app.do("shove", range="09:00-17:00", decision="keep_must_dos")
    assert out["message"].startswith("Cleared today ") and out["message"].endswith("–5pm"), out


def test_your_rules_read_on_your_clock_whichever_clock_you_wrote_them_on(app: App) -> None:
    app.do("rule_add", text="no work after 10pm")
    app.do("rule_add", text="no work before 07:30")
    said = lambda: {r["sentence"] for r in app.do("rules") if r["source"] == "you"}  # noqa: E731
    assert said() == {"No work after 10pm", "No work before 7:30am"}
    clock(app, "24h")
    assert said() == {"No work after 22:00", "No work before 07:30"}
    assert app.do("rule_read", text="no work after 9pm")["sentence"] == "No work after 21:00"


def test_a_decision_and_a_refusal_say_their_times_on_your_clock(app: App) -> None:
    app.do("add", text="essay due mon 12:00 ~3h one-sitting")
    app.do("add", title="busy", when="fixed", start="2026-10-19T12:00", end="2026-10-19T23:30")
    chore = app.do("add", title="call bank", duration_min=60)["item"]["id"]
    app.full("pin", payload={"id": chore, "start": "2026-10-19T10:00", "end": "2026-10-19T11:00"}, provisional=False)
    app.do("replan")
    clock(app, "24h")
    lock = [d for d in app.do("status")["decisions"] if d["kind"] == "lock"]
    assert lock[0]["detail"].startswith("Locked at Mon 10:00, it makes other work")
    app.do("start", id=chore)
    app.at("2026-10-19T09:30")
    with pytest.raises(FieldError, match="must be after you started, at 09:00"):
        app.do("stop", at="2026-10-19T08:00")


def test_the_plans_notices_are_written_again_on_the_clock_you_change_to(app: App) -> None:
    app.do("add", title="Lab", when="fixed", start="2026-10-20T14:30", end="2026-10-20T16:00")
    app.do("add", title="Prelim", when="fixed", start="2026-10-20T15:00", end="2026-10-20T16:30")
    app.do("replan")
    assert "Lab and Prelim overlap on Tue Oct 20 at 3pm" in app.do("status")["notices"]
    clock(app, "24h")
    app.do("replan")  # the server's planner does this after any change of settings
    assert "Lab and Prelim overlap on Tue Oct 20 at 15:00" in app.do("status")["notices"]


def test_a_command_on_the_24_hour_clock_leaves_the_12_hour_one_for_what_runs_after_it(app: App) -> None:
    clock(app, "24h")
    app.do("status")
    assert CLOCK.get() == "12h" and clock_time("15:00") == "3pm"
