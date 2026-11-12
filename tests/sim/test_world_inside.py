"""Glass box: the simulation loop's parts (sim/world.py) and the simulated student (sim/users.py), each on its own:
the metrics' summary, a refused command, a sick day, work still going at bedtime, sessions that run past Friday's
estimate, the student's answers to questions and the review, the hard deadlines counted at the end, and how close
the learned weights came. A whole day lived through the planner takes minutes, so the planner is left out where the
part doesn't need it."""

import json
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from friday.sim import world as world_module
from friday.sim.generate import Term, TermConfig
from friday.sim.users import MISSING, MOOD_EFFECT, SimUser, Taste
from friday.sim.world import Metrics, Working, World, recovery, run_term

MONDAY = date(2026, 8, 31)


class Dice:
    """A random generator that always rolls what it is told: `random()` gives `roll`, `integers` the first."""

    def __init__(self, roll: float = 0.0, delay: float = 0.0) -> None:
        self.roll, self.delay = roll, delay

    def random(self) -> float:
        return self.roll

    def exponential(self, mean: float) -> float:
        return self.delay

    def normal(self, mu: float, sigma: float) -> float:
        return 0.0

    def integers(self, n: int) -> int:
        return 0

    def choice(self, options: Any, p: Any = None) -> Any:
        return options[-1]


def make_world(tmp_path: Path, user: SimUser | None = None, sick: set[date] | None = None) -> World:
    term = Term(TermConfig(start=MONDAY, weeks=1), [], sick or set(), [])
    return World(tmp_path, term, user or SimUser(Dice()))


def add(world: World, title: str = "PS1", minutes: int = 60, due: str = "2026-08-31T20:00") -> int:
    return world.do("add", title=title, preset="Assignment", duration_min=minutes, due=due)["item"]["id"]


class Script:
    """Stands in for `World.do`: answers the queries it was given, records every command."""

    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers, self.calls = answers, []

    def __call__(self, command: str, /, **payload: Any) -> Any:
        self.calls.append((command, payload))
        return self.answers.get(command)

    def said(self, command: str) -> list[dict[str, Any]]:
        return [p for c, p in self.calls if c == command]


# Metrics


def test_the_summary_rounds_each_measure_and_reads_percentiles_of_the_solve_times() -> None:
    m = Metrics(days=2, hard_due=3, hard_missed=1, late_hours=4.26, plan_seconds=[1.0, 3.0, 2.0], moved_hours=3.0)
    m.lived_minutes, m.missed_minutes, m.predicted, m.recovery = 90, 30, [True, False, True, True], 0.876
    s = m.summary()
    assert s["plan seconds p50"] == 2.0 and s["plan seconds p90"] == 3.0 and s["replans"] == 3
    assert s["late hours"] == 4.3 and s["churn hours per day"] == 1.5 and s["adherence"] == 0.75
    assert s["accuracy of the weights in use"] == 0.75 and s["weight recovery"] == 0.88 and s["questions"] == 4


def test_an_empty_summary_has_no_accuracy_or_recovery_and_no_division_by_zero() -> None:
    s = Metrics().summary()
    assert s["plan seconds p50"] == 0.0 and s["adherence"] == 0.0 and s["churn hours per day"] == 0.0
    assert s["accuracy of the weights in use"] is None and s["weight recovery"] is None


# Commands and replans


def test_a_refused_command_is_noted_with_its_local_time_and_leaves_the_plan_clean(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    world.at("2026-08-31T08:00")
    world.dirty = False
    assert world.do("drop", id=9999) is None
    assert not world.dirty and world.metrics.errors[0].startswith("2026-08-31T08:00 drop: ")
    add(world)
    assert world.dirty  # a command that affects the plan, run


def test_a_replan_that_saved_no_plan_measures_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    world = make_world(tmp_path)
    world.dirty = True
    monkeypatch.setattr(world_module, "current_plan", lambda conn: None)
    world.replan()
    assert not world.dirty and world.last_replan == world.now and world.metrics.plan_seconds == []


# A day


def test_on_a_sick_day_the_student_may_ease_off_and_works_no_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = make_world(tmp_path, sick={MONDAY})
    script = Script({"review": None})
    monkeypatch.setattr(world, "do", script)
    monkeypatch.setattr(world, "replan", lambda: None)
    world.live_day(MONDAY)
    assert script.said("pace") == [{"name": "Easy", "for_days": 2}]
    assert script.said("now") == [] and script.said("close_day") == []  # the first day: nothing to close
    assert world.metrics.days == 1


def test_work_still_going_at_bedtime_is_stopped_and_counted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    world = make_world(tmp_path)
    item = add(world)
    script = Script({"item": {"item": {"remaining_min": 30, "duration_min": 60}}, "review": None})
    monkeypatch.setattr(world, "do", script)
    monkeypatch.setattr(world, "replan", lambda: None)
    world.true_left[item] = 120
    world.working = Working(item, until=10**12, minutes=45)
    world.live_day(MONDAY + timedelta(days=1))
    assert script.said("close_day") == [{"date": "2026-08-31"}] and script.said("materialize") == [{}]
    assert script.said("stop") == [{}] and world.working is None
    assert world.metrics.lived_minutes == 45 and world.true_left[item] == 75


def test_with_a_taste_the_student_answers_questions_before_the_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = make_world(tmp_path, sick={MONDAY})
    world.taste = Taste(Dice(), "consistent", {})
    asked: list[date] = []
    monkeypatch.setattr(world, "answer_questions", asked.append)
    monkeypatch.setattr(world, "replan", lambda: None)
    monkeypatch.setattr(world, "do", Script({"review": None}))
    world.live_day(MONDAY)
    assert asked == [MONDAY]


# Starting and finishing work


def test_work_past_its_estimate_goes_on_for_up_to_an_hour(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    item = add(world, minutes=60)
    world.true_left[item] = 150  # really two and a half hours
    world.begin(item, 60, None)
    assert world.working is not None and world.working.minutes == 120


def test_work_that_is_really_shorter_ends_when_it_is_done(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    item = add(world, minutes=60)
    world.true_left[item] = 30
    world.begin(item, 60, None)
    assert world.working is not None and world.working.minutes == 30


def test_work_already_done_is_not_started(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    item = add(world)
    world.do("done", id=item)
    world.begin(item, 60, None)
    assert world.working is None and item not in world.true_left


def test_when_friday_thinks_work_is_finished_but_it_isnt_the_student_adds_the_rest(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    item = add(world, minutes=60)
    world.at("2026-08-31T09:00")
    world.true_left[item] = 100
    world.begin(item, 60, None)
    world.now += 60
    world.finish(Working(item, world.now, 60))  # an hour worked, as Friday planned
    detail = world.do("item", id=item)["item"]
    assert detail["status"] == "todo" and detail["duration_min"] == 60 + 45  # 40 minutes left, in quarter hours


def test_work_really_finished_is_marked_done(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    item = add(world, minutes=60)
    world.at("2026-08-31T09:00")
    world.true_left[item] = 45
    world.begin(item, 60, None)
    world.now += 45
    assert world.working is not None
    world.finish(world.working)
    assert world.do("item", id=item)["item"]["status"] == "done"


def test_finishing_work_that_has_gone_stops_the_timer_and_nothing_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = make_world(tmp_path)
    script = Script({})
    monkeypatch.setattr(world, "do", script)
    world.true_left[7] = 10
    world.finish(Working(7, 0, 30))
    assert [c for c, _ in script.calls] == ["stop", "item"] and world.metrics.lived_minutes == 30


# Questions, approvals and the review


def comparison(world: World, a: dict[str, float], b: dict[str, float]) -> int:
    cur = world.conn.execute(
        "INSERT INTO comparisons (asked_utc, plan_a, plan_b, features_a, features_b, source, dials) "
        "VALUES ('2026-08-31T03:00Z', '{}', '{}', ?, ?, 'question', '{}')",
        [json.dumps({"rules": a}), json.dumps({"rules": b})],
    )
    return int(cur.lastrowid or 0)


def test_questions_are_answered_by_true_taste_and_the_weights_in_use_are_scored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = make_world(tmp_path, user=SimUser(Dice(roll=0.9)))
    world.taste = Taste(Dice(roll=0.99), "moody", {"late_night": 4.0, "daily_load": 1.0})
    cheap_late = comparison(world, {"late_night": 1.0, "daily_load": 0.0}, {"late_night": 0.0, "daily_load": 2.0})
    script = Script(
        {
            "questions": {
                "comparisons": [{"id": cheap_late}],
                "proposal": {"name": "fri_sat:late:any"},
                "checkin": True,
            },
            "learning": {"multipliers": {"late_night": 1.0}},  # Friday still thinks late is cheap
        }
    )
    monkeypatch.setattr(world_module, "prepare_questions", lambda conn, now: None)
    monkeypatch.setattr(world, "do", script)
    world.answer_questions(MONDAY)
    assert world.taste.mood == "motivated"  # a Monday: a moody student's mood moves
    # truth: a costs 4, b costs 2, so b is better; the weights in use say a (1 < 2): called wrong
    assert world.metrics.predicted == [False]
    assert script.said("compare_answer") == [{"id": cheap_late, "answer": "b"}]
    assert script.said("proposal_answer") == [{"kind": "rule", "name": "fri_sat:late:any", "yes": False}]
    assert world.metrics.accepted == [] and script.said("checkin") == [{"state": "motivated"}]


def test_only_a_student_missing_that_rule_takes_the_proposal_and_checks_in_honestly_most_days(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = make_world(tmp_path, user=SimUser(Dice(roll=0.1)))
    world.taste = Taste(Dice(), "missing", {}, mood="tired")
    script = Script({"questions": {"comparisons": [], "proposal": {"name": MISSING}, "checkin": True}})
    monkeypatch.setattr(world_module, "prepare_questions", lambda conn, now: None)
    monkeypatch.setattr(world, "do", script)
    world.answer_questions(MONDAY + timedelta(days=1))
    assert script.said("proposal_answer") == [{"kind": "rule", "name": MISSING, "yes": True}]
    assert world.metrics.accepted == [MISSING] and script.said("checkin") == [{"state": "tired"}]


def test_with_no_questions_waiting_nothing_is_answered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    world = make_world(tmp_path)
    world.taste = Taste(Dice(), "consistent", {})
    script = Script({})
    monkeypatch.setattr(world_module, "prepare_questions", lambda conn, now: None)
    monkeypatch.setattr(world, "do", script)
    world.answer_questions(MONDAY)
    assert [c for c, _ in script.calls] == ["questions", "learning"]


def test_the_weeks_suggestion_is_approved_when_there_is_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    world = make_world(tmp_path)
    script = Script({"learning": {"suggested": {"version": 4}}})
    monkeypatch.setattr(world, "do", script)
    world.approve()
    assert script.said("learn_apply") == [{"version": 4}]
    script.answers = {"learning": {"suggested": None}}
    world.approve()
    assert len(script.said("learn_apply")) == 1


def test_the_review_answers_each_block_as_it_went_and_on_sunday_approves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = make_world(tmp_path, user=SimUser(Dice(roll=0.9)))
    world.taste = Taste(Dice(), "consistent", {})
    world.lived = {(1, "2026-09-06T09:00")}
    blocks = [
        {"item_id": 1, "start": "2026-09-06T09:00", "end": "2026-09-06T10:00", "key": "k1"},
        {"item_id": 2, "start": "2026-09-06T11:00", "end": "2026-09-06T11:45", "key": "k2"},
    ]
    script = Script({"review": {"blocks": blocks, "finished": [{"id": 3}]}, "learning": {"suggested": {"version": 2}}})
    monkeypatch.setattr(world, "do", script)
    sunday = MONDAY + timedelta(days=6)
    world.review(sunday)
    entries = script.said("review_submit")[0]["entries"]
    assert [e["status"] for e in entries] == ["done", "not_done"] and world.metrics.missed_minutes == 45
    assert script.said("done") == [{"id": 3}] and script.said("learn_apply") == [{"version": 2}]


def test_a_review_that_cannot_be_read_is_left(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    world = make_world(tmp_path)
    script = Script({"review": None})
    monkeypatch.setattr(world, "do", script)
    world.review(MONDAY)
    assert [c for c, _ in script.calls] == ["review"]


# The end of the term


def test_hard_deadlines_count_work_finished_late_and_work_never_finished(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    world.at("2026-08-31T08:00")
    on_time, late, _never = (add(world, t, due="2026-08-31T12:00") for t in ("on time", "late", "never"))
    add(world, "later", due="2026-09-30T12:00")  # due after the end: not counted
    world.at("2026-08-31T11:00")
    world.do("done", id=on_time)
    world.at("2026-08-31T14:00")
    world.do("done", id=late)
    world.at("2026-08-31T18:00")
    world.deadlines()
    assert world.metrics.hard_due == 3 and world.metrics.hard_missed == 2
    assert world.metrics.late_hours == pytest.approx(2 + 6)  # finished two hours late; six hours and counting


def test_recovery_is_the_cosine_of_the_learned_weights_with_the_true_ones() -> None:
    taste = Taste(Dice(), "consistent", {"a": 2.0, "b": 1.0})
    learned = SimpleNamespace(do=lambda command: {"multipliers": {"a": 2.0}})
    assert recovery(learned, taste) == pytest.approx(1.0)  # type: ignore[arg-type]
    unlearned = SimpleNamespace(do=lambda command: None)
    assert recovery(unlearned, taste) == pytest.approx(3 / (2**0.5 * 5**0.5))  # type: ignore[arg-type]
    assert recovery(learned, Taste(Dice(), "consistent", {})) == 0.0  # type: ignore[arg-type]


def test_a_term_with_a_taste_tells_each_day_and_measures_recovery_at_the_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lived: list[date] = []
    monkeypatch.setattr(World, "live_day", lambda self, day: lived.append(day))
    heard: list[int] = []
    hear = lambda n, m: heard.append(n)  # noqa: E731
    metrics = run_term(tmp_path, TermConfig(weeks=1), seed=0, days=2, on_day=hear, family="noisy")
    assert lived == [date(2026, 8, 31), date(2026, 9, 1)] and heard == [1, 2]
    assert metrics.recovery is not None and 0 < metrics.recovery <= 1 and metrics.hard_due == 0


# The student


def test_a_review_answer_slips_one_step_now_and_then() -> None:
    honest, slipping = SimUser(Dice(roll=0.5)), SimUser(Dice(roll=0.0))
    assert [honest.answer(s) for s in ("done", "partial", "not_done")] == ["done", "partial", "not_done"]
    assert [slipping.answer(s) for s in ("done", "partial", "not_done")] == ["partial", "done", "partial"]


def test_late_starts_come_in_quarter_hours_and_work_never_takes_less_than_one() -> None:
    assert SimUser(Dice(delay=22)).delay() == 15 and SimUser(Dice(delay=5)).delay() == 0
    assert SimUser(Dice()).work_minutes(5, None) == 15
    assert SimUser(Dice(), {"C1": 2.0}).work_minutes(60, "C1") == 120


def test_a_tastes_weights_are_the_same_for_the_same_seed() -> None:
    a, b = Taste.make(3, "noisy", ("x", "y")), Taste.make(3, "noisy", ("x", "y"))
    assert a.theta == b.theta and set(a.theta) == {"x", "y"} and all(t > 0 for t in a.theta.values())


def test_only_a_moody_student_feels_their_mood() -> None:
    theta = {"late_night": 1.0, "open_value": 1.0, "weekends": 1.0}
    moody = Taste(Dice(), "moody", theta, mood="tired")
    assert moody.true_theta() == {r: MOOD_EFFECT["tired"].get(r, 1.0) for r in theta}
    assert Taste(Dice(), "consistent", theta, mood="tired").true_theta() == theta
    moody.step_mood()
    steady = Taste(Dice(), "consistent", theta)
    steady.step_mood()
    assert moody.mood == "motivated" and steady.mood == "normal"


def test_a_student_missing_a_rule_feels_its_cost_others_dont() -> None:
    features = {"rules": {"late_night": 1.0}, "templates": {MISSING: 2.0}}
    assert Taste(Dice(), "missing", {"late_night": 2.0}).energy(features) == 2.0 + 6.0
    assert Taste(Dice(), "consistent", {"late_night": 2.0}).energy(features) == 2.0


def test_comparisons_follow_true_energy_noisy_ones_less_sharply_and_adversarial_ones_flip() -> None:
    cheap, dear = {"rules": {"late_night": 0.0}}, {"rules": {"late_night": 1.0}}
    theta = {"late_night": 1.0}
    # P(a) is 1 / (1 + e^gap): near 1 for the cheaper plan as a, near 0 for the dearer
    assert Taste(Dice(roll=0.5), "consistent", theta).prefers_a(cheap, dear)
    assert not Taste(Dice(roll=0.5), "consistent", theta).prefers_a(dear, cheap)
    # a noisy student's gap is six times smaller: a roll a sharp student would answer is closer to a coin
    sharp_p = 1 / (1 + np.exp(1 / 0.05))
    noisy_p = 1 / (1 + np.exp(1 / 0.3))
    assert not Taste(Dice(roll=(sharp_p + noisy_p) / 2), "consistent", theta).prefers_a(dear, cheap)
    assert Taste(Dice(roll=(sharp_p + noisy_p) / 2), "noisy", theta).prefers_a(dear, cheap)
    assert not Taste(Dice(roll=0.1), "adversarial", theta).prefers_a(cheap, dear)  # flipped on purpose
