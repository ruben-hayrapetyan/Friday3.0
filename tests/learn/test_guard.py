"""How far learning may move what you said (learn/guard.py): rules you wrote, and those your answers and settings set,
stay within half and double of what you set until you decide; kept as written they're weighed as set; let go, as
learned. Other rules learn freely."""

from types import SimpleNamespace

from friday.learn.guard import BAND, guarded, outside

RULES = [
    SimpleNamespace(name="you:keep-fri-sat-lighter", type="reserve", enabled=True),
    SimpleNamespace(name="you:lunch-and-dinner", type="elastic_shortfall", enabled=True),
    SimpleNamespace(name="late_night", type="late_night", enabled=True),  # your bedtime and winding down
    SimpleNamespace(name="finish_early", type="finish_early", enabled=True),  # your setup answer
    SimpleNamespace(name="chunk_cost", type="chunk_cost", enabled=True),  # Friday's own
    SimpleNamespace(name="you:off", type="reserve", enabled=False),
]
THETA = {"you:keep-fri-sat-lighter": 0.033, "you:lunch-and-dinner": 5.0, "late_night": 0.033, "finish_early": 1.2,
         "chunk_cost": 0.033, "you:off": 0.033}  # fmt: skip


def test_what_you_said_stays_within_half_and_double() -> None:
    out = guarded(THETA, RULES)
    assert out["you:keep-fri-sat-lighter"] == BAND[0] and out["you:lunch-and-dinner"] == BAND[1]
    assert out["late_night"] == BAND[0] and out["finish_early"] == 1.2
    assert out["chunk_cost"] == 0.033  # Friday's own rule learns freely


def test_kept_as_written_is_weighed_as_set_and_let_go_as_learned() -> None:
    out = guarded(THETA, RULES, held=["you:keep-fri-sat-lighter"], freed=["late_night"])
    assert out["you:keep-fri-sat-lighter"] == 1.0 and out["late_night"] == 0.033


def test_what_learning_would_move_too_far_is_listed_to_ask_about() -> None:
    names = [r.name for r, _ in outside(THETA, RULES)]
    assert names == ["you:keep-fri-sat-lighter", "you:lunch-and-dinner", "late_night"]  # not Friday's own, not off
    assert [r.name for r, _ in outside(THETA, RULES, held=["late_night"], freed=["you:lunch-and-dinner"])] == [
        "you:keep-fri-sat-lighter"
    ]
