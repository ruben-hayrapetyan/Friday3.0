"""An event's category and who said (31 Oct: categories by word lists were "a very fragile way to do this"; clues
instead, Claude asked only within the call Friday already makes, and your choice before all)."""

import json
from pathlib import Path

import pytest

from friday.commands.rating import rate_upcoming
from friday.core.items import FieldError
from tests.commands.helpers import App, new_app
from tests.ingest.test_rating import Answering

CATEGORIES = {
    "categories": [
        {"name": "Classes", "slug": "class", "color": "blue", "pattern": r"\blecture\b"},
        {"name": "Club meetings", "slug": "club", "color": "orange", "pattern": ""},
        {"name": "Social", "slug": "social", "color": "pink", "pattern": "poker"},
        {"name": "Professional", "slug": "professional", "color": "purple", "pattern": ""},
    ]
}


@pytest.fixture
def app(tmp_path: Path) -> App:
    made = new_app(tmp_path)
    made.do("settings_set", key="categories", value=CATEGORIES)
    return made


def event(app: App, title: str, day: int = 20, at: str = "18:00") -> int:
    start = f"2026-10-{day}T{at}"
    end = f"2026-10-{day}T{int(at[:2]) + 1:02d}{at[2:]}"
    return int(app.do("add", title=title, when="fixed", start=start, end=end)["item"]["id"])


def facts(app: App, item_id: int) -> tuple[str | None, str | None]:
    item = app.do("item", id=item_id)["item"]
    return item["category"], item["category_by"]


def claude_said(app: App, said: dict[str, str]) -> None:
    ratings = {title.lower(): {"level": "optional", "reason": "x", "category": c} for title, c in said.items()}
    app.conn.execute(
        "INSERT OR REPLACE INTO kv (user_id, key, value) VALUES (1, 'event_ratings', ?)", [json.dumps(ratings)]
    )


def test_your_words_then_claude_and_each_says_who(app: App) -> None:
    lecture, poker, chess = event(app, "CS 2112 Lecture"), event(app, "Poker night", 21), event(app, "Chess Club", 22)
    claude_said(app, {"Chess Club": "Club meetings"})
    assert facts(app, lecture) == ("Classes", "always")
    assert facts(app, poker) == ("Social", "always")
    assert facts(app, chess) == ("Club meetings", "claude")


def test_an_empty_word_list_finds_nothing(app: App) -> None:
    dentist = event(app, "Dentist")
    assert facts(app, dentist) == (None, None)


def test_your_choice_comes_first_for_every_event_with_its_title_and_can_be_undone(app: App) -> None:
    first, second = event(app, "Poker night", 20), event(app, "Poker night", 27)
    chose = app.full("event_category", payload={"id": first, "category": "Club meetings"})
    assert chose.result["message"] == "Poker night is Club meetings now, and events like it follow"
    assert facts(app, first) == facts(app, second) == ("Club meetings", "you")
    app.do("undo", command_id=chose.command_id)
    assert facts(app, second) == ("Social", "always")


def test_none_and_back_to_friday(app: App) -> None:
    poker = event(app, "Poker night")
    app.do("event_category", id=poker, category="")
    assert facts(app, poker) == (None, "you")
    app.do("event_category", id=poker, category=None)
    assert facts(app, poker) == ("Social", "always")


def test_what_you_choose_spreads_to_events_like_it_before_claude(app: App) -> None:
    for day, title in ((20, "Chess Club"), (21, "Poker night"), (22, "Jane Street info session"), (23, "Math lecture")):
        event(app, title, day)
    gbody = event(app, "CATC GBody", 24)
    mandatory = event(app, "[CATC - Mandatory] GBody", 25)
    claude_said(app, {"Chess Club": "Club meetings", "Jane Street info session": "Professional",
                      "CATC GBody": "Social", "[CATC - Mandatory] GBody": "Social"})  # fmt: skip
    assert facts(app, mandatory) == ("Social", "claude")
    app.do("event_category", id=gbody, category="Club meetings")
    assert facts(app, mandatory) == ("Club meetings", "similar")
    assert app.do("item", id=mandatory)["item"]["category_like"] == "CATC GBody"


def test_an_unsure_guess_is_offered_not_painted(app: App) -> None:
    event(app, "Jane Street info session", 20)
    event(app, "Citadel info session", 21)
    claude_said(app, {"Jane Street info session": "Professional", "Citadel info session": "Professional"})
    talk = event(app, "Info night", 22)
    item = app.do("item", id=talk)["item"]
    assert item["category"] is None and item["category_color"] is None
    assert item["category_hint"] == "Professional"


def test_choosing_checks_the_event_and_the_category(app: App) -> None:
    poker = event(app, "Poker night")
    task = app.do("add", title="Essay", due="2026-10-22T17:00", duration_min=60)["item"]["id"]
    with pytest.raises(FieldError):
        app.do("event_category", id=poker, category="Sports")
    with pytest.raises(FieldError):
        app.do("event_category", id=task, category="Social")


def test_a_merge_takes_your_choices_along(app: App) -> None:
    chess = event(app, "Chess Club")
    app.do("event_category", id=chess, category="Club meetings")
    app.do("category_merge", name="Club meetings", into="Social")
    assert facts(app, chess) == ("Social", "you")


def test_a_category_deleted_since_claude_chose_it_is_asked_about_again(app: App) -> None:
    event(app, "Chess Club")
    claude_said(app, {"Chess Club": "Chess"})
    answer = {"events": [{"title": "Chess Club", "level": "likely", "reason": "a club", "category": "Club meetings"}]}
    assert rate_upcoming(app.conn, app.now_utc, client=Answering(json.dumps(answer))) == 1


def test_claude_is_told_what_friday_knows_and_what_each_category_has_meant(app: App) -> None:
    for day, title in ((20, "CUAI meeting"), (21, "CUAI zoom")):
        event(app, title, day)
    claude_said(app, {"CUAI meeting": "Club meetings", "CUAI zoom": "Club meetings"})
    new = event(app, "CUAI subteam meeting", 22)
    app.conn.execute("UPDATE items SET location = 'Gates 114' WHERE id = ?", [new])
    ai = Answering(json.dumps({"events": [{"title": "CUAI subteam meeting", "level": "likely", "reason": "club",
                                            "category": "Club meetings"}]}))  # fmt: skip
    assert rate_upcoming(app.conn, app.now_utc, client=ai) == 1
    request = ai.asked[0]
    text = request["messages"][0]["content"][0]["text"]
    assert '- CUAI subteam meeting\n    place: Gates 114; like "CUAI meeting" (Club meetings)' in text
    assert "Club meetings: CUAI meeting, CUAI zoom" in request["system"]
    ratings = json.loads(app.conn.execute("SELECT value FROM kv WHERE key = 'event_ratings'").fetchone()[0])
    assert ratings["cuai subteam meeting"]["category"] == "Club meetings"  # its title, without what was told
