"""The executor: EDF agrees with exhaustive search, slack matches feasibility, safe swaps stay safe (DESIGN §14)."""

from functools import cache

from hypothesis import given, settings
from hypothesis import strategies as st

from friday.engine.checker import check
from friday.engine.executor import (
    ExecutorInput,
    Job,
    NowSettings,
    edf,
    is_safe,
    latest_starts,
    merge,
    now,
    provisional_plan,
    slack,
    subtract,
)
from friday.planner.build import Pin
from friday.planner.inputs import executor_input
from tests.bench.generator import Scenario, bench_settings, reference_rules
from tests.engine.helpers import at, item


def brute_min_lmax(jobs: list[Job], free: list[tuple[int, int]]) -> int:
    """Exhaustive search over unit minutes: the least maximum lateness of any schedule."""
    units = sorted({t for lo, hi in merge(free) for t in range(lo, hi)})
    n = len(jobs)
    end_of_free = (units[-1] + 1) if units else 0

    @cache
    def best(i: int, rem: tuple[int, ...]) -> int:
        if all(r == 0 for r in rem):
            return -(10**9)
        if i == len(units):
            return max(max(end_of_free, jobs[j].due) + rem[j] - jobs[j].due for j in range(n) if rem[j] > 0)
        t = units[i]
        out = best(i + 1, rem)  # idle
        for j in range(n):
            if rem[j] > 0 and jobs[j].release <= t:
                after = list(rem)
                after[j] -= 1
                finish = (t + 1 - jobs[j].due) if after[j] == 0 else -(10**9)
                out = min(out, max(finish, best(i + 1, tuple(after))))
        return out

    return best(0, tuple(j.minutes for j in jobs))


jobs_st = st.lists(st.tuples(st.integers(0, 6), st.integers(1, 4), st.integers(1, 14)), min_size=1, max_size=6)
free_st = st.lists(st.tuples(st.integers(0, 12), st.integers(1, 5)), min_size=1, max_size=3)


def make(jobs_raw: list[tuple[int, int, int]], free_raw: list[tuple[int, int]]) -> tuple[list[Job], list]:
    jobs = [Job(f"j{i}", release, due, minutes, 3, i) for i, (release, minutes, due) in enumerate(jobs_raw)]
    return jobs, merge([(lo, lo + length) for lo, length in free_raw])


@settings(max_examples=300, deadline=None)
@given(jobs_st, free_st)
def test_edf_feasibility_is_exact_and_lmax_is_exact_when_feasible(jobs_raw, free_raw) -> None:  # noqa: ANN001
    """When jobs can't all finish, an unfinished job's "finish" is a convention, so only the sign of L_max is exact."""
    jobs, free = make(jobs_raw, free_raw)
    got, best = edf(jobs, free).l_max, brute_min_lmax(jobs, free)
    assert (got <= 0) == (best <= 0)
    if best <= 0:
        assert got == best


@settings(max_examples=300, deadline=None)
@given(jobs_st, free_st)
def test_slack_is_nonnegative_iff_edf_is_feasible(jobs_raw, free_raw) -> None:  # noqa: ANN001
    jobs, free = make(jobs_raw, free_raw)
    late = latest_starts(jobs, free)
    assert edf(jobs, free).feasible == all(late[j.key] >= j.release for j in jobs)


@settings(max_examples=200, deadline=None)
@given(jobs_st, free_st)
def test_every_job_can_wait_until_its_latest_start(jobs_raw, free_raw) -> None:  # noqa: ANN001
    jobs, free = make(jobs_raw, free_raw)
    if not edf(jobs, free).feasible:
        return
    late = latest_starts(jobs, free)
    delayed = [Job(j.key, max(j.release, late[j.key]), j.due, j.minutes, j.importance, j.order) for j in jobs]
    assert edf(delayed, free).feasible


def test_subtract_and_merge() -> None:
    assert merge([(5, 8), (0, 3), (2, 4)]) == [(0, 4), (5, 8)]
    assert subtract([(0, 10)], [(2, 4), (3, 6)]) == [(0, 2), (6, 10)]


@settings(max_examples=300, deadline=None)
@given(jobs_st, free_st, st.integers(0, 6), st.integers(1, 5))
def test_a_safe_swap_never_makes_feasible_deadlines_infeasible(jobs_raw, free_raw, who, run) -> None:  # noqa: ANN001
    """Whether the swap is one of the jobs or other work, if it is called safe the jobs still all fit after it."""
    jobs, free = make(jobs_raw, free_raw)
    inp = ExecutorInput(free[0][0], free, jobs)
    before = edf(jobs, free)
    key = jobs[who].key if who < len(jobs) else "other"
    if before.feasible and is_safe(inp, key, run, before):
        taken = subtract(free, [(inp.now, inp.now + run)])
        rest = [Job(j.key, j.release, j.due, j.minutes - run, j.importance, j.order) if j.key == key else j
                for j in jobs]  # fmt: skip
        assert edf([j for j in rest if j.minutes > 0], taken).feasible


def test_slack_counts_wall_time_and_free_time_to_the_latest_start() -> None:
    """Due at 100 with 20 minutes of work and a busy stretch 60–90: the latest start is 50 (50–60, then 90–100)."""
    inp = ExecutorInput(0, [(0, 60), (90, 200)], [Job("a", 0, 100, 20)])
    assert slack(inp)["a"].latest_start == 50
    assert slack(inp)["a"].minutes == 50 and slack(inp)["a"].free_minutes == 50


# now() and provisional placement on built problems: Monday from 09:00, two days, the bench's sleep times.

MON, TUE = 0, 1


def day(items: list, rules: tuple[str, ...] = ("late_work",), now_at: str = "09:00", **kw: object):  # noqa: ANN201
    sc = Scenario("t", list(items), at(MON, now_at), bench_settings(horizon_days=2, fine_days=2,
                                                                     rules=reference_rules(rules)), **kw)  # fmt: skip
    p = sc.build()
    return p, executor_input(sc.build_input(), p)


def slots_between(p, start: str, end: str) -> tuple[int, ...]:  # noqa: ANN001
    return tuple(p.grid.slots_in(at(MON, start), at(MON, end)))


def test_now_names_the_block_covering_now_and_the_next_one() -> None:
    p, inp = day([item("chore", 1), item("chore", 2)])
    plan = {"item:1": slots_between(p, "09:00", "09:30"), "item:2": slots_between(p, "10:00", "10:30")}
    shown = now(p, plan, inp, NowSettings())
    assert (shown.current, shown.current_source) == ("item:1", "block")
    assert shown.next is not None and shown.next.key == "item:2"
    assert all(w.key != "item:1" for w in shown.swaps)


def test_a_running_timer_is_current_even_off_plan() -> None:
    p, inp = day([item("chore", 1), item("chore", 2)])
    plan = {"item:1": slots_between(p, "09:00", "09:30"), "item:2": ()}
    assert now(p, plan, inp, NowSettings(), timer_key="item:2").current_source == "timer"


def test_free_time_offers_what_fits_before_the_next_block() -> None:
    long_chore = item("chore", 1, duration_units=8)  # one sitting, 2 h
    reading = item("reading", 2, duration_units=8, min_chunk_units=2)
    meal = item("chore", 3)
    p, inp = day([long_chore, reading, meal])
    shown = now(p, {"item:1": (), "item:2": (), "item:3": slots_between(p, "10:00", "10:30")}, inp, NowSettings())
    assert shown.current is None and shown.gap_minutes == 60
    assert [w.key for w in shown.fits] == ["item:3", "item:2"]  # the meal could start early; the 2 h chore can't


def test_work_that_would_make_a_deadline_late_is_never_offered() -> None:
    """Three hours of hard work due at noon and exactly three free hours: only that work is safe."""
    essay = item("assignment", 1, duration_units=12, due_utc=at(MON, "12:00"), min_chunk_units=1)
    p, inp = day([essay, item("chore", 2)])
    shown = now(p, {"item:1": (), "item:2": ()}, inp, NowSettings())
    assert [w.key for w in shown.swaps] == ["item:1"]
    assert [(a.key, a.kind) for a in shown.alerts] == [("item:1", "start_now")]


def test_alerts_say_soon_start_now_or_triage_by_slack() -> None:
    """Negative slack goes only to the job that can't make it; the others keep their real latest start."""
    soon = item("assignment", 1, duration_units=4, due_utc=at(TUE, "08:00"), min_chunk_units=1)  # by midnight
    tight = item("assignment", 2, duration_units=4, due_utc=at(MON, "11:00"), min_chunk_units=1)  # by 10:00
    hopeless = item("assignment", 3, duration_units=8, due_utc=at(MON, "10:00"), min_chunk_units=1)
    p, inp = day([soon, tight, hopeless])
    kinds = {a.key: a.kind for a in now(p, {}, inp, NowSettings()).alerts}
    assert kinds == {"item:1": "soon", "item:2": "start_now", "item:3": "triage"}


def test_provisional_placement_keeps_unchanged_blocks_and_places_new_work_by_deadline() -> None:
    kept = item("chore", 1)
    pinned = item("chore", 2)
    new = item("assignment", 3, duration_units=4, due_utc=at(MON, "12:00"), min_chunk_units=1)
    book = item("side_project", 4, title="book")
    p, _ = day([kept, pinned, new, book], pins=[Pin(2, at(MON, "15:00"), at(MON, "15:30"))])
    previous = {"item:1": slots_between(p, "09:00", "09:30"), "item:4": slots_between(p, "16:00", "17:00")}
    ghosts = provisional_plan(p, previous, changed={"item:3"})
    assert ghosts["item:1"] == previous["item:1"] and ghosts["item:4"] == previous["item:4"]
    assert ghosts["item:2"] == slots_between(p, "15:00", "15:30")
    assert ghosts["item:3"] == slots_between(p, "09:30", "10:30")
    assert check(p, ghosts) == []


def test_provisional_placement_never_adds_open_items() -> None:
    p, _ = day([item("side_project", 1, title="book")])
    assert provisional_plan(p, {}, changed=set())["item:1"] == ()
