"""Start over before anything was learned (23 Nov, found while debugging 0.6.6; in 0.6.5 too): Insights' "Start over"
for learned lengths on a Friday with no learned weights yet saved a profile whose weights were null, and from then on
every plan failed reading it ("Friday couldn't make a new plan"; the questions job erred every minute). No weights
learned means the weights as you set them: when a profile is saved, and when one is read."""

import json
from pathlib import Path

import pytest

from friday.planner.service import replan
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    app = new_app(tmp_path, now="2026-10-01T09:00", horizon_days=2)
    app.do("add", text="essay 1h due fri")
    return app


def profiles(app: App) -> list[dict]:
    return [dict(r) for r in app.conn.execute("SELECT version, theta, status FROM learned_profile ORDER BY version")]


def planned(app: App) -> bool:
    replan(app.conn, app.now_utc)
    plan = app.table("plans")[-1]
    return any(b["plan_id"] == plan["id"] for b in app.table("blocks"))


@pytest.mark.parametrize("module", ["durations", "energy", "state", "proposals"])
def test_starting_a_part_over_before_anything_was_learned_keeps_planning(app: App, module: str) -> None:
    assert not profiles(app)  # a new Friday: nothing learned
    app.do("learn_reset", module=module)
    [saved] = profiles(app)
    theta = json.loads(saved["theta"])
    assert isinstance(theta, dict) and set(theta.values()) <= {1.0}  # the weights as you set them, not null
    assert planned(app)


def test_a_friday_the_bug_already_broke_plans_again(app: App) -> None:
    """A profile saved by the bug (weights null, active) is read as the weights as set: Fridays that hit it plan again
    without anything for the user to do."""
    app.conn.execute(
        "INSERT INTO learned_profile (version, created_utc, theta, answer_noise, state, proposals, wall_decisions, "
        "evidence, status) VALUES (1, '2026-10-01T13:00:00Z', 'null', 0.05, NULL, '{}', '{}', 'null', 'active')"
    )
    assert planned(app)
    assert app.do("learning")["multipliers"] == {}  # Insights reads it as nothing learned, as before


def test_starting_a_part_over_keeps_weights_that_were_learned(app: App) -> None:
    app.do("learn_reset", module="weights")  # weights in use, as set
    learned = {name: 1.0 for name in json.loads(profiles(app)[-1]["theta"])}
    some = next(iter(learned))
    learned[some] = 1.7
    app.conn.execute("UPDATE learned_profile SET theta = ? WHERE status = 'active'", [json.dumps(learned)])
    app.do("learn_reset", module="durations")
    assert json.loads(profiles(app)[-1]["theta"])[some] == 1.7  # only lengths started over
    assert planned(app)
