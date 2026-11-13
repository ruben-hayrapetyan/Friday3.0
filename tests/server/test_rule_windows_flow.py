"""A rule's hours run to your day's start, end to end through the HTTP API the web app uses, the plan solved in the
request (audit, 12 Nov: they ran to 4am whatever your day start). A night owl's day starts at 6am and sleep is 6am to
1pm; "Never work after 10pm" is added in the Rules box, Always. The evening is taken up to 4am, and an hour of work is
due at 6am: 4am to 6am is still after 10pm in that day, so the work isn't planned there (it's left unplanned, late),
where before it went into 4am to 6am."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from friday.server.app import create_app
from tests.commands.helpers import TZ, App, new_app
from tests.server.test_combined_flows import ask, blocks

OWL = {d: {"bedtime": "06:00", "wake": "13:00", "margin_min": 0} for d in ("mon", "tue", "wed", "thu", "fri", "sat",
                                                                         "sun")}  # fmt: skip


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, now="2026-10-19T14:00", horizon_days=7)  # Monday afternoon


@pytest.fixture
def client(app: App, tmp_path: Path) -> Iterator[TestClient]:
    served = create_app(tmp_path / "friday.db", clock=lambda: app.now_utc, background=False, plugin_dir=tmp_path)
    with TestClient(served) as client:
        yield client


def post(client: TestClient, name: str, body: dict) -> dict:
    out = client.post(f"/api/c/{name}", json=body)
    assert out.status_code == 200, out.text
    return out.json()["result"]


def owl_with_a_full_evening(client: TestClient, rule: bool) -> int:
    post(client, "settings_set", {"key": "time", "value": {"timezone": TZ, "horizon_days": 7, "day_start": "06:00"}})
    post(client, "settings_set", {"key": "sleep", "value": OWL})
    if rule:
        post(client, "rule_add", {"text": "Never work after 10pm", "strength": "Always"})
    post(client, "add", {"title": "Shift", "when": "fixed", "start": "2026-10-19T14:00", "end": "2026-10-20T04:00",
                         "color": None, "notes": "", "location": None})  # fmt: skip
    made = post(client, "add", {"title": "Essay", "duration_min": 60, "due": "2026-10-20T06:00", "firmness": "hard"})
    post(client, "replan", {})
    return made["item"]["id"]


def test_the_rule_shown_runs_to_6am(client: TestClient) -> None:
    owl_with_a_full_evening(client, rule=True)
    (rule,) = [r for r in ask(client, "settings")["rules"] if r["reason"] == "No work after 10pm"]  # type: ignore[index]
    assert (rule["params"]["start"], rule["params"]["end"]) == ("22:00", "06:00")


def test_no_work_goes_between_4am_and_your_6am_day_start(client: TestClient) -> None:
    essay = owl_with_a_full_evening(client, rule=True)
    assert [b for b in blocks(client, essay) if b[0] < "2026-10-20T06:00"] == []


def test_without_the_rule_that_time_is_used(client: TestClient) -> None:
    essay = owl_with_a_full_evening(client, rule=False)
    assert blocks(client, essay) == [("2026-10-20T04:00", "2026-10-20T05:00")]
