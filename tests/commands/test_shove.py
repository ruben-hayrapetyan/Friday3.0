"""Shove (DESIGN §15.4): ranges that can't be read are refused in words, keeping the must-dos locks their planned
time and clears only the gaps around it, and unshove with nothing shoved says so."""

from pathlib import Path

import pytest

from friday.core.items import FieldError
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


@pytest.mark.parametrize(
    ("said", "answer"),
    [
        ("", "say how long, or which times or days"),
        ("12:00-13:00 blah", "'blah' isn't a day"),
        ("lots", "'lots' isn't a length, a time range, `rest` or `day …`"),
        ("day blursday", "'blursday' isn't a day"),
    ],
)
def test_a_range_that_cannot_be_read_is_refused_in_words(app: App, said: str, answer: str) -> None:
    with pytest.raises(FieldError, match=answer) as refused:
        app.do("shove", range=said)
    assert refused.value.field == "range"


def test_keeping_the_must_dos_locks_their_time_and_clears_the_gaps(app: App) -> None:
    essay = app.do("add", text="essay due mon 17:00 ~4h")["item"]["id"]
    app.do("add", text="laundry ~1h")  # planned on another day: not kept
    app.do("replan")
    asked = app.do("shove", range="09:00-17:00")
    assert asked["created"] == [] and [m["item_id"] for m in asked["must_do"]] == [essay]
    assert asked["message"] == "Clearing that would make these later: essay (+4 h)"
    out = app.do("shove", range="09:00-17:00", decision="keep_must_dos")
    assert out["message"] == "Cleared today 12–12:15pm; today 1:15–5pm" and out["day"] == "2026-10-19"
    assert len(out["created"]) == 2
    locks = [(p["item_id"], p["start_utc"], p["end_utc"], p["kind"]) for p in app.table("pins")]
    assert locks == [
        (essay, "2026-10-19T13:00Z", "2026-10-19T16:00Z", "locked"),
        (essay, "2026-10-19T16:15Z", "2026-10-19T17:15Z", "locked"),
    ]


def test_unshove_with_nothing_shoved_says_so(app: App) -> None:
    with pytest.raises(FieldError, match="no shove to remove") as refused:
        app.do("unshove")
    assert refused.value.field == "id"
