"""The solver worker (DESIGN §15.5).

One spawned child process solves snapshots, one at a time; its chains run as threads inside it. A supervisor thread
in the API process debounces replan requests, takes the snapshot, cancels a solve that a newer request has made
stale, saves each finished plan and publishes `plan.changed`. A crashed child is restarted and its snapshot retried
once; a solve that raises (a failed check is a kernel bug) keeps the current plan, raises a banner and saves the
snapshot for replay.
"""

import contextlib
import json
import logging
import multiprocessing as mp
import os
import pickle
import sqlite3
import sys
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from multiprocessing.connection import Connection
from pathlib import Path

import numpy as np

from friday.core.db import connect
from friday.notify.webhooks import fire
from friday.planner.service import plan_snapshot, save_plan
from friday.planner.snapshot import Snapshot, take_snapshot
from friday.planner.store import current_plan, kv_get, load_settings
from friday.server.events import Hub
from friday.server.plugins import load_plugins

log = logging.getLogger("friday.worker")
POLL_S = 0.05


def child(pipe: Connection, cancel_buffer: object, plugin_dir: Path) -> None:
    """The worker process: receive (snapshot, warm), send back ("plan", AssembledPlan) or ("error", traceback)."""
    load_plugins(plugin_dir)
    cancel = np.frombuffer(cancel_buffer, dtype=np.int64)  # type: ignore[call-overload]
    while True:
        job = pipe.recv()
        if job is None:
            return
        snapshot, warm = job
        try:
            pipe.send(("plan", plan_snapshot(snapshot, warm, cancel)))
        except Exception:  # anything the solve raises is reported, and the worker lives on
            pipe.send(("error", traceback.format_exc()))


@dataclass
class Job:
    snapshot: Snapshot
    warm: bool
    reason: str
    retried: bool = False
    cancelled: bool = False


@dataclass
class Waiter:
    generation: int
    done: threading.Event = field(default_factory=threading.Event)
    plan_id: int | None = None


class Supervisor:
    def __init__(self, db_path: Path, hub: Hub, clock: Callable[[], int], plugin_dir: Path, user_id: int = 1):
        self.db_path, self.hub, self.clock, self.plugin_dir, self.user_id = db_path, hub, clock, plugin_dir, user_id
        self.context = mp.get_context("spawn")
        self.cancel_buffer = self.context.RawArray("q", 1)
        self.cancel = np.frombuffer(self.cancel_buffer, dtype=np.int64)  # type: ignore[call-overload]
        self.lock = threading.Lock()
        self.due: float | None = None  # when (monotonic) the next solve should start
        self.warm = True
        self.reason = "replan"
        self.waiters: list[Waiter] = []
        self.job: Job | None = None
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self.loop, name="friday-worker", daemon=True)

    def start(self) -> None:
        self.spawn()
        self.thread.start()

    def stop(self) -> None:
        """At shutdown the solve in hand is of no use and the child holds nothing to save (the plan is saved here), so
        it's ended at once rather than asked: letting Python wind down in it made quitting slower (28 Oct)."""
        self.stopping.set()
        self.process.terminate()  # first: the thread may be waiting on it, handing it the next snapshot mid-solve
        self.thread.join(5)
        self.process.join(2)

    def spawn(self) -> None:
        orphaned_streams()
        self.pipe, theirs = self.context.Pipe()
        self.process = self.context.Process(
            target=child, args=(theirs, self.cancel_buffer, self.plugin_dir), name="friday-solver", daemon=True
        )
        self.process.start()

    def request(self, delay_s: float, warm: bool = True, reason: str = "commands") -> None:
        """Solve `delay_s` from now; each request resets the wait (the debounce). Any cold request makes it cold."""
        with self.lock:
            self.due = time.monotonic() + delay_s
            self.warm = self.warm and warm
            self.reason = reason

    def solve_now(self, reason: str, generation: int, timeout_s: float = 300) -> int | None:
        """Solve at once and wait for a plan that has seen `generation`; None if the solve failed."""
        waiter = Waiter(generation)
        with self.lock:
            self.waiters.append(waiter)
        self.request(0, reason=reason)
        waiter.done.wait(timeout_s)
        return waiter.plan_id

    def loop(self) -> None:
        conn = connect(self.db_path)
        while not self.stopping.is_set():
            try:
                self.step(conn)
            except Exception:  # the supervisor must outlive any one bad snapshot
                log.exception("worker supervisor")
                self.job = None
                self.release(None, sys.maxsize)
                self.problem(conn, "the planner failed; see the server log")
        conn.close()

    def step(self, conn: sqlite3.Connection) -> None:
        try:
            message = self.pipe.recv() if self.pipe.poll(POLL_S) else None
        except (EOFError, OSError):
            message = None
        if message is not None:
            self.finished(conn, *message)
        elif not self.process.is_alive():
            self.crashed(conn)
        self.maybe_start(conn)

    def maybe_start(self, conn: sqlite3.Connection) -> None:
        with self.lock:
            if self.due is None or time.monotonic() < self.due:
                return
            if self.job is not None:
                if not self.job.cancelled:  # chains stop within 50k steps; the newer snapshot goes next
                    self.job.cancelled = True
                    self.cancel[0] = 1
                return
            warm, reason = self.warm, self.reason
            self.due, self.warm = None, True
        snapshot = take_snapshot(conn, self.clock(), self.user_id)
        if snapshot.settings["time"].timezone is None or snapshot.settings["sleep"] is None:
            self.release(None, snapshot.generation)
            return
        self.send(Job(snapshot, warm, reason))

    def finished(self, conn: sqlite3.Connection, kind: str, payload: object) -> None:
        job, self.job = self.job, None
        if job is None or job.cancelled:
            return
        if kind == "error":
            self.failed(conn, job, str(payload))
            return
        plan_id = save_plan(conn, job.snapshot, payload, job.reason)  # type: ignore[arg-type]
        report = getattr(payload, "report", None) or {}
        log.info(
            "plan %s: %s, generation %s, %s, %.2f s, %d blocks, late %s, notices %s",
            f"P{plan_id}" if plan_id else "not saved (a newer one)",
            job.reason,
            job.snapshot.generation,
            "warm" if job.warm else "cold",
            getattr(payload, "solve_seconds", 0.0),
            len(getattr(payload, "blocks", ())),
            report.get("late_hours") or "none",
            report.get("notices") or "none",
        )
        if plan_id is None:  # a newer plan was saved meanwhile
            saved = current_plan(conn, self.user_id)
            plan_id = saved["id"] if saved else None
        self.clear_problem(conn)
        self.hub.publish("plan.changed", {"plan_id": plan_id, "generation": job.snapshot.generation})
        fire(load_settings(conn, self.user_id)["webhooks"], "plan.changed", {"plan_id": plan_id, "reason": job.reason})
        self.release(plan_id, job.snapshot.generation)

    def crashed(self, conn: sqlite3.Connection) -> None:
        if self.stopping.is_set():  # shutting down: the worker went with it, nothing to restart
            return
        log.warning("the solver worker exited (code %s); restarting", self.process.exitcode)
        job, self.job = self.job, None
        self.spawn()
        if job is None or job.cancelled:
            return
        if job.retried:
            self.failed(conn, job, "the solver worker crashed twice on this snapshot")
            return
        job.retried = True
        self.send(job)

    def send(self, job: Job) -> None:
        self.cancel[0] = 0
        self.job = job
        # A child that died just now is noticed (and the job retried) by the next step.
        with contextlib.suppress(OSError):
            self.pipe.send((job.snapshot, job.warm))

    def failed(self, conn: sqlite3.Connection, job: Job, error: str) -> None:
        folder = self.db_path.parent / "snapshots"
        folder.mkdir(exist_ok=True)
        saved = folder / f"generation-{job.snapshot.generation}.pickle"
        saved.write_bytes(pickle.dumps(job.snapshot))
        log.error("planning failed; snapshot saved to %s\n%s", saved, error)
        self.problem(conn, f"Planning failed; the last plan stays. Snapshot saved to {saved}")
        self.release(None, job.snapshot.generation)

    def release(self, plan_id: int | None, generation: int) -> None:
        """Answer the `solve_now` callers this solve satisfies."""
        with self.lock:
            done = [w for w in self.waiters if w.generation <= generation]
            self.waiters = [w for w in self.waiters if w.generation > generation]
        for waiter in done:
            waiter.plan_id = plan_id
            waiter.done.set()

    def problem(self, conn: sqlite3.Connection, message: str) -> None:
        set_problem(conn, self.user_id, "worker", message)
        self.hub.publish("status.changed")

    def clear_problem(self, conn: sqlite3.Connection) -> None:
        if "worker" in kv_get(conn, "server_problems", {}, self.user_id):
            set_problem(conn, self.user_id, "worker", None)
            self.hub.publish("status.changed")


def set_problem(conn: sqlite3.Connection, user_id: int, source: str, message: str | None) -> None:
    """Set or clear one of the banners the `status` query shows."""
    problems = kv_get(conn, "server_problems", {}, user_id)
    problems.pop(source, None)
    if message:
        problems[source] = message
    conn.execute(
        "INSERT INTO kv (user_id, key, value) VALUES (?, 'server_problems', ?) "
        "ON CONFLICT (user_id, key) DO UPDATE SET value = excluded.value",
        [user_id, json.dumps(problems)],
    )


def orphaned_streams() -> None:
    """The Mac app reads fridayd's output; once it has quit, writing there fails, and starting a worker flushes it.
    The log file has everything, so what nobody reads any more goes nowhere instead."""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        try:
            stream.flush()
        except (BrokenPipeError, OSError, ValueError):
            setattr(sys, name, open(os.devnull, "w"))  # noqa: SIM115  (kept for the life of the process)
