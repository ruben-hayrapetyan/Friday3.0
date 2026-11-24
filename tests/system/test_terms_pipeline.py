"""Terms (tests/features.toml: terms), the whole pipeline (24 Nov, the user: "go through every single functionality of
the app and build an extensive test suite"): a real `fridayd serve`, the terms read and accepted over HTTP as the app's
locked page does, and what that unlocks read back. The tests run in order on one server: first not yet accepted."""

from collections.abc import Iterator

import pytest

from tests.system.test_beat_plan_system import Friday


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("terms"))
    yield server
    server.stop()


def test_1_a_new_friday_asks_for_the_terms_and_says_what_changed(friday: Friday) -> None:
    terms = friday.q("terms")
    assert terms["needed"] is True and terms["accepted"] is None
    assert terms["version"] and f"Version: {terms['version']}" in terms["text"]
    assert terms["text"].startswith("# Friday's terms")
    assert terms["changes"] and all(isinstance(c, str) and c for c in terms["changes"])


def test_2_terms_changed_while_reading_are_refused_and_still_asked(friday: Friday) -> None:
    answer = friday.http.post("/api/c/terms_accept", json={"version": "2000-01-01.1"})
    assert answer.status_code == 422
    assert answer.json() == {
        "field": "version",
        "message": "version: These terms changed while you were reading them: read the new ones first",
    }
    assert friday.q("terms")["needed"] is True


def test_3_accepting_needs_the_version_read(friday: Friday) -> None:
    answer = friday.http.post("/api/c/terms_accept", json={})
    assert answer.status_code == 422 and answer.json()["detail"][0]["loc"] == ["body", "version"]
    assert friday.q("terms")["accepted"] is None


def test_4_an_assistant_can_read_the_terms_but_never_accept_them(friday: Friday) -> None:
    token = friday.c("token_add", name="helper", scope="read-write")["token"]
    sent = {"authorization": f"Bearer {token}"}
    read = friday.http.get("/api/q/terms", headers=sent)
    assert read.status_code == 200 and read.json()["needed"] is True
    answer = friday.http.post("/api/c/terms_accept", json={"version": read.json()["version"]}, headers=sent)
    assert answer.status_code == 422
    assert "Only you can do that (terms_accept), not an assistant" in answer.json()["message"]
    assert friday.q("terms")["needed"] is True  # nothing was kept


def test_5_accepting_the_version_read_unlocks_friday(friday: Friday) -> None:
    version = friday.q("terms")["version"]
    assert friday.c("terms_accept", version=version)["message"] == "Thanks: you've accepted Friday's terms"
    after = friday.q("terms")
    assert (after["needed"], after["accepted"], after["version"]) == (False, version, version)


def test_6_accepting_again_keeps_them_accepted(friday: Friday) -> None:
    version = friday.q("terms")["version"]
    friday.c("terms_accept", version=version)
    assert friday.q("terms")["needed"] is False
    wrong = friday.http.post("/api/c/terms_accept", json={"version": "nope"})
    assert wrong.status_code == 422
    after = friday.q("terms")  # a refused acceptance takes nothing back
    assert (after["needed"], after["accepted"]) == (False, version)
