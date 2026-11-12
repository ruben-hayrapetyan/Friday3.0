"""The job loop's banners and failures (server/jobs.py): a job that raises is recorded and the others still run,
publishing's failure is said in words, `friday.toml` changing tells the app, and Google or Gmail chosen but not
connected is said with where to connect."""

from pathlib import Path
from typing import Any

import pytest

from friday.planner.store import kv_get
from friday.server import jobs
from friday.server.jobs import run_due
from tests.commands.helpers import App, new_app


class Recorder:
    def __init__(self) -> None:
        self.events: list[str] = []

    def publish(self, event: str, data: Any = None) -> None:
        self.events.append(event)


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=3)


def run_jobs(app: App, tmp_path: Path, hub: Recorder | None = None) -> list[str]:
    return run_due(app.conn, app.now_utc, hub or Recorder(), None, tmp_path / "backups")  # type: ignore[arg-type]


def problems(app: App) -> dict[str, str]:
    return kv_get(app.conn, "server_problems", {}, 1)


def job_run(app: App, name: str) -> dict[str, Any]:
    return next(r for r in app.table("job_runs") if r["name"] == name)


def test_a_failing_publish_is_said_recorded_and_the_other_jobs_still_run(
    app: App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def publish_plan(*args: Any) -> None:
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(jobs, "publish_plan", publish_plan)
    ran = run_jobs(app, tmp_path)
    assert "publish" in ran and ran[-1] == "updates"
    assert problems(app)["publish"] == "Publishing to Google Calendar failed: quota exceeded"
    run = job_run(app, "publish")
    assert run["last_status"] == "error" and run["last_error"] == "RuntimeError: quota exceeded"
    assert job_run(app, "event_writes")["last_status"] == "ok"
    monkeypatch.setattr(jobs, "publish_plan", lambda *args: None)
    app.at("2026-10-19T09:05")
    run_jobs(app, tmp_path)
    assert "publish" not in problems(app) and job_run(app, "publish")["last_status"] == "ok"


def test_a_changed_settings_file_tells_the_app(app: App, tmp_path: Path, no_personal_config: Path) -> None:
    run_jobs(app, tmp_path)
    (no_personal_config / "friday.toml").write_text("[planner]\ndebounce_s = 7\n")
    heard = Recorder()
    app.at("2026-10-19T09:05")
    run_jobs(app, tmp_path, heard)
    assert "items.changed" in heard.events
    assert [r["actor"] for r in app.table("command_log")][-1] == "config"


def test_google_chosen_but_not_connected_says_where_to_connect(app: App, tmp_path: Path) -> None:
    app.do("settings_set", key="gcal", value={"read": ["primary"]})
    run_jobs(app, tmp_path)
    assert problems(app)["google"] == (
        "Google isn't connected: press Connect under Google Calendar in Settings → Integrations"
    )


def test_gmail_on_without_its_permission_says_to_allow_it(
    app: App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An account connected for its calendars only: no Gmail scope.
    monkeypatch.setattr(jobs, "connected", lambda folder, scopes=(): not scopes)
    app.do("settings_set", key="gmail", value={"enabled": True})
    assert jobs.google_problem(app.conn, jobs.load_settings(app.conn), tmp_path) == (
        "Gmail isn't allowed yet: press Allow Gmail beside your account under Gmail in Settings → Integrations"
    )
    monkeypatch.setattr(jobs, "connected", lambda folder, scopes=(): True)
    assert jobs.google_problem(app.conn, jobs.load_settings(app.conn), tmp_path) is None
