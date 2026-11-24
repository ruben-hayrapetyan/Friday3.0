"""A few random worlds in the ordinary suite (tests/stress/random_worlds.py; the big runs are on debian, TESTING.md):
each world's every plan has to pass every check, after every change."""

import pytest

from tests.stress.random_worlds import play


@pytest.mark.parametrize("seed", [101, 202])
def test_a_random_world_breaks_nothing(seed: int) -> None:
    outcome = play(seed, changes=6)
    assert outcome.steps == 6, outcome.issues
    assert outcome.issues == [], "\n".join(
        f"step {i['step']} after {i['after']!r}: {i['issue']}" for i in outcome.issues
    )
