"""The Inbox asks one thing once, and says where it comes from (23 Nov, the user's screenshot: "You skip breakfast on
most weekdays, but your rule says it's never skipped", asked twice, weekdays and weekends, about a rule they didn't
recognize; "i would like it if you could include evidence (like in emails) of the two rules that conflict and when";
then, of one question per meal: "it should just overall encompass duplicates"). Two questions about the same thing
are one, with both sides' evidence, and one answer settles it. Monday 19 Oct 2026, 9am (the helpers' now)."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from tests.commands.helpers import App, new_app

FIRST = date(2026, 9, 28)  # three weeks of breakfasts before today


@pytest.fixture
def app(tmp_path: Path) -> App:
    app = new_app(tmp_path)
    app.do("settings_set", key="meal_tracking", value={"on": True})
    return app


def breakfasts(app: App, eaten_weekdays: int = 3, eaten_weekends: int = 1) -> None:
    """Three weeks of breakfast, mostly skipped: eaten only on the first few weekdays and weekend days."""
    seen = {"weekdays": 0, "weekends": 0}
    for n in range(21):
        day = FIRST + timedelta(days=n)
        group = "weekends" if day.weekday() >= 5 else "weekdays"
        seen[group] += 1
        if seen[group] <= (eaten_weekdays if group == "weekdays" else eaten_weekends):
            app.do("meal_log", kind="breakfast", start=f"{day}T08:00", end=f"{day}T08:20")
        else:
            app.do("meal_skip", kind="breakfast", date=day.isoformat())


def asked(app: App) -> list[dict]:
    return [d for d in app.do("status")["decisions"] if d["kind"] == "learned"]


def test_skipping_breakfast_weekdays_and_weekends_is_one_question_with_its_evidence(app: App) -> None:
    app.do("rule_add", text="Meals are never skipped for work", strength="Always")
    breakfasts(app)
    [question] = asked(app)  # was two: weekdays, then weekends
    assert question["title"] == "You skip breakfast on most days, but your rule says it's never skipped"
    lines = {e["label"]: e["text"] for e in question["evidence"]}
    assert lines["Your rule"] == "“Meals are never skipped for work”, which you added on Mon 19 Oct"
    assert lines["What Friday saw"] == (
        "Breakfast skipped on 12 of 15 weekdays and 5 of 6 weekend days, Mon 28 Sep to Sun 18 Oct"
    )


def test_one_answer_settles_it(app: App) -> None:
    app.do("rule_add", text="Meals are never skipped for work", strength="Always")
    breakfasts(app)
    [question] = asked(app)
    app.do("conflict_resolve", key=question["key"].removeprefix("learned:"), option="keep")
    assert asked(app) == []  # neither half comes back


def test_skipped_on_weekdays_only_says_weekdays(app: App) -> None:
    app.do("rule_add", text="Meals are never skipped for work", strength="Always")
    breakfasts(app, eaten_weekdays=3, eaten_weekends=6)
    [question] = asked(app)
    assert question["title"] == "You skip breakfast on most weekdays, but your rule says it's never skipped"
    lines = {e["label"]: e["text"] for e in question["evidence"]}
    assert lines["What Friday saw"] == "Breakfast skipped on 12 of 15 weekdays, Mon 28 Sep to Fri 16 Oct"


def test_two_meals_are_two_questions(app: App) -> None:
    app.do("rule_add", text="Meals are never skipped for work", strength="Always")
    breakfasts(app)
    for n in range(21):
        day = FIRST + timedelta(days=n)
        app.do("meal_skip", kind="lunch", date=day.isoformat())
    titles = sorted(q["title"] for q in asked(app))
    assert titles == [
        "You skip breakfast on most days, but your rule says it's never skipped",
        "You skip lunch on most days, but your rule says it's never skipped",
    ]
