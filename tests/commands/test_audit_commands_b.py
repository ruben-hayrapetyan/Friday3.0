"""Bugs found auditing the commands (12 Nov): learning and rules."""

import json
from pathlib import Path

import pytest

from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=3)


def profile_row(app: App, version: int, theta: dict, status: str, pending: str | None = None) -> None:
    app.conn.execute(
        "INSERT INTO learned_profile (version, created_utc, theta, proposals, wall_decisions, evidence, status) "
        "VALUES (?, 'x', ?, ?, ?, '{}', ?)",
        [version, json.dumps(theta), json.dumps({"pending": pending, "accepted": [], "refused": []}),
         json.dumps({"pending": None, "decided": {}}), status],
    )  # fmt: skip


def test_starting_the_state_over_keeps_the_weights_in_use_not_a_suggestion_waiting(app: App) -> None:
    profile_row(app, 1, {"late_night": 1.2}, "active")
    profile_row(app, 2, {"late_night": 4.0}, "suggested")
    app.do("learn_reset", module="state")
    assert app.do("learning")["multipliers"] == {"late_night": 1.2}  # the suggestion was never approved


def test_strongly_on_a_learned_rule_is_three_times_once_and_prefer_takes_it_back(app: App) -> None:
    profile_row(app, 1, {}, "suggested", pending="fri_sat:late:any")
    app.do("proposal_answer", kind="rule", name="fri_sat:late:any", yes=True)
    name = "learned:fri_sat:late:any"

    def weight() -> float:
        return next(r["weight"] for r in app.do("settings")["rules"] if r["name"] == name)

    app.do("rule_set", name=name, strength="Strongly")
    app.do("rule_set", name=name, strength="Strongly")
    assert weight() == 3.0
    assert next(r for r in app.do("rules") if r["name"] == name)["strength"] == "Strongly"
    app.do("rule_set", name=name, strength="Prefer")
    assert weight() == 1.0
