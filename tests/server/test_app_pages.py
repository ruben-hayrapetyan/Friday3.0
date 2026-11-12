"""The HTTP API's own pages and errors (server/app.py): the page a service's sign-in sends your browser back to, and
a change refused by a model inside a command, named by its field."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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


@pytest.mark.parametrize(
    ("params", "said"),
    [
        ({"state": "abc", "error": "access_denied"}, "The service didn&#x27;t connect: you said no"),
        ({"state": "abc"}, "The service didn&#x27;t connect: no answer"),
        ({"state": "abc", "error": "<script>"}, "didn&#x27;t connect: &lt;script&gt;"),
    ],
)
def test_a_sign_in_that_didnt_connect_says_so_on_its_page(
    client: TestClient, params: dict[str, str], said: str
) -> None:
    page = client.get("/oauth/callback", params=params)
    assert page.status_code == 400 and page.headers["content-type"].startswith("text/html")
    assert "<h1 style='font-size: 20px'>Not connected</h1>" in page.text and said in page.text


def test_a_change_kept_from_what_if_that_a_command_wouldnt_take_names_its_field(client: TestClient) -> None:
    kept = client.post("/api/c/whatif_keep", json={"changes": [{"command": "edit", "input": {"title": "x"}}]})
    assert kept.status_code == 422
    assert kept.json() == {"field": "id", "message": "id: Field required"}
