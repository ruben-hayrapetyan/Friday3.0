"""Learning on synthetic comparisons where the answer is known (ported from the research's `test_learning.py`,
Bradley–Terry parts, plus query choice and the gate)."""

import numpy as np

from friday.learn.preferences import Comparison, accuracy, answer_scale, bt_fit, design, fit
from friday.learn.proposals import TEMPLATES, cv_gain, propose
from friday.learn.queries import choose, committee, disagreement
from friday.learn.state import PACE_H, StateModel, Week, loadings

RULES = (
    "late_night",
    "deep_run",
    "weekday_evenings",
    "weekends",
    "daily_load",
    "even_load",
    "energy",
    "soft_late",
    "unscheduled",
    "chunk_cost",
    "spread",
    "cluster",
    "target_shortfall",
    "elastic_shortfall",
    "open_value",
)
D = len(RULES)


def as_dict(values: np.ndarray) -> dict[str, float]:
    return dict(zip(RULES, values, strict=True))


def comparisons(theta: np.ndarray, n: int, rng: np.random.Generator, extra_w: float = 0.0, noise: float = 0.0,
                h: np.ndarray | None = None) -> tuple[list[Comparison], list[tuple[float, float]]]:  # fmt: skip
    """Random plan features; the user prefers lower true energy (plus a feature no rule has)."""
    out, extra = [], []
    true = theta if h is None else theta * np.exp(h @ loadings(RULES))
    for _ in range(n):
        a, b = rng.random(D) * 10, rng.random(D) * 10
        xa, xb = rng.random() * 5, rng.random() * 5
        a_wins = true @ a + extra_w * xa < true @ b + extra_w * xb
        if noise and rng.random() < noise:
            a_wins = not a_wins
        win, lose = (a, b) if a_wins else (b, a)
        out.append(Comparison(as_dict(win), as_dict(lose)))
        extra.append((xa, xb) if a_wins else (xb, xa))
    return out, extra


def test_the_fit_recovers_the_direction_of_the_true_weights() -> None:
    rng = np.random.default_rng(1)
    truth = np.exp(rng.normal(0, 0.5, D))
    found, _ = comparisons(truth, 400, rng)
    x, _ = design(found, RULES)
    theta = bt_fit(x, np.ones(D), np.full(D, 10.0), np.full(D, 0.02))
    assert theta @ truth / np.linalg.norm(theta) / np.linalg.norm(truth) > 0.9


def test_learning_predicts_held_out_answers_better_than_the_hand_set_weights() -> None:
    rng = np.random.default_rng(4)
    truth = np.exp(rng.normal(0, 0.6, D))
    seen, held = comparisons(truth, 60, rng)[0], comparisons(truth, 200, rng)[0]
    learned = fit(seen, RULES)
    assert accuracy(held, RULES, learned) > accuracy(held, RULES, dict.fromkeys(RULES, 1.0)) + 0.03


def test_answer_noise_is_higher_for_a_noisy_user() -> None:
    rng = np.random.default_rng(5)
    truth = np.ones(D)
    calm, noisy = comparisons(truth, 60, rng)[0], comparisons(truth, 60, rng, noise=0.3)[0]
    x_calm, _ = design(calm, RULES)
    x_noisy, _ = design(noisy, RULES)
    assert answer_scale(x_noisy, np.ones(D)) > answer_scale(x_calm, np.ones(D))


def test_a_planted_missing_feature_gains_and_a_fake_one_does_not() -> None:
    rng = np.random.default_rng(2)
    truth = np.ones(D)

    def gain(extra_w: float) -> float:
        found, extra = comparisons(truth, 150, rng, extra_w=extra_w)
        lib, _ = design(found, RULES)
        size = np.array([sum(abs(c.winner[r] - c.loser[r]) for r in RULES) for c in found])
        ext = np.array([[w - lo] for w, lo in extra]) / size[:, None]
        return float(cv_gain(lib, ext)[0])

    assert gain(3.0) > 0.05 > gain(0.0)


def test_nothing_is_proposed_from_too_few_comparisons_or_a_refused_template() -> None:
    rng = np.random.default_rng(6)
    found, _ = comparisons(np.ones(D), 5, rng)
    assert propose(found, [({}, {})] * 5, RULES, set(), 0.1) == (None, 0.0)
    refused = {t.name for t in TEMPLATES}
    found, _ = comparisons(np.ones(D), 20, rng)
    assert propose(found, [({}, {})] * 20, RULES, refused, 0.1) == (None, 0.0)


def test_before_ten_answers_the_pair_nearest_a_draw_is_asked() -> None:
    rng = np.random.default_rng(9)
    obvious = (as_dict(np.zeros(D)), as_dict(np.full(D, 10.0)))
    near = (as_dict(np.full(D, 5.0)), as_dict(np.full(D, 5.0) + rng.normal(0, 0.1, D)))
    assert committee([], RULES) == []
    assert choose([obvious, near], [], RULES) == 1


def test_the_committee_asks_what_it_disagrees_on_and_stops_when_it_agrees() -> None:
    rng = np.random.default_rng(7)
    seen, _ = comparisons(np.ones(D), 40, rng)
    members = committee(seen, RULES)
    obvious = (as_dict(np.zeros(D)), as_dict(np.full(D, 10.0)))  # A costs nothing anywhere
    assert disagreement(members, *obvious, RULES) == 0.0
    assert choose([obvious], seen, RULES) is None
    split = max(range(50), key=lambda k: disagreement(members, *pairs_k(k), RULES))
    assert disagreement(members, *pairs_k(split), RULES) > 0
    assert choose([obvious, pairs_k(split)], seen, RULES, stop_below=0.0) == 1


def pairs_k(k: int) -> tuple[dict[str, float], dict[str, float]]:
    rng = np.random.default_rng(100 + k)
    return as_dict(rng.random(D)), as_dict(rng.random(D))


def test_state_units_read_a_planted_tired_week() -> None:
    """One week in three is tired; with check-ins the units read most weeks right."""
    rng = np.random.default_rng(3)
    model = StateModel(RULES)
    moods = ["tired" if w % 3 == 1 else "normal" for w in range(9)]
    for mood in moods:
        found, _ = comparisons(np.ones(D), 40, rng, h=PACE_H[mood])
        x, weight = design(found, RULES)
        model.add(Week(x, weight, 0, 0, mood, None))
    reads = [model.mood(h) for h in model.h]
    assert np.mean([r == m for r, m in zip(reads, moods, strict=True)]) >= 0.65, reads


def test_the_gate_stays_shut_for_a_user_without_moods() -> None:
    rng = np.random.default_rng(8)
    model = StateModel(RULES)
    for _ in range(6):
        found, _ = comparisons(np.ones(D), 10, rng, noise=0.2)
        x, weight = design(found, RULES)
        week = Week(x, weight, 0, 0, None, None)
        model.score(week, model.predict_h(None, None), model.theta)
        model.add(week)
    assert not model.units_on(2.0)


def test_a_planted_missing_feature_is_proposed_as_a_rule_and_said_in_words() -> None:
    rng = np.random.default_rng(2)
    planted = next(t for t in TEMPLATES if t.name == "fri_sat:late:deep")
    found, extra = comparisons(np.ones(D), 150, rng, extra_w=3.0)
    extras = [({planted.name: w}, {planted.name: lo}) for w, lo in extra]
    best, gain = propose(found, extras, RULES, set(), 0.05)
    assert best == planted and gain > 0.05
    assert best.sentence() == "You seem to prefer no deep work on Friday and Saturday late evenings."
    assert best.rule() == {
        "type": "time_preference",
        "name": "learned:fri_sat:late:deep",
        "weight": 1.0,
        "params": {"start": "19:00", "end": "23:59", "price": 1.0, "days": ["fri", "sat"]},
        "scope": {"energy": "deep"},
    }


def test_a_template_for_any_day_and_any_work_has_no_days_or_scope() -> None:
    every = next(t for t in TEMPLATES if t.name == "all:night:any")
    assert every.rule()["params"] == {"start": "21:00", "end": "23:59", "price": 1.0} and "scope" not in every.rule()
    assert every.sentence() == "You seem to prefer no work on any day nights."


def test_no_gain_above_the_bar_proposes_nothing_but_says_the_best_gain() -> None:
    rng = np.random.default_rng(6)
    found, _ = comparisons(np.ones(D), 30, rng)
    best, gain = propose(found, [({}, {})] * 30, RULES, set(), 10.0)
    assert best is None and gain < 10.0


def test_with_nothing_answered_the_hand_set_weights_stand() -> None:
    assert fit([], RULES) == dict.fromkeys(RULES, 1.0)
    assert fit(comparisons(np.ones(D), 3, np.random.default_rng(0))[0], ()) == {}
    assert accuracy([], RULES, dict.fromkeys(RULES, 1.0)) == 0.0


def test_under_twelve_answers_the_answer_noise_is_the_default() -> None:
    found, _ = comparisons(np.ones(D), 11, np.random.default_rng(0), noise=0.5)
    x, _ = design(found, RULES)
    assert answer_scale(x, np.ones(D)) == 0.05


def test_a_picked_pace_is_the_weeks_state_and_a_check_in_moves_it() -> None:
    model = StateModel(RULES)
    tired = model.predict_h(None, "tired")
    assert np.array_equal(tired, PACE_H["tired"]) and tired is not PACE_H["tired"]
    assert np.array_equal(model.predict_h(None, None), np.zeros(4))
    said_tired = model.predict_h("tired", None)
    assert model.mood(said_tired) == "tired"


def test_skipped_blocks_count_in_a_weeks_likelihood() -> None:
    model = StateModel(RULES)
    empty = np.zeros((0, D))
    none_skipped = Week(empty, np.zeros(0), 0, 10, None, None)
    most_skipped = Week(empty, np.zeros(0), 9, 10, None, None)
    rested = np.zeros(4)
    assert model.week_ll(model.theta, rested, none_skipped) > model.week_ll(model.theta, rested, most_skipped)
    assert model.week_ll(model.theta, rested, Week(empty, np.zeros(0), 0, 0, None, None)) == 0.0


def test_a_week_without_comparisons_leaves_the_gate_tally_alone() -> None:
    model = StateModel(RULES)
    model.score(Week(np.zeros((0, D)), np.zeros(0), 2, 5, "tired", None), np.zeros(4), model.theta)
    assert model.ll_units == 0.0 and set(model.ll_taste.values()) == {0.0}
