"""Two lists, not one (24 Nov, the new pipeline tests: "I'm going" to a free event kept its id in `events_going`, and
"I go to this" in What gives kept a title in the same list; sorting ids with titles crashed the second). Each has its
own list; what was saved together before is read by each as its own kind, and moved apart on the next change."""

import json
from pathlib import Path

import pytest

from friday.planner.snapshot import going_ids, gone_to_titles
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def free_event(app: App) -> int:
    return app.do("add", title="Drop-in hours", when="fixed", start="2026-10-21T13:00", end="2026-10-21T14:00",
                  free=True)["item"]["id"]  # fmt: skip


def test_going_to_a_free_event_then_another_by_title_both_kept(app: App) -> None:
    free = free_event(app)
    app.do("event_choice", id=free, choice="going")
    app.do("event_going", title="Movie night")
    app.do("event_going", title="Book club")
    assert going_ids(app.conn) == {free}
    assert {"movie night", "book club"} <= {t.lower() for t in gone_to_titles(app.conn)}


def test_what_was_saved_together_before_is_read_and_moved_apart(app: App) -> None:
    free = free_event(app)
    app.conn.execute("INSERT OR REPLACE INTO kv (user_id, key, value) VALUES (1, 'events_going', ?)",
                     [json.dumps([free, "seminar"])])  # fmt: skip  (as saved before 24 Nov)
    assert going_ids(app.conn) == {free} and gone_to_titles(app.conn) == {"seminar"}
    app.do("event_going", title="Movie night")  # no crash
    app.do("event_choice", id=free, choice="skip")  # the ids rewritten
    assert going_ids(app.conn) == set()
    assert "seminar" in gone_to_titles(app.conn)  # kept, in its own list now
