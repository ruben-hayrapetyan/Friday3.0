"""A rule keeps your words and says what it clashes with (23 Nov: on the Rules page the user typed "Things that can
happen during other events can't happen during meals"; Claude's reading saved it as "Meals are never skipped for work",
a minute later the Inbox asked about "your rule" in words they never wrote, and nothing said the new rule contradicted
"Let Friday decide breakfast from your habits" or covered "Lunch and dinner are never skipped for work"). Meal rules
weren't compared at all; the words you typed were kept but never shown. Monday 19 Oct 2026, 9am."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from tests.commands.helpers import App, new_app

TYPED = "Things that can happen during other events can't happen during meals"
CLAUDE = '{"kind": "meals_kept", "events": ["breakfast", "lunch", "dinner"]}'
CLAUDE_FIELDS = {"kind": "meals_kept", "events": ["breakfast", "lunch", "dinner"]}


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def read(app: App, text: str, overrides: str = "{}") -> dict:
    return app.do("rule_read", text=text, overrides=overrides)


def test_keeping_meals_says_it_contradicts_letting_friday_decide_breakfast(app: App) -> None:
    app.do("rule_add", text="Let Friday decide breakfast from your habits", strength="Always")
    found = read(app, TYPED, CLAUDE)["conflicts"]
    [clash] = [c for c in found if not c["overlap"]]
    assert clash["other_sentence"] == "Let Friday decide breakfast from your habits"
    assert "breakfast" in clash["why"]


def test_keeping_all_meals_says_it_covers_keeping_lunch_and_dinner(app: App) -> None:
    app.do("rule_add", text="Lunch and dinner are never skipped for work", strength="Always")
    found = read(app, TYPED, CLAUDE)["conflicts"]
    [same] = [c for c in found if c["overlap"]]
    assert same["other_sentence"] == "Lunch and dinner are never skipped for work"


def test_different_meals_dont_clash(app: App) -> None:
    app.do("rule_add", text="Let Friday decide breakfast from your habits", strength="Always")
    assert read(app, "Lunch and dinner are never skipped for work")["conflicts"] == []


def test_the_rules_list_keeps_what_you_typed(app: App) -> None:
    app.do("rule_add", text=TYPED, strength="Always", overrides=CLAUDE_FIELDS)
    [mine] = [r for r in app.do("rules") if r["name"].startswith("you:")]
    assert mine["sentence"] == "Meals are never skipped for work" and mine["words"] == TYPED


def test_the_inbox_quotes_what_you_typed(app: App) -> None:
    app.do("settings_set", key="meal_tracking", value={"on": True})
    app.do("rule_add", text=TYPED, strength="Always", overrides=CLAUDE_FIELDS)
    first = date(2026, 9, 28)
    for n in range(21):
        app.do("meal_skip", kind="breakfast", date=(first + timedelta(days=n)).isoformat())
    [question] = [d for d in app.do("status")["decisions"] if d["kind"] == "learned"]
    lines = {e["label"]: e["text"] for e in question["evidence"]}
    assert lines["Your rule"] == (
        f"“Meals are never skipped for work”, from your words “{TYPED}”, which you added on Mon 19 Oct"
    )
