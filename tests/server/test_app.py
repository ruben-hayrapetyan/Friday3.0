"""The HTTP API generated from the registry, without the worker: `replan` solves in the request."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from friday.commands.all import REGISTRY
from friday.server.app import create_app
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=3)


@pytest.fixture
def client(app: App, tmp_path: Path) -> Iterator[TestClient]:
    served = create_app(tmp_path / "friday.db", clock=lambda: app.now_utc, background=False, plugin_dir=tmp_path)
    with TestClient(served) as client:
        yield client


def test_every_command_and_query_has_a_typed_route(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    operations = {op["operationId"] for path in schema["paths"].values() for op in path.values()}
    assert set(REGISTRY) <= operations
    add = schema["paths"]["/api/c/add"]["post"]
    result = add["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].rsplit("/", 1)[1]
    assert schema["components"]["schemas"][result]["properties"]["result"]["$ref"].endswith("/AddOutput")


def test_a_command_answers_with_its_id_result_and_ghosts(client: TestClient) -> None:
    out = client.post("/api/c/add", json={"text": "essay due tue 17:00 ~2h"}).json()
    assert out["command_id"] and out["result"]["item"]["title"] == "essay"
    assert any(g["title"] == "essay" for g in out["provisional"])


def test_queries_take_query_parameters(client: TestClient) -> None:
    client.post("/api/c/add", json={"text": "essay ~2h"})
    client.post("/api/c/add", json={"text": "laundry ~1h"})
    assert [i["title"] for i in client.get("/api/q/items", params={"text": "laund"}).json()] == ["laundry"]
    assert client.get("/api/q/item", params={"id": 1}).json()["item"]["title"] == "essay"


def test_a_query_with_a_mapping_is_posted(client: TestClient) -> None:
    client.post("/api/c/add", json={"text": "essay due tue 17:00 ~2h"})
    client.post("/api/c/replan")
    changed = client.post("/api/q/preview_weights", json={"weights": {"spread": 2}})
    assert changed.status_code == 200 and "rule_totals_after" in changed.json()


def test_the_cli_is_logged_as_cli_and_the_web_as_you(client: TestClient) -> None:
    client.post("/api/c/add", json={"text": "a ~30m"}, headers={"X-Friday-Client": "cli"})
    client.post("/api/c/add", json={"text": "b ~30m"})
    assert [e["actor"] for e in client.get("/api/q/log_list").json()][:2] == ["you", "cli"]


def test_preview_changes_nothing_and_an_idempotency_key_runs_once(client: TestClient) -> None:
    preview = client.post("/api/c/add", params={"preview": True}, json={"text": "essay ~2h"}).json()
    assert preview["preview"] and client.get("/api/q/items").json() == []
    first = client.post("/api/c/add", json={"text": "essay ~2h"}, headers={"Idempotency-Key": "k1"}).json()
    again = client.post("/api/c/add", json={"text": "essay ~2h"}, headers={"Idempotency-Key": "k1"}).json()
    assert again["repeated"] and again["command_id"] == first["command_id"]
    assert len(client.get("/api/q/items").json()) == 1


def test_a_full_preview_lists_what_a_solve_would_change_and_saves_nothing(client: TestClient) -> None:
    client.post("/api/c/add", json={"text": "essay due tue 17:00 ~2h"})
    client.post("/api/c/replan")
    plan = client.get("/api/q/plan").json()
    preview = client.post("/api/c/add", params={"preview": "full"}, json={"text": "report due tue 12:00 ~1h"}).json()
    assert preview["preview"] and {b["title"] for b in preview["changes"]["added"]} == {"report"}
    assert preview["changes"]["late_hours"] == {}
    assert len(client.get("/api/q/items").json()) == 1 and client.get("/api/q/plan").json() == plan


def test_errors_name_the_field(client: TestClient) -> None:
    refused = client.post("/api/c/add", json={"title": "essay", "firmness": "hard"})
    assert refused.status_code == 422 and refused.json()["field"] == "due_utc"
    missing = client.post("/api/c/edit", json={"title": "no id"})
    assert missing.status_code == 422


def test_replan_without_a_worker_solves_in_the_request(client: TestClient) -> None:
    client.post("/api/c/add", json={"text": "essay due tue 17:00 ~2h"})
    answer = client.post("/api/c/replan").json()["result"]
    assert answer["status"] == "current"
    assert {b["title"] for b in client.get("/api/q/plan").json()["blocks"]} == {"essay"}


def test_undo_through_the_api(client: TestClient) -> None:
    added = client.post("/api/c/add", json={"text": "essay ~2h"}).json()
    client.post("/api/c/undo", json={"command_id": added["command_id"]})
    assert client.get("/api/q/items").json() == []


def test_a_backup_downloads_the_whole_database(client: TestClient, tmp_path: Path) -> None:
    import sqlite3

    client.post("/api/c/add", json={"text": "essay due wed 17:00 ~2h"})
    got = client.get("/api/backup")
    assert got.status_code == 200 and got.headers["content-disposition"].startswith("attachment")
    copy = tmp_path / "copy.db"
    copy.write_bytes(got.content)
    assert sqlite3.connect(copy).execute("SELECT title FROM items").fetchall() == [("essay",)]


def test_the_websites_own_pages_open_on_a_reload_and_missing_files_stay_missing(app: App, tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html>Friday")
    (dist / "assets" / "app.js").write_text("ok")
    served = create_app(tmp_path / "friday.db", clock=lambda: app.now_utc, background=False, web_dist=dist)
    with TestClient(served) as client:
        for page in ("/", "/settings", "/todo/12", "/lab/rules"):
            assert client.get(page).text == "<!doctype html>Friday", page
        assert client.get("/assets/app.js").text == "ok"
        assert client.get("/assets/gone.js").status_code == 404
        assert client.get("/api/q/no_such_query").status_code == 404
