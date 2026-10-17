"""EDF must agree with exhaustive search on small instances (reference 12.2)."""
from functools import lru_cache

from hypothesis import given, settings, strategies as st

from fr.core.edf import Job, edf, latest_starts, merge, subtract


def brute_min_lmax(jobs: list[Job], free: list[tuple[int, int]]) -> int:
    """Exhaustive DP over unit minutes: minimal maximum lateness over every possible schedule."""
    units = sorted({t for lo, hi in merge(free) for t in range(lo, hi)})
    n = len(jobs)
    end_of_free = (units[-1] + 1) if units else 0

    @lru_cache(maxsize=None)
    def best(i: int, rem: tuple[int, ...]) -> int:
        if all(r == 0 for r in rem):
            return -10**9
        if i == len(units):
            return max(max(end_of_free, jobs[j].due) + rem[j] - jobs[j].due for j in range(n) if rem[j] > 0)
        t = units[i]
        out = best(i + 1, rem)  # idle
        for j in range(n):
            if rem[j] > 0 and jobs[j].release <= t:
                r2 = list(rem)
                r2[j] -= 1
                fin = (t + 1 - jobs[j].due) if r2[j] == 0 else -10**9
                out = min(out, max(fin, best(i + 1, tuple(r2))))
        return out

    return best(0, tuple(j.minutes for j in jobs))


jobs_st = st.lists(
    st.tuples(st.integers(0, 6), st.integers(1, 4), st.integers(1, 14)), min_size=1, max_size=4
)
free_st = st.lists(st.tuples(st.integers(0, 12), st.integers(1, 5)), min_size=1, max_size=3)


def mk(jobs_raw, free_raw):
    jobs = [Job(f"j{i}", r, due, m, 3, i) for i, (r, m, due) in enumerate(jobs_raw)]
    free = merge([(lo, lo + ln) for lo, ln in free_raw])
    return jobs, free


@settings(max_examples=300, deadline=None)
@given(jobs_st, free_st)
def test_edf_feasibility_is_exact_and_lmax_is_exact_when_feasible(jobs_raw, free_raw):
    """When jobs cannot all finish, "finish" of an unfinished job is a convention, so only the sign of
    L_max is exact there. When everything fits, L_max equals the exhaustive optimum."""
    jobs, free = mk(jobs_raw, free_raw)
    got, best = edf(jobs, free).l_max, brute_min_lmax(jobs, free)
    assert (got <= 0) == (best <= 0)
    if best <= 0:
        assert got == best


@settings(max_examples=300, deadline=None)
@given(jobs_st, free_st)
def test_slack_is_nonnegative_iff_edf_is_feasible(jobs_raw, free_raw):
    jobs, free = mk(jobs_raw, free_raw)
    feasible = edf(jobs, free).feasible
    late = latest_starts(jobs, free)
    all_ok = all(late[j.key] >= j.release for j in jobs)
    assert feasible == all_ok


@settings(max_examples=200, deadline=None)
@given(jobs_st, free_st)
def test_latest_start_is_achievable(jobs_raw, free_raw):
    """If feasible, delaying every job to its latest start still meets every deadline."""
    jobs, free = mk(jobs_raw, free_raw)
    if not edf(jobs, free).feasible:
        return
    late = latest_starts(jobs, free)
    delayed = [Job(j.key, max(j.release, late[j.key]), j.due, j.minutes, j.importance, j.order) for j in jobs]
    assert edf(delayed, free).feasible


def test_subtract_and_merge():
    assert merge([(5, 8), (0, 3), (2, 4)]) == [(0, 4), (5, 8)]
    assert subtract([(0, 10)], [(2, 4), (3, 6)]) == [(0, 2), (6, 10)]
