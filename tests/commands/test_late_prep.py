"""Work that's pointless once late, like an exam's prep, in the late options (19 Nov, a user's notes: "if prep is going
to be 'late', as in finish after the exam, there is not much use in rescheduling it bc the exam is over. ideally leave
it late and/or ask if other events should be skipped instead. for instance, it could tell me to skip engineering
seminar which is currently marked as 'im going'"). Whole system, through the commands and the planner; Monday
19 Oct 2026 9am in New York."""

import json
from pathlib import Path

import pytest

from friday.planner.service import replan
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    made = new_app(tmp_path)
    made.conn.execute(
        "INSERT INTO kv (user_id, key, value) VALUES (1, 'event_ratings', ?)",
        [json.dumps({"engineering seminar": {"level": "likely", "reason": "a talk you signed up for"}})],
    )
    # Monday is taken but for the seminar; the prep is due at the exam Tuesday 9am and can't fit around it
    made.do("add", title="CS 2110 Lecture", when="fixed", start="2026-10-19T09:00", end="2026-10-19T16:00")
    made.do("add", title="Engineering seminar", when="fixed", start="2026-10-19T16:00", end="2026-10-19T20:00")
    made.do("add", title="Lab", when="fixed", start="2026-10-19T20:00", end="2026-10-20T09:00")
    return made


def late_options(app: App) -> list[dict]:
    replan(app.conn, app.now_utc)
    return app.do("triage")["options"]


def test_prep_that_is_pointless_late_isnt_offered_a_later_due(app: App) -> None:
    app.do("add", title="brain dump study", preset="Assignment", duration_min=120, due="2026-10-20T09:00", expires=True)
    actions = [o["action"] for o in late_options(app)]
    assert actions, "it is late: there are options"
    assert not [a for a in actions if "due" in a and "later" in a], actions


def test_it_offers_skipping_an_event_you_said_youre_going_to_saying_so(app: App) -> None:
    app.do("event_going", title="Engineering seminar")
    app.do("add", title="brain dump study", preset="Assignment", duration_min=120, due="2026-10-20T09:00", expires=True)
    skips = [o for o in late_options(app) if o["skip_title"] == "Engineering seminar"]
    assert len(skips) == 1
    assert "You said you're going" in skips[0]["side_effects"]


def test_other_work_still_gets_a_later_due_and_your_going_is_still_kept(app: App) -> None:
    app.do("event_going", title="Engineering seminar")
    app.do("add", title="Problem set", preset="Assignment", duration_min=120, due="2026-10-20T09:00")
    options = late_options(app)
    assert any("Problem set's due 1 day later" in o["action"] for o in options)
    assert "Engineering seminar" not in [o["skip_title"] for o in options]  # "I'm going" stops offering it
