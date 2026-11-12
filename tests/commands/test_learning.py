"""Learning through the registry (DESIGN §21): questions about tomorrow, answers, the refit after the review,
approving or resetting, drags, rule proposals, wall questions and check-ins."""

import json
from pathlib import Path

import pytest

from friday.commands.refit import prepare_questions
from friday.planner.service import replan
from friday.planner.store import current_plan
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    app = new_app(tmp_path, horizon_days=3)
    for text in ("essay due wed 17:00 ~3h", "reading due wed ~2h", "laundry ~1h", "PS2 due wed 12:00 ~2h", "gym ~1h"):
        app.do("add", text=text)
    replan(app.conn, app.now_utc)
    return app


def answer_all(app: App, answer: str = "a") -> None:
    for q in app.do("questions")["comparisons"]:
        app.do("compare_answer", id=q["id"], answer=answer)


def test_up_to_three_questions_a_day_show_two_versions_of_tomorrow(app: App) -> None:
    made = prepare_questions(app.conn, app.now_utc)
    asked = app.do("questions")["comparisons"]
    assert 1 <= made <= 3 and len(asked) == made and {q["day"] for q in asked} == {"2026-10-20"}
    assert all(q["a"] != q["b"] for q in asked)
    assert prepare_questions(app.conn, app.now_utc) == 0  # the day's are asked


def test_answers_are_fitted_after_the_review_and_wait_for_approval(app: App) -> None:
    prepare_questions(app.conn, app.now_utc)
    answer_all(app)
    app.at("2026-10-19T21:00").do("review_submit")
    learned = app.do("learning")
    assert learned["version"] == 0 and learned["suggested"] and learned["comparisons"] == len(app.table("comparisons"))
    app.do("learn_apply", version=learned["suggested"]["version"])
    replan(app.conn, app.now_utc)
    assert json.loads(current_plan(app.conn)["report"])["profile_version"] == learned["suggested"]["version"]
    assert app.do("learning")["version"] == learned["suggested"]["version"]


def test_auto_mode_moves_a_weight_at_most_half_again_a_week(app: App) -> None:
    app.do("settings_set", key="learn", value={"weights": "auto"})
    prepare_questions(app.conn, app.now_utc)
    answer_all(app)
    app.at("2026-10-19T21:00").do("review_submit")
    theta = app.do("learning")["multipliers"]
    assert theta and all(1 / 1.5 - 1e-9 <= t <= 1.5 + 1e-9 for t in theta.values())


def test_a_reset_puts_the_hand_set_weights_back(app: App) -> None:
    app.do("settings_set", key="learn", value={"weights": "auto"})
    prepare_questions(app.conn, app.now_utc)
    answer_all(app)
    app.at("2026-10-19T21:00").do("review_submit")
    app.do("learn_reset", module="weights")
    assert set(app.do("learning")["multipliers"].values()) == {1.0}


def test_a_block_you_move_is_a_comparison_your_version_won(app: App) -> None:
    item = app.do("items")[0]["id"]
    app.do("pin", id=item, start="2026-10-19T15:00", kind="preferred")
    replan(app.conn, app.now_utc)
    drags = app.table("comparisons")
    assert [(d["source"], d["answer"]) for d in drags] == [("drag", "a")]
    assert app.do("learning")["drags"] == 1


def test_a_proposed_rule_is_added_only_on_yes(app: App) -> None:
    app.conn.execute(
        "INSERT INTO learned_profile (version, created_utc, theta, proposals, wall_decisions, evidence, status) "
        "VALUES (1, 'x', '{}', ?, ?, '{}', 'suggested')",
        [json.dumps({"pending": "fri_sat:late:any", "accepted": [], "refused": []}),
         json.dumps({"pending": None, "decided": {}})],
    )  # fmt: skip
    proposal = app.do("questions")["proposal"]
    assert proposal["sentence"].startswith("You seem to prefer no work on Friday and Saturday late evenings")
    app.do("proposal_answer", kind="rule", name=proposal["name"], yes=True)
    assert "learned:fri_sat:late:any" in [r["name"] for r in app.do("settings")["rules"]]
    assert app.do("questions")["proposal"] is None


def test_work_inside_a_never_window_asks_once_and_no_softens_it(app: App) -> None:
    rules = app.do("settings")["rules"] + [
        {
            "type": "time_preference",
            "name": "no_late_work",
            "params": {"start": "07:00", "end": "08:00", "price": "forbid"},
        }
    ]
    app.do("settings_set", key="rules", value=rules)
    item = app.do("items")[0]["id"]
    app.do("log", id=item, start="2026-10-19T07:15", end="2026-10-19T07:45")
    prepare_questions(app.conn, app.now_utc)
    answer_all(app)
    app.at("2026-10-19T21:00").do("review_submit")
    assert app.do("questions")["wall"]["rule"] == "no_late_work"
    app.do("proposal_answer", kind="wall", name="no_late_work", yes=False)
    softened = next(r for r in app.do("settings")["rules"] if r["name"] == "no_late_work")
    assert softened["params"]["price"] == 10.0 and app.do("questions")["wall"] is None


def test_a_check_in_is_asked_only_while_state_inference_is_on(app: App) -> None:
    assert not app.do("questions")["checkin"]
    app.do("settings_set", key="learn", value={"state_inference": "on"})
    assert app.do("questions")["checkin"]
    app.do("checkin", state="tired")
    assert not app.do("questions")["checkin"]


def test_with_learning_off_nothing_is_asked_or_fitted(app: App) -> None:
    app.do("settings_set", key="learn", value={"weights": "off"})
    assert prepare_questions(app.conn, app.now_utc) == 0
    app.at("2026-10-19T21:00").do("review_submit")
    assert app.table("learned_profile") == [] and app.do("learning")["suggested"] is None


def many_answers(app: App, copies: int = 14) -> None:
    """Today's questions answered, then the same answers again as if from other evenings (3 × 15 = 45)."""
    prepare_questions(app.conn, app.now_utc)
    answer_all(app)
    columns = "user_id, asked_utc, plan_a, plan_b, features_a, features_b, answer, answered_utc, source, dials"
    for _ in range(copies):
        app.conn.execute(f"INSERT INTO comparisons ({columns}) SELECT {columns} FROM comparisons WHERE id <= 3")


def test_a_rule_is_proposed_only_once_its_week_comes(app: App) -> None:
    many_answers(app)
    app.at("2026-10-19T21:00").do("review_submit")
    learned = app.do("learning")
    assert learned["comparisons"] == 45 and learned["proposals"]["pending"] is None  # proposals start in week 6
    assert 0 < learned["answer_noise"] < 0.15  # enough answers to measure how noisy they are


def test_enough_answers_from_the_proposal_week_propose_the_best_rule(app: App) -> None:
    app.do("settings_set", key="learn", value={"proposal_from_week": 0, "proposal_every_weeks": 1})
    many_answers(app)
    app.at("2026-10-19T21:00").do("review_submit")
    assert app.do("learning")["proposals"]["pending"] == "weekdays:afternoon:any"
    assert app.do("questions")["proposal"]["name"] == "weekdays:afternoon:any"


def test_no_proposal_when_proposals_are_off(app: App) -> None:
    app.do("settings_set", key="learn", value={"proposals": "off", "proposal_from_week": 0, "proposal_every_weeks": 1})
    many_answers(app)
    app.at("2026-10-19T21:00").do("review_submit")
    assert app.do("learning")["proposals"]["pending"] is None


def test_with_state_inference_on_the_refit_records_this_weeks_state(app: App) -> None:
    app.do("settings_set", key="learn", value={"state_inference": "on"})
    prepare_questions(app.conn, app.now_utc)
    answer_all(app)
    app.at("2026-10-19T21:00").do("review_submit")
    state = app.do("learning")["state"]
    assert len(state["h"]) == 4 and state["on"] is False and state["mood"] == "normal"


def test_this_weeks_check_in_reaches_the_state(app: App) -> None:
    app.do("settings_set", key="learn", value={"state_inference": "on"})
    prepare_questions(app.conn, app.now_utc)
    answer_all(app)
    app.do("checkin", state="tired")
    app.at("2026-10-19T21:00").do("review_submit")
    assert app.do("learning")["state"]["mood"] == "tired"
