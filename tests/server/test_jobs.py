"""The job loop: when nightly and tick are due, and what they do (with a stand-in for the worker)."""

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from friday.planner.service import replan
from friday.planner.store import load_settings
from friday.server.events import Hub
from friday.server.jobs import backup, nightly_due, run_due
from tests.commands.helpers import App, new_app


class Worker:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def request(self, delay_s: float, warm: bool = True, reason: str = "commands") -> None:
        self.requests.append({"warm": warm, "reason": reason})


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=3)


def run_jobs(app: App, worker: Worker, tmp_path: Path) -> list[str]:
    return run_due(app.conn, app.now_utc, Hub(), worker, tmp_path / "backups")  # type: ignore[arg-type]


def test_nightly_is_due_once_after_its_time_and_catches_up_after_downtime(app: App) -> None:
    settings = load_settings(app.conn)
    at = app.at("2026-10-20T03:31").now_utc
    assert nightly_due(None, at, settings)
    assert not nightly_due(at, app.at("2026-10-21T03:00").now_utc, settings)
    assert nightly_due(at, app.at("2026-10-21T03:30").now_utc, settings)
    assert nightly_due(at, app.at("2026-10-25T12:00").now_utc, settings)  # off for days: runs once on start


def test_nightly_closes_yesterday_backs_up_and_asks_for_a_cold_replan(app: App, tmp_path: Path) -> None:
    essay = app.do("add", text="essay due wed ~1h")["item"]["id"]
    app.do("pin", id=essay, start="2026-10-19T10:00", kind="locked")
    replan(app.conn, app.now_utc)
    app.at("2026-10-20T04:00")
    worker = Worker()
    assert run_jobs(app, worker, tmp_path) == [
        "nightly",
        "tick",
        "questions",
        "config",
        "sync",
        "integrations",
        "publish",
        "event_writes",
        "ratings",
        "meals",
        "updates",
    ]
    assert [r["last_error"] for r in app.table("job_runs") if r["last_error"]] == []
    assumed = [(p["item_id"], p["minutes"]) for p in app.table("progress") if p["source"] == "assumed"]
    assert assumed == [(essay, 60)]
    assert (tmp_path / "backups" / "friday-2026-10-20.db").exists()
    assert {"warm": False, "reason": "nightly"} in worker.requests
    assert run_jobs(app, worker, tmp_path) == []  # nothing is due again straight away


def test_a_reviewed_day_gets_no_assumptions(app: App, tmp_path: Path) -> None:
    essay = app.do("add", text="essay due wed ~1h")["item"]["id"]
    app.do("pin", id=essay, start="2026-10-19T10:00", kind="locked")
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00").do("review_submit", entries=[])
    app.at("2026-10-20T04:00")
    run_jobs(app, Worker(), tmp_path)
    assert [p["source"] for p in app.table("progress")] == ["review"]


def test_materialize_adds_the_occurrences_that_came_into_range(app: App) -> None:
    app.do("add", text="gym every mon,wed ~1h")
    assert app.do("materialize")["message"] == "0 new occurrences"
    assert app.at("2026-10-26T09:00").do("materialize")["message"] == "2 new occurrences"


def test_tick_replans_when_a_block_boundary_passed_and_not_for_a_timer(app: App, tmp_path: Path) -> None:
    app.do("add", text="essay due tue 17:00 ~2h")
    replan(app.conn, app.now_utc)
    app.conn.execute("INSERT INTO job_runs (name, last_run_utc) VALUES ('nightly', '2026-10-19T13:00Z')")
    worker = Worker()
    assert (
        run_jobs(app, worker, tmp_path)
        == ["tick", "questions", "config", "sync", "integrations", "publish", "event_writes", "ratings", "meals",
            "updates"]  # fmt: skip
        and worker.requests == []
    )
    app.at("2026-10-19T09:15").do("start", id=1)  # the timer is an overlay on the plan, not a reason to replan
    app.at("2026-10-19T09:16")
    run_jobs(app, worker, tmp_path)
    assert worker.requests == []
    app.at(max(b["end"] for b in app.do("plan")["blocks"]))
    run_jobs(app, worker, tmp_path)
    assert worker.requests == [{"warm": True, "reason": "tick"}]


def test_backups_keep_the_newest(app: App, tmp_path: Path) -> None:
    for day in (18, 19, 20):
        backup(app.conn, tmp_path / "backups", 2, date(2026, 10, day))
    assert sorted(p.name for p in (tmp_path / "backups").iterdir()) == ["friday-2026-10-19.db", "friday-2026-10-20.db"]


def test_jobs_wait_until_friday_is_set_up(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    app.do("settings_set", key="sleep", value=None)
    assert run_jobs(app, Worker(), tmp_path) == []


def test_the_daemon_log_file_takes_every_logger_under_friday(tmp_path: Path) -> None:
    import logging

    from friday.server.logs import install

    where = install(tmp_path, "info")
    logging.getLogger("friday.commands").info("add by you: C7, 12 ms")
    logging.getLogger("friday.worker").warning("the solver worker exited")
    text = where.read_text()
    assert "friday.commands: add by you: C7" in text and "WARNING friday.worker" in text


def test_meals_you_let_friday_decide_are_planned_by_the_job(app: App, tmp_path: Path) -> None:
    app.do("settings_set", key="meal_tracking", value={"on": True})
    for day in range(12, 19):
        app.do("meal_log", kind="breakfast", start=f"2026-10-{day}T08:00", end=f"2026-10-{day}T08:15")
    app.do("rule_add", text="Let Friday decide breakfast")
    worker = Worker()
    run_jobs(app, worker, tmp_path)
    assert any(r["title"] == "Breakfast" for r in app.table("items"))
    assert {"warm": True, "reason": "meals"} in worker.requests
