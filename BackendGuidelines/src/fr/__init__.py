"""Friday v3 engine research."""
# OR-Tools and highspy (pulled in by cvxpy) ship different HiGHS builds; OR-Tools must be loaded first or its
# extension resolves HiGHS symbols against the wrong library and fails to import.
from ortools.sat.python import cp_model as _cp_model  # noqa: F401
