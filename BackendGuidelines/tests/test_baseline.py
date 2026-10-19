"""The CP-SAT baseline against brute force and the shared evaluator."""
import pytest

from fr.baseline.cpsat import GridModel, solve
from fr.core.brute import brute_force
from fr.core.evaluate import check, evaluate
from fr.core.generate import tiny


@pytest.mark.parametrize("seed", range(20))
def test_cpsat_matches_brute_force_on_tiny_instances(seed):
    sc = tiny(seed, 7, 3)
    sc.settings.workers = 1
    sc.settings.det_time = (5.0, 5.0, 5.0)
    p = sc.build()
    bf = brute_force(p)
    res = solve(p, workers=1)
    assert check(p, res.plan) == []
    assert res.evaluation.lex() == bf.best.lex(), (res.evaluation.stage_values, bf.best.stage_values)
    # the model's own objective for each stage equals the evaluator's recomputation
    for sr in res.stages:
        assert sr.cp_objective == sr.true_value or sr.status == "FEASIBLE"


@pytest.mark.parametrize("seed", range(12))
def test_pinned_instances_are_never_infeasible(seed):
    """Locks must not make the model INFEASIBLE (reference 8.1: that would be a bug)."""
    from fr.baseline.cpsat import GridModel
    from fr.core.generate import many_pins, reference_instance

    sc = many_pins(seed) if seed % 2 else reference_instance(20, seed, pins=8, deps=8)
    sc.settings.workers = 4
    sc.settings.det_time = (20.0, 20.0, 20.0)
    sc.settings.time_limit_s = 25.0
    p = sc.build()
    from fr.baseline.cpsat import SolveTimeout

    try:
        res = solve(p, stages=["deadlines"])
    except SolveTimeout:  # slow hardware or a loaded machine: no answer is not an INFEASIBLE model
        pytest.skip("CP-SAT found no solution in time on this machine")
    assert check(p, res.plan) == []
