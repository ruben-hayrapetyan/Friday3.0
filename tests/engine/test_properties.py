"""Engine invariants on generated instances (DESIGN §24.3)."""

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from friday.engine.checker import check
from friday.engine.explain import block_costs, blocks_of
from friday.engine.scheduler import schedule
from tests.bench.generator import ADVERSARIAL, reference_instance
from tests.engine.configs import fast

FAMILIES = ["reference", *ADVERSARIAL]


def instance(family: str, seed: int, size: int):  # noqa: ANN201
    return reference_instance(size, seed) if family == "reference" else ADVERSARIAL[family](seed)


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.sampled_from(FAMILIES), st.integers(0, 10_000), st.sampled_from([10, 20, 40]))
def test_every_plan_is_valid_protected_items_stay_on_time_and_explanations_add_up(family: str, seed: int,
                                                                                    size: int) -> None:  # fmt: skip
    p = instance(family, seed, size).build()
    result = schedule(p, fast(steps=8_000, fallback=False))
    assert check(p, result.plan, result.protected) == []
    per_block, other = block_costs(p, result.plan, blocks_of(result.plan))
    for rule, total in result.evaluation.rule_totals.items():
        assert sum(b.get(rule, 0) for b in per_block) + other.get(rule, 0) == total
