"""What the app is told after a command (12 Nov, "the acceptances and rejections for the inbox are very very slow"):
each change event has the app read things again, on the same Mac, so a change names its command, for the app to
refresh only what that command touches (web/src/api/events.ts)."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from friday.server.app import create_app
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=3)


@pytest.fixture
def heard(app: App, tmp_path: Path) -> Iterator[tuple[TestClient, list[tuple[str, Any]]]]:
    served = create_app(tmp_path / "friday.db", clock=lambda: app.now_utc, background=False, plugin_dir=tmp_path)
    events: list[tuple[str, Any]] = []
    hub = served.state.services.hub
    hub.publish = lambda event, data=None: events.append((event, data))  # type: ignore[method-assign]
    with TestClient(served) as client:
        yield client, events


def test_a_change_names_its_command(heard: tuple[TestClient, list[tuple[str, Any]]]) -> None:
    client, events = heard
    added = client.post("/api/c/add", json={"text": "essay 2h due fri"})
    assert added.status_code == 200
    assert ("items.changed", {"command": "add"}) in events
