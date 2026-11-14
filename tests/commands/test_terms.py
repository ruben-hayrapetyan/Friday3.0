"""Friday's terms (PROGRESS.md C71): everyone accepts them before Friday opens, again each time they change; only you
can accept them; the copy on GitHub is the one in the app; the license is PolyForm Noncommercial."""

import json
from pathlib import Path

import pytest

from friday.core import terms
from friday.core.items import FieldError
from tests.commands.helpers import App, new_app

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


# Black box: through the commands.


def test_a_new_user_must_accept(app: App) -> None:
    shown = app.do("terms")
    assert shown["needed"] is True and shown["accepted"] is None
    assert shown["version"] == terms.current().version and "# Friday's terms" in shown["text"]


def test_accepting_opens_friday(app: App) -> None:
    app.do("terms_accept", version=terms.current().version)
    shown = app.do("terms")
    assert (shown["needed"], shown["accepted"]) == (False, terms.current().version)


def test_terms_changed_while_open_are_read_again(app: App) -> None:
    with pytest.raises(FieldError, match="changed while you were reading"):
        app.do("terms_accept", version="2000-01-01")
    assert app.do("terms")["needed"] is True


def test_a_change_to_the_terms_asks_again(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    app.do("terms_accept", version=terms.current().version)
    newer = terms.Terms("2027-01-01", "# Friday's terms\n\nVersion: 2027-01-01\n", ("Prices are in section 4.",))
    monkeypatch.setattr(terms, "current", lambda: newer)
    shown = app.do("terms")
    assert (shown["needed"], shown["accepted"], shown["changes"]) == (
        True,
        "2026-11-09.2",
        ["Prices are in section 4."],
    )
    app.do("terms_accept", version="2027-01-01")
    assert app.do("terms")["needed"] is False


def test_an_assistant_cant_accept_for_you(app: App) -> None:
    app.actor = "mcp:claude"
    with pytest.raises(FieldError, match="Only you can do that"):
        app.do("terms_accept", version=terms.current().version)
    app.actor = "you"
    assert app.do("terms")["needed"] is True


# Glass box: what's kept, and how the document is read.


def test_every_acceptance_is_kept_with_its_time(app: App) -> None:
    app.do("terms_accept", version=terms.current().version)
    app.at("2026-10-20T10:00").do("terms_accept", version=terms.current().version)
    (row,) = [r for r in app.table("kv") if r["key"] == "terms_accepted"]
    assert [a["at"] for a in json.loads(row["value"])] == ["2026-10-19T13:00Z", "2026-10-20T14:00Z"]


def test_the_document_names_its_version_and_what_changed() -> None:
    now = terms.current()
    assert now.version == "2026-11-09.2"
    assert now.changes and now.changes[0].startswith("Section 3 says plainly")
    assert terms.changes_in("# T\n\n## What changed\n\n- one\n- two\n\n## 1. Next\n\n- not this") == ("one", "two")


def test_the_copy_on_github_is_the_one_in_the_app() -> None:
    assert (REPO / "TERMS.md").read_text() == terms.TEXT.read_text()


def test_the_terms_say_what_you_decided() -> None:
    text = terms.current().text
    for said in (
        "13 or older",
        "Ruben Hayrapetyan",
        "friday-scheduler.com/contact.html",
        "friday_support@friday-scheduler.com",
        "PolyForm Noncommercial License 1.0.0",
        "**You may not sell Friday, or anything built from its code",
        "A version you have already downloaded keeps working for free",
        "your computer's internet (IP) address",
        "## 7. Not professional advice",
        "## 12. Indemnity",
        "## 13. Ending your license",
        "free for me to use in Friday",
    ):
        assert said in text, said
    for gone in (
        "arbitration",
        "State of New York",
        "courts located",
        "Law and disputes",
        "Affero",
        "0.3.1",
        "The only thing Friday sends",
    ):
        assert gone not in text, gone
    assert "I take no responsibility for the code" in text


def test_the_license_is_polyform_noncommercial() -> None:
    license = (REPO / "LICENSE").read_text()
    assert license.startswith("Required Notice: Copyright 2026 Ruben Hayrapetyan")
    assert "# PolyForm Noncommercial License 1.0.0" in license and "Affero" not in license
    assert "may also use, license and sell it commercially" in (REPO / "CONTRIBUTING.md").read_text()


# The whole system: the server, as the web app asks.


def test_through_the_server(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from friday.server.app import create_app

    app = new_app(tmp_path)
    served = create_app(tmp_path / "friday.db", clock=lambda: app.now_utc, background=False, plugin_dir=tmp_path)
    with TestClient(served, base_url="http://127.0.0.1:8765") as web:
        shown = web.get("/api/q/terms").json()
        assert shown["needed"] is True
        accepted = web.post("/api/c/terms_accept", json={"version": shown["version"]})
        assert accepted.status_code == 200, accepted.text
        assert web.get("/api/q/terms").json()["needed"] is False
