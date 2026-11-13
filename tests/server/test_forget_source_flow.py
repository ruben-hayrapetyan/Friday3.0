"""A feed removed with "forget" keeps what you accepted from it, end to end through the HTTP API the web app uses
(audit, 12 Nov: forgetting deleted the accepted suggestions too): the feed added and read, one suggestion accepted and
one rejected, then Settings' Remove with forget; the inbox is empty, the feed gone, and the to-do you accepted is
still yours, still tied to the suggestion that made it."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from friday.commands.fetching import sync
from friday.server.app import create_app
from tests.commands.helpers import App, new_app
from tests.ingest.fakes import FEED
from tests.server.test_combined_flows import ask, do


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=7)


@pytest.fixture
def client(app: App, tmp_path: Path) -> Iterator[TestClient]:
    served = create_app(tmp_path / "friday.db", clock=lambda: app.now_utc, background=False, plugin_dir=tmp_path)
    with TestClient(served) as client:
        yield client


def test_forgetting_a_feed_keeps_the_to_do_you_accepted_from_it(client: TestClient, app: App) -> None:
    added = client.post("/api/c/source_add", json={"name": "Canvas", "url": "https://example.edu/feed.ics"})
    assert added.status_code == 200, added.text
    sync(app.conn, app.now_utc, fetch=lambda url: FEED)  # the job's next minute
    inbox = ask(client, "inbox")
    waiting = {s["input"].get("title", s["origin"]): s["id"] for s in inbox["suggestions"]}  # type: ignore[index]
    do(client, "suggestion_accept", id=waiting["PS4"])
    do(client, "suggestion_reject", id=waiting["Essay draft"])
    source = inbox["sources"][0]["id"]  # type: ignore[index]
    said = do(client, "source_remove", id=source, forget=True)["result"]["message"]
    assert said == "Removed Canvas and what it brought in; the one you accepted stays"
    after = ask(client, "inbox")
    assert after["suggestions"] == [] and after["sources"] == []  # type: ignore[index]
    (item,) = ask(client, "items")  # type: ignore[misc]
    assert item["title"] == "PS4"
    (kept,) = app.table("suggestions")
    assert (kept["id"], kept["status"], kept["item_id"]) == (waiting["PS4"], "accepted", item["id"])
