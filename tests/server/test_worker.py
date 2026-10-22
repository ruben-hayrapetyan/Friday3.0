"""The solver worker in a real spawned process: debounce, cancelling a stale solve, restart after a crash, and a
failing solve that keeps the current plan."""

import os
import signal
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from friday.planner.store import current_plan, generation
from friday.server.events import Hub
from friday.server.plugins import load_plugins
from friday.server.worker import Supervisor
from tests.commands.helpers import App, new_app

BOOM = """
from friday.engine.rules import Rule, rule_type


@rule_type("boom")
class Boom(Rule):
    def prepare(self, problem):
        raise RuntimeError("boom")
"""


class Recorder(Hub):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[tuple[str, Any]] = []

    def publish(self, event: str, data: Any = None) -> None:
        self.events.append((event, data))


def wait_for(condition: Callable[[], Any], timeout_s: float = 60) -> Any:
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        found = condition()
        if found:
            return found
        time.sleep(0.05)
    raise AssertionError("timed out")


@pytest.fixture
def app(tmp_path: Path) -> App:
    app = new_app(tmp_path, horizon_days=3)
    app.do("add", text="essay due tue 17:00 ~2h")
    return app


@pytest.fixture
def worker(app: App, tmp_path: Path) -> Iterator[Supervisor]:
    supervisor = Supervisor(tmp_path / "friday.db", Recorder(), lambda: app.now_utc, tmp_path / "rules")
    supervisor.start()
    yield supervisor
    supervisor.stop()


def plans(app: App) -> list[dict[str, Any]]:
    return app.table("plans")


def huge_budget(app: App) -> None:
    app.do("settings_set", key="engine", value={"chains": 2, "step_budgets": [
        {"max_items": 1000, "cold": 2_000_000_000, "warm": 2_000_000_000}]})  # fmt: skip


def test_a_request_is_solved_saved_and_announced(app: App, worker: Supervisor) -> None:
    worker.request(0)
    wait_for(lambda: plans(app))
    assert current_plan(app.conn, 1)["generation"] == generation(app.conn)
    assert wait_for(lambda: [e for e in worker.hub.events if e[0] == "plan.changed"])  # type: ignore[attr-defined]


def test_requests_inside_the_debounce_make_one_solve(app: App, worker: Supervisor) -> None:
    for _ in range(3):
        worker.request(0.5)
        time.sleep(0.1)
    wait_for(lambda: plans(app))
    time.sleep(1)
    assert len(plans(app)) == 1


def test_a_newer_request_cancels_the_running_solve(app: App, worker: Supervisor) -> None:
    huge_budget(app)
    worker.request(0)
    wait_for(lambda: worker.job)
    app.do("settings_set", key="engine", value={"chains": 2, "step_budgets": [
        {"max_items": 1000, "cold": 20_000, "warm": 20_000}]})  # fmt: skip
    began = time.monotonic()
    worker.request(0)
    wait_for(lambda: plans(app))
    assert time.monotonic() - began < 30
    assert [p["generation"] for p in plans(app)] == [generation(app.conn)]  # the stale solve was never saved


def test_replan_now_waits_for_the_plan(app: App, worker: Supervisor) -> None:
    plan_id = worker.solve_now("replan by you", generation(app.conn))
    assert plan_id == current_plan(app.conn, 1)["id"]


def test_a_crashed_worker_is_restarted_and_the_snapshot_retried(app: App, worker: Supervisor) -> None:
    worker.request(0)
    job = wait_for(lambda: worker.job)
    os.kill(worker.process.pid, signal.SIGKILL)
    wait_for(lambda: plans(app))
    assert job.retried and worker.process.is_alive()


def test_a_failing_solve_keeps_the_plan_raises_a_banner_and_saves_the_snapshot(
    app: App, worker: Supervisor, tmp_path: Path
) -> None:
    worker.request(0)
    wait_for(lambda: plans(app))
    (tmp_path / "rules").mkdir()
    (tmp_path / "rules" / "boom.py").write_text(BOOM)
    load_plugins(tmp_path / "rules")
    worker.stop()  # the child loads plugins as it starts
    restarted = Supervisor(tmp_path / "friday.db", Recorder(), lambda: app.now_utc, tmp_path / "rules")
    restarted.start()
    try:
        app.do("settings_set", key="rules", value=[{"type": "boom", "name": "boom"}])
        assert restarted.solve_now("replan", generation(app.conn)) is None
        assert len(plans(app)) == 1
        assert "Planning failed" in app.do("status")["problems"][0]
        assert list((tmp_path / "snapshots").glob("*.pickle"))
    finally:
        restarted.stop()
