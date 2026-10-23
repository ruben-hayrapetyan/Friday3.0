from numba import njit
from ortools.sat.python import cp_model


@njit(cache=True, nogil=True)
def sum_of_squares(n: int) -> int:
    total = 0
    for i in range(n):
        total += i * i
    return total


def test_numba_compiles_and_runs() -> None:
    assert sum_of_squares(4) == 14


def test_cp_sat_solves_a_small_model() -> None:
    model = cp_model.CpModel()
    x = model.new_int_var(0, 10, "x")
    y = model.new_int_var(0, 10, "y")
    model.add(x + y == 7)
    model.maximize(x - y)
    solver = cp_model.CpSolver()
    assert solver.solve(model) == cp_model.OPTIMAL
    assert (solver.value(x), solver.value(y)) == (7, 0)
