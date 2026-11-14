"""The deadline fallback with a fixed effort (FRIDAY_FIXED_EFFORT, 13 Nov): CP-SAT stops after a number of seconds on
several threads, so a busy Mac gave the screen tests a different plan now and then (load 65 from other programs:
"2 things will be late" where one was). The screen tests' Friday sets it: one thread and a deterministic budget, so
the same problem plans the same however busy the machine is. Your Friday doesn't set it and plans as before.

Glass box: the solver's parameters either way. Black box: an overloaded week solved twice, once with the CPU kept
busy, gives the same plan."""

import threading
import time
from pathlib import Path

import pytest

from friday.engine import cpsat_deadlines
from friday.engine.cpsat_deadlines import DeadlineModel
from tests.bench.generator import overload

ROOT = Path(__file__).resolve().parents[2]


def solved_with(monkeypatch: pytest.MonkeyPatch, fixed: bool, seconds: float = 2.0, workers: int = 4) -> DeadlineModel:
    if fixed:
        monkeypatch.setenv("FRIDAY_FIXED_EFFORT", "1")
    else:
        monkeypatch.delenv("FRIDAY_FIXED_EFFORT", raising=False)
    model = DeadlineModel(overload(1).build())
    model.solve(None, seconds, workers, seed=7)
    return model


def test_fixed_effort_is_one_thread_and_a_deterministic_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    params = solved_with(monkeypatch, True).solver.parameters
    assert params.num_workers == 1 and params.max_deterministic_time == 2.0
    assert params.max_time_in_seconds >= 60  # only a backstop for a machine that's stuck


def test_without_it_the_fallback_plans_as_your_friday_does(monkeypatch: pytest.MonkeyPatch) -> None:
    params = solved_with(monkeypatch, False).solver.parameters
    assert params.num_workers == 4 and params.max_time_in_seconds == 2.0


def test_the_same_week_plans_the_same_with_the_cpu_kept_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRIDAY_FIXED_EFFORT", "1")
    calm = DeadlineModel(overload(3).build()).solve(None, 5.0, 4, seed=7)  # fallback_s, as Friday gives it
    stop = threading.Event()

    def spin() -> None:
        while not stop.is_set():
            sum(i * i for i in range(10_000))

    busy = [threading.Thread(target=spin, daemon=True) for _ in range(8)]
    for t in busy:
        t.start()
    try:
        time.sleep(0.05)
        loaded = DeadlineModel(overload(3).build()).solve(None, 5.0, 4, seed=7)  # fallback_s, as Friday gives it
    finally:
        stop.set()
    assert calm.plan is not None and loaded.plan == calm.plan and loaded.objective == calm.objective


def test_the_screen_tests_friday_sets_it_and_your_friday_doesnt() -> None:
    server = (ROOT / "web" / "src" / "test" / "server.ts").read_text()
    assert f'{cpsat_deadlines.FIXED_EFFORT.removeprefix("FRIDAY_")}: "1"' in server and 'CHAINS: "3"' in server
    for shipped in (ROOT / "Mac" / "Sources").glob("*.swift"):
        assert cpsat_deadlines.FIXED_EFFORT not in shipped.read_text(), shipped.name
