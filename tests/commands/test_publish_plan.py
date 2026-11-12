"""Publishing the plan to Google (commands/google.py) at the edges: a new plan waits out the debounce after the last
publish, and with no Google account connected nothing is sent."""

from pathlib import Path

from friday.commands.google import publish_plan
from friday.planner.service import replan
from friday.sim.fakes import FakeGoogle
from tests.commands.helpers import App, new_app


def planned(tmp_path: Path, debounce_s: int) -> App:
    app = new_app(tmp_path)
    app.do("add", text="essay due wed 17:00 ~3h")
    replan(app.conn, app.now_utc)
    app.do("settings_set", key="gcal", value={"publish": True, "publish_debounce_s": debounce_s})
    return app


def test_a_new_plan_waits_out_the_debounce_after_the_last_publish(tmp_path: Path) -> None:
    app = planned(tmp_path, 600)
    google = FakeGoogle()
    assert publish_plan(app.conn, app.now_utc, google=google)
    replan(app.conn, app.now_utc + 1)
    assert not publish_plan(app.conn, app.now_utc + 5, google=google)  # 5 minutes of the 10
    assert publish_plan(app.conn, app.now_utc + 11, google=google)


def test_with_no_google_account_nothing_is_published(tmp_path: Path) -> None:
    app = planned(tmp_path, 0)
    assert not publish_plan(app.conn, app.now_utc, google={})
