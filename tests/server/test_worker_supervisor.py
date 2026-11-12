"""The worker's supervisor step by step, in this process (server/worker.py): the child's loop fed by hand, and the
supervisor's answers to a database not set up, a failing step, a plan made stale while it solved, and a child that
died once, twice, or with nothing in hand. The spawned process itself is in test_worker.py."""

import multiprocessing as mp
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from friday.core.db import connect
from friday.planner.service import plan_snapshot
from friday.planner.snapshot import take_snapshot
from friday.planner.store import current_plan, kv_get
from friday.server.worker import Job, Supervisor, Waiter, child, set_problem
from tests.commands.helpers import App, new_app


class Pipe:
    """One end of the child's pipe: what it will be sent, and what it said."""

    def __init__(self, *coming: Any) -> None:
        self.coming, self.said = list(coming), []

    def recv(self) -> Any:
        return self.coming.pop(0)

    def send(self, message: Any) -> None:
        self.said.append(message)

    def poll(self, timeout: float) -> bool:
        return bool(self.coming)


class Process:
    exitcode = -9

    def is_alive(self) -> bool:
        return False


class Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, Any]] = []

    def publish(self, event: str, data: Any = None) -> None:
        self.events.append((event, data))


@pytest.fixture
def app(tmp_path: Path) -> App:
    app = new_app(tmp_path, horizon_days=3)
    app.do("add", text="essay due tue 17:00 ~2h")
    return app


def supervisor(app: App, tmp_path: Path) -> Supervisor:
    """A supervisor whose child is a stand-in: spawning makes a fresh pipe, counted, and starts nothing."""
    made = Supervisor(tmp_path / "friday.db", Recorder(), lambda: app.now_utc, tmp_path / "rules")  # type: ignore[arg-type]
    made.spawned = 0  # type: ignore[attr-defined]

    def spawn() -> None:
        made.spawned += 1  # type: ignore[attr-defined]
        made.pipe, made.process = Pipe(), Process()  # type: ignore[assignment]

    made.spawn = spawn  # type: ignore[method-assign]
    spawn()
    return made


def never_cancelled() -> Any:
    return np.zeros(1, dtype=np.int64)


def problems(app: App) -> dict[str, str]:
    return kv_get(app.conn, "server_problems", {}, 1)


def test_the_child_solves_each_snapshot_its_sent_and_stops_when_told(app: App, tmp_path: Path) -> None:
    snapshot = take_snapshot(app.conn, app.now_utc, 1)
    pipe = Pipe((snapshot, False), ("not a snapshot", False), None)
    child(pipe, mp.get_context("spawn").RawArray("q", 1), tmp_path / "rules")  # type: ignore[arg-type]
    (kind, plan), (failed, trace) = pipe.said
    assert kind == "plan" and {b.item_id for b in plan.blocks} == {1}
    assert failed == "error" and "Traceback" in trace


def test_nothing_is_solved_until_friday_is_set_up(tmp_path: Path) -> None:
    conn = connect(tmp_path / "friday.db")
    made = Supervisor(tmp_path / "friday.db", Recorder(), lambda: 0, tmp_path)  # type: ignore[arg-type]
    made.pipe = Pipe()  # type: ignore[assignment]
    waiting = Waiter(0)
    made.waiters.append(waiting)
    made.request(0)
    made.maybe_start(conn)
    assert made.job is None and made.pipe.said == []  # type: ignore[attr-defined]
    assert waiting.done.is_set() and waiting.plan_id is None


def test_a_failing_step_answers_the_waiters_and_raises_a_banner(app: App, tmp_path: Path) -> None:
    made = supervisor(app, tmp_path)
    waiting = Waiter(10**6)
    made.waiters.append(waiting)

    def step(conn: Any) -> None:
        made.stopping.set()  # one turn of the loop
        raise RuntimeError("a bad snapshot")

    made.step = step  # type: ignore[method-assign]
    made.loop()
    assert waiting.done.is_set() and waiting.plan_id is None
    assert problems(app)["worker"] == "the planner failed; see the server log"
    assert ("status.changed", None) in made.hub.events  # type: ignore[attr-defined]


def test_a_plan_made_stale_while_it_solved_answers_with_the_newer_one(app: App, tmp_path: Path) -> None:
    made = supervisor(app, tmp_path)
    older = take_snapshot(app.conn, app.now_utc, 1)
    app.do("add", text="laundry ~1h")
    newer = take_snapshot(app.conn, app.now_utc, 1)
    stop = never_cancelled()
    made.job = Job(newer, False, "commands")
    made.finished(app.conn, "plan", plan_snapshot(newer, False, stop))
    saved = current_plan(app.conn, 1)
    waiting = Waiter(older.generation)
    made.waiters.append(waiting)
    made.job = Job(older, False, "commands")
    made.finished(app.conn, "plan", plan_snapshot(older, False, stop))
    assert current_plan(app.conn, 1)["id"] == saved["id"]  # the older solve wasn't kept
    assert waiting.plan_id == saved["id"]
    assert made.hub.events[-1] == ("plan.changed", {"plan_id": saved["id"], "generation": older.generation})  # type: ignore[attr-defined]


def test_a_plan_clears_the_workers_banner(app: App, tmp_path: Path) -> None:
    made = supervisor(app, tmp_path)
    set_problem(app.conn, 1, "worker", "the planner failed; see the server log")
    snapshot = take_snapshot(app.conn, app.now_utc, 1)
    stop = never_cancelled()
    made.job = Job(snapshot, True, "commands")
    made.finished(app.conn, "plan", plan_snapshot(snapshot, True, stop))
    assert "worker" not in problems(app)
    assert ("status.changed", None) in made.hub.events  # type: ignore[attr-defined]


def test_a_child_that_died_with_nothing_in_hand_or_a_cancelled_solve_is_only_restarted(
    app: App, tmp_path: Path
) -> None:
    made = supervisor(app, tmp_path)
    made.crashed(app.conn)
    snapshot = take_snapshot(app.conn, app.now_utc, 1)
    made.job = Job(snapshot, True, "commands", cancelled=True)
    made.crashed(app.conn)
    assert made.spawned == 3 and made.pipe.said == [] and made.job is None  # type: ignore[attr-defined]


def test_a_child_that_dies_twice_on_one_snapshot_gives_up_and_saves_it(app: App, tmp_path: Path) -> None:
    made = supervisor(app, tmp_path)
    snapshot = take_snapshot(app.conn, app.now_utc, 1)
    waiting = Waiter(snapshot.generation)
    made.waiters.append(waiting)
    made.job = Job(snapshot, True, "commands")
    made.crashed(app.conn)
    assert made.job.retried and made.pipe.said == [(snapshot, True)]  # type: ignore[attr-defined]
    made.crashed(app.conn)
    assert waiting.done.is_set() and waiting.plan_id is None
    assert problems(app)["worker"].startswith("Friday couldn't make a new plan, so the last one stays.")
    saved = tmp_path / "snapshots" / f"generation-{snapshot.generation}.pickle"
    assert pickle.loads(saved.read_bytes()).generation == snapshot.generation


def test_a_stopping_supervisor_doesnt_restart_the_child(app: App, tmp_path: Path) -> None:
    made = supervisor(app, tmp_path)
    made.stopping.set()
    made.crashed(app.conn)
    assert made.spawned == 1  # type: ignore[attr-defined]
