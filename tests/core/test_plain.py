"""Errors said so you can act on them on the spot (8 Nov: "make all errors and warnings very user friendly so that
they can debug it on the spot"). Glass box: `plain` by an error's status and kind, `kept` keeping what the sign-in and
offline lines look for. Black box: a feed that answers 404 shows in words, without its private link; the server's
own unexpected failure comes back as a sentence, not "500 Internal Server Error"."""

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from friday.core.plain import kept, plain, status_of, without_links
from tests.commands.helpers import App, new_app


class Http(Exception):
    """An error as an HTTP library raises it, carrying a status somewhere."""

    def __init__(self, status: int, where: str = "status_code", text: str = "") -> None:
        super().__init__(text)
        if where == "resp":
            self.resp = type("Resp", (), {"status": str(status)})()
        else:
            setattr(self, where, status)


class TestGlassBox:
    @pytest.mark.parametrize("where", ["status_code", "status", "resp"])
    def test_the_status_is_found_wherever_a_library_keeps_it(self, where: str) -> None:
        assert status_of(Http(404, where)) == 404
        assert status_of(ValueError("x")) is None

    @pytest.mark.parametrize(
        ("status", "who", "words"),
        [
            (401, "Google Calendar", "refused Friday's access (401). Connect it again in Settings → Integrations"),
            (401, "The AI", "The AI refused the key (401). Check or replace it in Settings → AI"),
            (400, "The AI", "won't take Friday's request (400). Choose another model"),
            (404, "The calendar link", "isn't there any more (404)"),
            (429, "Gmail", "asked Friday to slow down (429: too many requests). Friday waits and tries again"),
            (503, "Canvas", "had a problem on its side (503). Friday tries again by itself"),
            (418, "Canvas", "Canvas said no (418)"),
        ],
    )
    def test_each_status_is_said_with_what_to_do(self, status: int, who: str, words: str) -> None:
        assert words in plain(Http(status), who)

    def test_a_retired_model_is_said_as_that(self) -> None:
        assert "isn't offered any more" in plain(Http(404, text="model: claude-x not found"), "The AI")

    def test_no_answer_and_unreadable_answers(self) -> None:
        assert "didn't answer in time" in plain(TimeoutError(), "Gmail")
        assert "couldn't be reached" in plain(ConnectionRefusedError(61, "refused"), "The AI")
        assert "couldn't read" in plain(json.JSONDecodeError("Expecting value", "", 0), "The AI")

    def test_fridays_own_words_are_kept_as_they_are(self) -> None:
        assert plain(LookupError("no longer on your Mac")) == "No longer on your Mac"

    def test_anything_else_keeps_its_reason_short_and_without_links(self) -> None:
        said = plain(ValueError("tool_choice is not supported, see https://x.example/secret?token=abc"), "The AI")
        assert "tool_choice is not supported" in said and "token=abc" not in said and "Diagnose" in said
        assert without_links("at https://feed.example/x.ics?k=1 now") == "at (link) now"
        assert without_links("webcal://feed.example/cal?token=t and url: /x.ics?token=t") == "(link) and url: (link)"

    def test_kept_leaves_what_the_sign_in_and_offline_lines_read(self) -> None:
        class RefreshError(Exception):
            pass

        assert kept(RefreshError("invalid_grant: Token has been expired"), "Gmail").startswith("RefreshError:")
        assert "nodename nor servname" in kept(OSError("[Errno 8] nodename nor servname provided"), "Gmail")
        assert kept(Http(503), "Gmail").startswith("Gmail had a problem on its side")


class TestBlackBox:
    def test_a_feed_that_is_gone_says_so_in_words_without_its_link(self, tmp_path: Path) -> None:
        from friday.commands import fetching

        app = new_app(tmp_path)
        url = "https://canvas.example.edu/feeds/calendars/user_SECRETTOKEN.ics"

        def gone(link: str) -> str:
            request = httpx.Request("GET", link)
            raise httpx.HTTPStatusError(
                "Client error '404 Not Found'", request=request, response=httpx.Response(404, request=request)
            )

        app.do("source_add", kind="ics", name="canvas", url=url)
        fetching.sync(app.conn, app.now_utc, 1, fetch=gone)
        said = next(s for s in app.table("sources") if s["name"] == "canvas")["last_error"]
        assert said.startswith("The calendar link isn't there any more (404)") and "SECRETTOKEN" not in said


@pytest.fixture
def client(tmp_path: Path) -> Iterator[tuple[App, TestClient]]:
    from friday.server.app import create_app

    app = new_app(tmp_path)
    served = create_app(tmp_path / "friday.db", clock=lambda: app.now_utc, background=False, plugin_dir=tmp_path)
    with TestClient(served, raise_server_exceptions=False) as client:
        yield app, client


def test_an_unexpected_failure_is_a_sentence_not_a_500_page(
    client: tuple[App, TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole server: a query that breaks inside answers JSON in words, the toast's words."""
    from friday.commands import queries

    def broken(*_: object, **__: object) -> None:
        raise KeyError("plan_id")

    monkeypatch.setattr(queries, "current_plan", broken)
    _, http = client
    answer = http.get("/api/q/status")
    assert answer.status_code == 500
    body = answer.json()
    assert body["field"] is None and body["message"].startswith("Something went wrong inside Friday (KeyError)")
    assert "Try again" in body["message"] and "Diagnose" in body["message"]
