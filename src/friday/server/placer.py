"""The quick placement after the answer (27 Oct): a change used to wait for it before answering, most of a second on a
real calendar, so a click took that long to show. Now the change answers once it's saved and this places what changed
(`planner/service.placement`), keeps it for the plan view, then says so (`plan.provisional`) and the app redraws the
plan, which shows the placement until the solve lands. Changes since the saved plan are placed together: each
placement starts again from the saved plan, so one placed alone would lose what the one before it moved.

The placing is done in a process of its own, as the solve is: on a thread of the server's it held Python's lock while
it worked, and a change made meanwhile waited for it (a tenth of a second each). A thread here hands it the changes,
keeps what comes back and tells the app.
"""

import logging
import multiprocessing as mp
import sqlite3
import threading
import time
import traceback
from collections.abc import Callable
from multiprocessing.connection import Connection
from pathlib import Path

from friday.api.types import BlockOut
from friday.core.db import begin_write, connect, held
from friday.planner.assemble import PlannedBlock
from friday.planner.service import keep_provisional, placement
from friday.planner.store import current_plan
from friday.server.events import Hub
from friday.server.plugins import load_plugins
from friday.server.worker import orphaned_streams

log = logging.getLogger("friday.placer")

Placing = tuple[int, set[int], dict[int, list[tuple[int, int]]]]  # generation, items changed, spans left by item
Placed = tuple[int, list[PlannedBlock], list[BlockOut]]  # the generation seen, the blocks, as the calendar shows them


def child(pipe: Connection, db_path: Path, plugin_dir: Path) -> None:
    """The placing process: receive (now, user, changed, left), send back ("placed", Placed or None) or ("error", …)."""
    load_plugins(plugin_dir)
    conn = connect(db_path)
    while True:
        job = pipe.recv()
        if job is None:
            return
        try:
            pipe.send(("placed", read_placement(conn, *job)))
        except Exception:  # anything a placement raises is reported, and the process lives on
            pipe.send(("error", traceback.format_exc()))


def read_placement(
    conn: sqlite3.Connection, now: int, user_id: int, changed: set[int], left: dict[int, list[tuple[int, int]]]
) -> Placed | None:
    """The placement, read in one transaction (a snapshot of one moment) that writes nothing."""
    conn.execute("BEGIN")
    try:
        return placement(conn, now, user_id, changed, left)
    finally:
        conn.execute("COMMIT")


class Placer:
    def __init__(self, db_path: Path, hub: Hub, clock: Callable[[], int], plugin_dir: Path | None = None):
        self.db_path, self.hub, self.clock, self.plugin_dir = db_path, hub, clock, plugin_dir
        self.lock = threading.Lock()
        self.due: dict[int, list[Placing]] = {}  # by user: changes since the saved plan
        self.asked: set[int] = set()  # users with a placement to make
        self.wake = threading.Event()
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self.loop, name="friday-placer", daemon=True)
        self.pipe: Connection | None = None  # to the placing process, once started

    def start(self) -> None:
        orphaned_streams()
        context = mp.get_context("spawn")
        self.pipe, theirs = context.Pipe()
        self.process = context.Process(
            target=child, args=(theirs, self.db_path, self.plugin_dir), name="friday-placer", daemon=True
        )
        self.process.start()
        self.thread.start()

    def stop(self) -> None:
        """The placing process only reads, so at shutdown it's ended at once rather than asked (as the solver's)."""
        self.stopping.set()
        self.wake.set()
        if self.pipe is not None:
            self.process.terminate()  # first: the thread may be waiting on its answer
        self.thread.join(5)
        if self.pipe is not None:
            self.process.join(2)

    def request(self, user_id: int, placing: Placing) -> None:
        with self.lock:
            self.due.setdefault(user_id, []).append(placing)
            self.asked.add(user_id)
        self.wake.set()

    def loop(self) -> None:
        conn = connect(self.db_path)
        while not self.stopping.is_set():
            self.wake.wait(1)
            self.wake.clear()
            with self.lock:
                users, self.asked = self.asked, set()
            for user_id in users:
                try:
                    self.place(conn, user_id)
                except Exception:  # a failed placement leaves the saved plan showing until the solve
                    log.exception("quick placement")
        conn.close()

    def place(self, conn: sqlite3.Connection, user_id: int, here: bool = False) -> list[BlockOut] | None:
        """Place every change since the saved plan, keep it for the plan view, and say so; None until set up. In the
        placing process when it runs, else (or `here`: a request that waits for it, on its own thread, as the pipe to
        the process is the placer thread's alone) in this one."""
        saved = current_plan(conn, user_id)
        with self.lock:
            since = [p for p in self.due.get(user_id, []) if saved is None or p[0] > saved["generation"]]
            self.due[user_id] = since
        changed = {i for _, items, _ in since for i in items}
        left: dict[int, list[tuple[int, int]]] = {}
        for _, _, spans in since:
            for item, item_spans in spans.items():
                left.setdefault(item, []).extend(item_spans)
        if self.pipe is not None and not here:
            placed = self.ask(user_id, changed, left)
        else:
            placed = read_placement(conn, self.clock(), user_id, changed, left)
        if placed is None:
            return None
        made_at, blocks, shown = placed
        begin_write(conn, "keeping a quick placement")
        since = time.perf_counter()
        try:
            keep_provisional(conn, user_id, made_at, blocks)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        held("keeping a quick placement", since)
        self.hub.publish("plan.provisional", {"generation": made_at})
        return shown

    def ask(self, user_id: int, changed: set[int], left: dict[int, list[tuple[int, int]]]) -> Placed | None:
        assert self.pipe is not None
        self.pipe.send((self.clock(), user_id, changed, left))
        kind, value = self.pipe.recv()
        if kind == "error":
            log.error("quick placement failed in its process:\n%s", value)
            return None
        return value
