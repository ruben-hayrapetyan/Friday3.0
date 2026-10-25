"""The job loop (DESIGN §3.3 step 5, §15.6): a thread waking every 30 s that runs what is due, catching up once
after downtime. `job_runs` remembers when each job last ran.

- `nightly` (at `jobs.nightly_replan_at`): close yesterday (assumed progress), materialize series, refit learned
  durations and the energy map, back up the database, then a cold replan.
- `tick` (every `jobs.tick_replan_min`): a warm replan if a block boundary passed since the last plan.
- `notify` (every minute): send what is due (`commands/delivery.py`).
- `questions` (hourly): draw the day's comparison questions for the evening review, within the budget.
- `config` (every minute): apply `friday.toml` when it changed (`server/config.py`).
- `sync` (every minute): read the sources that are due and make suggestions (`commands/fetching.py`).
- `publish` (every minute): put a changed plan on the "Friday" Google calendar, debounced (`commands/google.py`).
"""

import logging
import sqlite3
import threading
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from friday.commands.delivery import deliver
from friday.commands.eventwrites import failed_writes, write_events
from friday.commands.fetching import failing_sources, sync
from friday.commands.google import publish_plan
from friday.commands.learned import learn_nightly
from friday.commands.rating import rate_upcoming
from friday.commands.refit import prepare_questions
from friday.commands.registry import run
from friday.core.db import connect, one
from friday.core.paths import config_path
from friday.core.settings import minutes_of
from friday.core.time import format_utc, local_midnight, parse_utc, to_local, to_utc
from friday.planner.store import current_plan, load_settings
from friday.server.config import apply_config
from friday.server.events import Hub
from friday.server.worker import Supervisor, set_problem
from friday.sync.google_auth import EVENTS_SCOPE, GMAIL_SCOPE, accounts, connected

log = logging.getLogger("friday.jobs")
WAKE_S = 30


class JobLoop:
    def __init__(self, db_path: Path, hub: Hub, supervisor: Supervisor | None, clock: Callable[[], int]):
        self.db_path, self.hub, self.supervisor, self.clock = db_path, hub, supervisor, clock
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self.loop, name="friday-jobs", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stopping.set()
        self.thread.join(5)

    def loop(self) -> None:
        conn = connect(self.db_path)
        while not self.stopping.is_set():
            run_due(conn, self.clock(), self.hub, self.supervisor, self.db_path.parent / "backups")
            self.stopping.wait(WAKE_S)
        conn.close()


def run_due(
    conn: sqlite3.Connection, now_utc: int, hub: Hub, supervisor: Supervisor | None, backups: Path, user_id: int = 1
) -> list[str]:
    """Run every job that is due; returns their names."""
    settings = load_settings(conn, user_id)
    if settings["time"].timezone is None or settings["sleep"] is None:
        return []
    ran = []
    jobs = (
        ("nightly", nightly_due, nightly),
        ("tick", tick_due, tick),
        ("notify", notify_due, notify),
        ("questions", questions_due, questions),
        ("config", every_minute, config),
        ("sync", every_minute, sync_sources),
        ("publish", every_minute, publish),
        ("event_writes", every_minute, send_event_writes),
        ("ratings", every_minute, rate_events),
    )
    for name, is_due, job in jobs:
        if not is_due(last_run(conn, name, user_id), now_utc, settings):
            continue
        try:
            job(conn, now_utc, settings, hub, supervisor, backups, user_id)
            record(conn, name, now_utc, user_id, None)
        except Exception as error:  # one failing job mustn't stop the others or the loop
            log.exception("job %s", name)
            record(conn, name, now_utc, user_id, f"{type(error).__name__}: {error}")
        ran.append(name)
    return ran


def last_run(conn: sqlite3.Connection, name: str, user_id: int) -> int | None:
    found = one(conn, "SELECT last_run_utc FROM job_runs WHERE user_id = ? AND name = ?", [user_id, name])
    return parse_utc(found["last_run_utc"]) if found and found["last_run_utc"] else None


def record(conn: sqlite3.Connection, name: str, now_utc: int, user_id: int, error: str | None) -> None:
    conn.execute(
        "INSERT INTO job_runs (user_id, name, last_run_utc, last_status, last_error) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (user_id, name) DO UPDATE SET last_run_utc = excluded.last_run_utc, "
        "last_status = excluded.last_status, last_error = excluded.last_error",
        [user_id, name, format_utc(now_utc), "error" if error else "ok", error],
    )


def nightly_due(last: int | None, now_utc: int, settings: dict[str, Any]) -> bool:
    """Due once the latest scheduled time has passed since the last run (so a missed night runs on start)."""
    tz, at = settings["time"].timezone, minutes_of(settings["jobs"].nightly_replan_at)
    today = to_local(now_utc, tz).date()
    scheduled = to_utc(local_midnight(today) + timedelta(minutes=at), tz)
    if scheduled > now_utc:
        scheduled = to_utc(local_midnight(today - timedelta(days=1)) + timedelta(minutes=at), tz)
    return last is None or last < scheduled


def tick_due(last: int | None, now_utc: int, settings: dict[str, Any]) -> bool:
    return last is None or now_utc - last >= settings["jobs"].tick_replan_min


def nightly(
    conn: sqlite3.Connection,
    now_utc: int,
    settings: dict[str, Any],
    hub: Hub,
    supervisor: Supervisor | None,
    backups: Path,
    user_id: int,
) -> None:
    for name in ("close_day", "materialize"):
        run(conn, name, {}, now_utc=now_utc, actor="job", user_id=user_id, provisional=False)
    learn_nightly(conn, now_utc, user_id)
    hub.publish("items.changed")
    backup(conn, backups, settings["jobs"].backup_keep, to_local(now_utc, settings["time"].timezone).date())
    if supervisor is not None:
        supervisor.request(0, warm=False, reason="nightly")


def tick(
    conn: sqlite3.Connection,
    now_utc: int,
    settings: dict[str, Any],
    hub: Hub,
    supervisor: Supervisor | None,
    backups: Path,
    user_id: int,
) -> None:
    if supervisor is not None and boundary_passed(conn, now_utc, user_id):
        supervisor.request(0, reason="tick")


def notify_due(last: int | None, now_utc: int, settings: dict[str, Any]) -> bool:
    return last is None or now_utc - last >= 1


def notify(
    conn: sqlite3.Connection,
    now_utc: int,
    settings: dict[str, Any],
    hub: Hub,
    supervisor: Supervisor | None,
    backups: Path,
    user_id: int,
) -> None:
    if deliver(conn, now_utc, backups.parent, user_id):
        hub.publish("status.changed")


def every_minute(last: int | None, now_utc: int, settings: dict[str, Any]) -> bool:
    return last is None or now_utc - last >= 1


def config(
    conn: sqlite3.Connection,
    now_utc: int,
    settings: dict[str, Any],
    hub: Hub,
    supervisor: Supervisor | None,
    backups: Path,
    user_id: int,
) -> None:
    if apply_config(conn, now_utc, config_path(), user_id):
        hub.publish("items.changed")


# `fridayd demo` puts the sample term's Google, Gmail and AI here; empty, the sync reads the real ones.
SAMPLE_APIS: dict[str, Any] = {}


def sync_sources(
    conn: sqlite3.Connection,
    now_utc: int,
    settings: dict[str, Any],
    hub: Hub,
    supervisor: Supervisor | None,
    backups: Path,
    user_id: int,
) -> None:
    made = sync(conn, now_utc, user_id, folder=backups.parent, **SAMPLE_APIS)
    if made:
        log.info("sync: %d suggestions", made)
    set_problem(conn, user_id, "sources", "; ".join(failing_sources(conn, user_id)) or None)
    set_problem(conn, user_id, "google", None if SAMPLE_APIS else google_problem(conn, settings, backups.parent))
    if made:
        hub.publish("items.changed")
        if supervisor is not None:
            supervisor.request(settings["planner"].debounce_s, reason="sync")


def google_problem(conn: sqlite3.Connection, settings: dict[str, Any], folder: Path) -> str | None:
    chosen = conn.execute("SELECT 1 FROM sources WHERE kind = 'gcal' AND enabled = 1").fetchone() is not None
    calendar, mail = settings["gcal"].read or settings["gcal"].publish or chosen, settings["gmail"].enabled
    if (calendar or mail) and not connected(folder):
        return "Google isn't connected: press Connect under Google Calendar in Settings → Integrations"
    if mail and not connected(folder, (GMAIL_SCOPE,)):  # with several accounts, any one allowing it will do
        return "Gmail isn't allowed yet: press Allow Gmail beside your account under Gmail in Settings → Integrations"
    return None


def publish(
    conn: sqlite3.Connection,
    now_utc: int,
    settings: dict[str, Any],
    hub: Hub,
    supervisor: Supervisor | None,
    backups: Path,
    user_id: int,
) -> None:
    try:
        publish_plan(conn, now_utc, user_id, backups.parent)
    except Exception as error:
        set_problem(conn, user_id, "publish", f"Publishing to Google Calendar failed: {error}"[:300])
        raise
    set_problem(conn, user_id, "publish", None)


def send_event_writes(
    conn: sqlite3.Connection,
    now_utc: int,
    settings: dict[str, Any],
    hub: Hub,
    supervisor: Supervisor | None,
    backups: Path,
    user_id: int,
) -> None:
    """Changes to your events saved back to Google (COMBINED.md 69)."""
    google = SAMPLE_APIS.get("google")
    write_events(conn, now_utc, user_id, backups.parent, google)  # changes to an account short of the OK wait
    waiting = (
        conn.execute(
            "SELECT 1 FROM event_writes WHERE user_id = ? AND done_utc IS NULL AND tries = 0", [user_id]
        ).fetchone()
        is not None
    )
    folder = backups.parent
    short = [] if google is not None else [a for a in accounts(folder) if a not in accounts(folder, (EVENTS_SCOPE,))]
    if waiting and short:
        who = ", ".join(a or "your Google account" for a in short)
        set_problem(
            conn,
            user_id,
            "event_writes",
            f"Saving your changes to Google needs Google's OK again for {who}: press Connect again beside it in "
            "Settings → Integrations",
        )
        return
    set_problem(conn, user_id, "event_writes", "; ".join(failed_writes(conn, user_id)) or None)


def rate_events(
    conn: sqlite3.Connection,
    now_utc: int,
    settings: dict[str, Any],
    hub: Hub,
    supervisor: Supervisor | None,
    backups: Path,
    user_id: int,
) -> None:
    """How much each new event needs attending, for triage's skips (COMBINED.md 56)."""
    rate_upcoming(conn, now_utc, user_id, SAMPLE_APIS.get("client"))


def questions_due(last: int | None, now_utc: int, settings: dict[str, Any]) -> bool:
    return last is None or now_utc - last >= 60


def questions(
    conn: sqlite3.Connection,
    now_utc: int,
    settings: dict[str, Any],
    hub: Hub,
    supervisor: Supervisor | None,
    backups: Path,
    user_id: int,
) -> None:
    if prepare_questions(conn, now_utc, user_id):
        hub.publish("status.changed")


def boundary_passed(conn: sqlite3.Connection, now_utc: int, user_id: int) -> bool:
    """A block of the current plan started or ended between the plan's making and now."""
    saved = current_plan(conn, user_id)
    if saved is None:
        return True
    since, now = saved["created_utc"], format_utc(now_utc)
    return (
        one(
            conn,
            "SELECT 1 FROM blocks WHERE plan_id = ? AND ((start_utc > ? AND start_utc <= ?) "
            "OR (end_utc > ? AND end_utc <= ?)) LIMIT 1",
            [saved["id"], since, now, since, now],
        )
        is not None
    )


def backup(conn: sqlite3.Connection, folder: Path, keep: int, today: date) -> Path:
    """An online SQLite backup, one per day, keeping the newest `keep`."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"friday-{today.isoformat()}.db"
    copy = sqlite3.connect(target)
    try:
        conn.backup(copy)
    finally:
        copy.close()
    for old in sorted(folder.glob("friday-*.db"))[:-keep]:
        old.unlink()
    return target
