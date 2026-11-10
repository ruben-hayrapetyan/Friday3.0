"""Not now, for Friday's questions in the Inbox (PROGRESS.md C75): kept on the server with what each was based on,
so the Mac and the phone count the same Inbox; asked again once that changes (the Inbox compares)."""

from pathlib import Path

import pytest

from friday.core.items import FieldError
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


# Black box: through the commands.


def test_nothing_set_aside_at_first(app: App) -> None:
    assert app.do("asks_later") == {"later": {}}


def test_not_now_keeps_the_question_with_its_evidence(app: App) -> None:
    app.do("ask_later", key="durations", evidence="8")
    app.do("ask_later", key="meal-time:dinner", evidence="19:00")
    assert app.do("asks_later") == {"later": {"durations": "8", "meal-time:dinner": "19:00"}}


def test_not_now_again_keeps_the_newest_evidence(app: App) -> None:
    app.do("ask_later", key="durations", evidence="8")
    app.do("ask_later", key="durations", evidence="11")
    assert app.do("asks_later")["later"] == {"durations": "11"}


def test_a_question_must_be_named(app: App) -> None:
    with pytest.raises(FieldError, match="which question"):
        app.do("ask_later", key=" ", evidence="1")


# Glass box: one kv row, and undo takes the answer back.


def test_undo_brings_the_question_back(app: App) -> None:
    done = app.full("ask_later", payload={"key": "energy", "evidence": "3"}, provisional=False)
    app.do("undo", command_id=done.command_id)
    assert app.do("asks_later")["later"] == {}


# The whole system: the Inbox's Not now, through the server.


def test_through_the_server(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from friday.server.app import create_app

    app = new_app(tmp_path)
    served = create_app(tmp_path / "friday.db", clock=lambda: app.now_utc, background=False, plugin_dir=tmp_path)
    with TestClient(served, base_url="http://127.0.0.1:8765") as web:
        assert web.post("/api/c/ask_later", json={"key": "sleep-times", "evidence": "bed23:45"}).status_code == 200
        assert web.get("/api/q/asks_later").json() == {"later": {"sleep-times": "bed23:45"}}
