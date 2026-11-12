"""Bugs an audit of the item, repeat, inbox and review commands found (12 Nov), each kept fixed: a tag or a source
renamed to a name already taken was a database error, a done with a negative time taught Friday a negative length,
something that happened added in a review could end before it began or after now, skipping a time that was done
undid its done, a stopped repeat edited came back on its own, and starting a running repeat again brought back the
times you had dropped."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from friday.core.items import FieldError
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=3)


def test_a_tag_renamed_to_one_you_have_is_refused_in_words(app: App) -> None:
    app.do("area_add", name="Physics")
    chem = app.do("area_add", name="Chem")["id"]
    with pytest.raises(FieldError, match="Physics"):
        app.do("area_edit", id=chem, name="Physics")  # was sqlite3.IntegrityError
    with pytest.raises(FieldError, match="physics"):
        app.do("area_edit", id=chem, name="physics")  # was a second tag that reads the same
    # its own name in other letters is a rename, not a clash
    assert app.do("area_edit", id=chem, name="CHEM")["name"] == "CHEM"


def test_a_tag_needs_a_name(app: App) -> None:
    with pytest.raises(FieldError, match="name"):
        app.do("area_add", name="  ")
    chem = app.do("area_add", name="Chem")["id"]
    with pytest.raises(FieldError, match="name"):
        app.do("area_edit", id=chem, name="")


def test_a_source_renamed_to_one_you_read_is_refused_in_words(app: App) -> None:
    app.do("source_add", name="Canvas", url="https://example.edu/a.ics")
    app.do("source_add", name="Club", url="https://example.edu/b.ics")
    club = next(r["id"] for r in app.table("sources") if r["name"] == "Club")
    with pytest.raises(FieldError, match="Canvas"):
        app.do("source_edit", id=club, name="Canvas")  # was sqlite3.IntegrityError
    app.do("source_edit", id=club, name="Club", trusted=True)  # its own name again is fine


def test_done_with_a_negative_time_is_refused(app: App) -> None:
    item = app.do("add", title="Essay", duration_min=60)["item"]["id"]
    with pytest.raises((FieldError, ValidationError), match="actual_min|minutes"):
        app.do("done", id=item, actual_min=-30)
    with pytest.raises((FieldError, ValidationError), match="actual_min|minutes"):
        app.do("done", id=item, actual_min=0)  # a length of nothing would be learned from too (DoneInput: at least 1)
    assert not app.table("completions")
    app.do("done", id=item)  # done without a time is still fine


def test_something_that_happened_in_a_review_must_end_after_it_starts_and_by_now(app: App) -> None:
    app.at("2026-10-19T18:00")
    item = app.do("add", title="Reading", duration_min=120)["item"]["id"]
    with pytest.raises(FieldError, match="end"):
        app.do("review_submit", entries=[{"item_id": item, "start": "2026-10-19T15:00", "end": "2026-10-19T14:00"}])
    with pytest.raises(FieldError, match="end"):
        app.do("review_submit", entries=[{"item_id": item, "start": "2026-10-19T17:00", "end": "2026-10-19T20:00"}])
    assert not [p for p in app.table("progress") if p["item_id"] == item]
    app.do("review_submit", entries=[{"item_id": item, "start": "2026-10-19T14:00", "end": "2026-10-19T15:00"}])
    assert [p["minutes"] for p in app.table("progress") if p["item_id"] == item] == [60]


def test_a_review_entry_for_an_item_that_isnt_there_says_so(app: App) -> None:
    app.at("2026-10-19T18:00")
    with pytest.raises(FieldError, match="T999"):  # was sqlite3.IntegrityError (FOREIGN KEY)
        app.do("review_submit", entries=[{"item_id": 999, "start": "2026-10-19T14:00", "end": "2026-10-19T15:00"}])


def test_skipping_a_time_you_did_keeps_it_done(app: App) -> None:
    out = app.do("add", title="Run", duration_min=30, every="day")
    first = app.conn.execute(
        "SELECT id FROM items WHERE series_id = ? ORDER BY occurrence_date LIMIT 1", [out["series_id"]]
    ).fetchone()["id"]
    app.do("done", id=first)
    with pytest.raises(FieldError, match="done"):
        app.do("skip", id=first)
    assert app.conn.execute("SELECT status FROM items WHERE id = ?", [first]).fetchone()["status"] == "done"


def test_a_stopped_repeat_edited_stays_stopped(app: App) -> None:
    series_id = app.do("add", title="Gym", when="fixed", start="2026-10-19T18:00", end="2026-10-19T19:00",
                       every="day")["series_id"]  # fmt: skip
    app.do("series_stop", id=series_id)
    edited = app.do("series_edit", id=series_id, title="Gym (legs)")
    assert edited["occurrences"] == 0, "it was stopped: changing its name doesn't start it again"
    row = next(r for r in app.do("series_list") if r["id"] == edited["id"])
    assert not row["active"]
    assert app.do("series_resume", id=edited["id"])["occurrences"] > 0


def test_starting_a_running_repeat_again_keeps_the_times_you_dropped(app: App) -> None:
    series_id = app.do("add", title="Run", duration_min=30, every="day")["series_id"]
    second = app.conn.execute(
        "SELECT id FROM items WHERE series_id = ? ORDER BY occurrence_date LIMIT 1 OFFSET 1", [series_id]
    ).fetchone()["id"]
    app.do("drop", id=second)
    app.do("series_resume", id=series_id)  # it was running all along
    statuses = [r["status"] for r in app.table("items") if r["series_id"] == series_id]
    assert "dropped" in statuses, statuses
    assert app.conn.execute("SELECT status FROM items WHERE id = ?", [second]).fetchone()["status"] == "dropped"


def test_skipping_a_time_with_its_timer_running_stops_the_timer(app: App) -> None:
    # as drop does: a timer left on a skipped time ran on, counting time on something you said you won't do
    out = app.do("add", title="Run", duration_min=30, every="day")
    first = app.conn.execute(
        "SELECT id FROM items WHERE series_id = ? ORDER BY occurrence_date LIMIT 1", [out["series_id"]]
    ).fetchone()["id"]
    app.do("start", id=first)
    app.do("skip", id=first)
    assert not app.conn.execute("SELECT 1 FROM timer WHERE item_id = ?", [first]).fetchone()


def test_a_tag_renamed_keeps_the_rules_that_name_it(app: App) -> None:
    # a buffer by tag and a rule about a tag named it by its old name, so they stopped reaching anything (audit, 12 Nov)
    chem = app.do("area_add", name="Chem")["id"]
    rules = app.do("settings")["rules"]
    for r in rules:
        if r["name"] == "buffer":
            r["params"] = {**r["params"], "by_area": {"Chem": "15m", "Math": "10m"}}
    rules.append({"type": "time_preference", "name": "you:chem mornings", "weight": 2, "scope": {"area": "Chem"},
                  "params": {"start": "08:00", "end": "12:00"}})  # fmt: skip
    app.do("settings_set", key="rules", value=rules)
    app.do("area_edit", id=chem, name="Chemistry")
    after = {r["name"]: r for r in app.do("settings")["rules"]}
    assert after["buffer"]["params"]["by_area"] == {"Chemistry": "15m", "Math": "10m"}
    assert after["you:chem mornings"]["scope"] == {"area": "Chemistry"}
