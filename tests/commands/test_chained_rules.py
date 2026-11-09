"""Chained rules (8 Nov: "i don't want to do work between 7:10 am and 7:20 am and i also don't want to work between
7:30 am and 7:40 am", and only the first was read): a rule for each stretch of the day, previewed together and added in
one command that one Undo takes back. Glass box on the grammar's split, black box through the commands."""

from pathlib import Path

import pytest

from friday.core.rule_text import read_all, sentence
from tests.commands.helpers import App, new_app

YOURS = "i don't want to do work between 7:10 am and 7:20 am and i also don't want to work between 7:30 am and 7:40 am"


@pytest.mark.parametrize(
    ("text", "rules"),
    [
        (YOURS, ["No work between 7:10am and 7:20am", "No work between 7:30am and 7:40am"]),
        ("no work between 7:10 and 7:20 am and between 7:30 and 7:40 am",
         ["No work between 7:10am and 7:20am", "No work between 7:30am and 7:40am"]),
        ("no work 7:10-7:20am and 7:30-7:40am on weekdays",
         ["No work between 7:10am and 7:20am on weekdays", "No work between 7:30am and 7:40am on weekdays"]),
        ("no work between 7 and 8 am on mondays and between 9 and 10 am on fridays",
         ["No work between 7am and 8am on Mon", "No work between 9am and 10am on Fri"]),
        ("I strongly prefer no work 1-2pm, 5-6pm and 9-10pm",
         ["No work between 1pm and 2pm", "No work between 5pm and 6pm", "No work between 9pm and 10pm"]),
        ("work between 9am and 5pm", ["Work between 9am and 5pm"]),  # one stretch: one rule, as before
        ("keep sunday free and go easy on saturday", []),  # two rules of other kinds: still for the AI
    ],
)  # fmt: skip
def test_a_rule_for_each_stretch(text: str, rules: list[str]) -> None:
    assert [sentence(r) for r in read_all(text)[0]] == rules


def test_the_strongest_word_holds_for_all() -> None:
    assert read_all("never work from 12 to 1pm or from 6 to 7pm")[1] == "Always"


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def test_previewed_together_and_added_in_one_undo(app: App) -> None:
    before = len(app.do("rules"))
    preview = app.do("rule_read", text=YOURS)
    assert [preview["sentence"], *(a["sentence"] for a in preview["also"])] == [
        "No work between 7:10am and 7:20am", "No work between 7:30am and 7:40am",
    ]  # fmt: skip
    added = app.full("rule_add", payload={"text": YOURS})
    assert added.result["message"].startswith("Added 2 rules")
    mine = [r["sentence"] for r in app.do("rules") if r["name"].startswith("you:")]
    assert mine == ["No work between 7:10am and 7:20am", "No work between 7:30am and 7:40am"]
    app.do("undo", command_id=added.command_id)
    assert len(app.do("rules")) == before


def test_fields_you_set_yourself_make_it_one_rule(app: App) -> None:
    """The fields under a reading are one rule's: changing them is about the first."""
    out = app.do("rule_read", text=YOURS, overrides='{"days": ["mon"]}')
    assert out["also"] == [] and out["reading"]["days"] == ["mon"]
