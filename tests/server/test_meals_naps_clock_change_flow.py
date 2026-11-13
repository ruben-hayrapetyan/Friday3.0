"""Meals and naps the night the clocks go back, end to end through the HTTP API the web app uses (audit, 12 Nov: read
as clock times, they were an hour off across the change). Tracking switched on, a late snack and a nap logged in
Sleep & meals across 2am on 1 Nov 2026 in New York, then the Meals and Sleep pages read: each keeps the clock times
you gave, and lasts the real minutes that went by."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from friday.server.app import create_app
from tests.commands.helpers import App, new_app
from tests.server.test_combined_flows import ask


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, now="2026-11-02T20:00")


@pytest.fixture
def client(app: App, tmp_path: Path) -> Iterator[TestClient]:
    served = create_app(tmp_path / "friday.db", clock=lambda: app.now_utc, background=False, plugin_dir=tmp_path)
    with TestClient(served) as client:
        yield client


def post(client: TestClient, name: str, body: dict) -> None:
    out = client.post(f"/api/c/{name}", json=body)
    assert out.status_code == 200, out.text


def test_a_snack_and_a_nap_across_the_change_keep_their_times_and_real_lengths(client: TestClient) -> None:
    post(client, "settings_set", {"key": "meal_tracking", "value": {"on": True}})
    post(client, "settings_set", {"key": "sleep_tracking", "value": {"on": True}})
    post(client, "meal_log", {"kind": "snack", "start": "2026-11-01T01:00", "end": "2026-11-01T03:00"})
    post(client, "nap_log", {"start": "2026-11-01T01:30", "end": "2026-11-01T02:30"})
    (day,) = [d for d in ask(client, "meals")["days"] if d["date"] == "2026-10-31"]  # type: ignore[index]
    assert [(m["start"], m["end"], m["minutes"]) for m in day["meals"]] == [
        ("2026-11-01T01:00", "2026-11-01T03:00", 180)
    ]
    (nap,) = ask(client, "sleep")["naps"]  # type: ignore[index]
    assert (nap["start"], nap["end"], nap["minutes"]) == ("2026-11-01T01:30", "2026-11-01T02:30", 120)
