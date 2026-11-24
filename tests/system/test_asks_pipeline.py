"""Ask me later, the whole pipeline (tests/features.toml: asks; 24 Nov, the user: "go through every single
functionality of the app and build an extensive test suite"): "Not now" on one of Friday's questions in the Inbox,
sent over HTTP to a real `fridayd serve` exactly as AskPane sends it, kept on the server with what it was based on
(so the Mac and your phone count the same Inbox), and read back the way the Inbox reads it (`asks_later`)."""

import subprocess
import sys
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from tests.system.test_beat_plan_system import REPO, Friday, free_port


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("asks"))
    yield server
    server.stop()


def later(friday: Friday) -> dict[str, str]:
    return friday.q("asks_later")["later"]


def refused(friday: Friday, **body: Any) -> dict[str, Any]:
    answer = friday.http.post("/api/c/ask_later", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()


def test_nothing_is_set_aside_at_first(friday: Friday) -> None:
    assert later(friday) == {}


def test_not_now_keeps_the_question_with_its_evidence(friday: Friday) -> None:
    said = friday.c("ask_later", key="durations", evidence="12")
    assert said["message"] == "Not now: Friday asks again once it knows more"
    assert later(friday) == {"durations": "12"}


def test_another_question_is_kept_beside_it(friday: Friday) -> None:
    friday.c("ask_later", key="meal-length-lunch", evidence="45")
    assert later(friday) == {"durations": "12", "meal-length-lunch": "45"}


def test_not_now_again_with_more_evidence_replaces_what_it_had(friday: Friday) -> None:
    friday.c("ask_later", key="durations", evidence="15")  # asked again once there were 15 timed, and set aside again
    assert later(friday) == {"durations": "15", "meal-length-lunch": "45"}


def test_a_question_with_no_key_is_refused_and_nothing_changes(friday: Friday) -> None:
    for key in ("", "   "):
        out = refused(friday, key=key, evidence="1")
        assert out["field"] == "key" and out["message"].endswith("say which question")
    assert later(friday) == {"durations": "15", "meal-length-lunch": "45"}


def test_a_question_without_evidence_is_refused(friday: Friday) -> None:
    answer = friday.http.post("/api/c/ask_later", json={"key": "weights"})
    assert answer.status_code == 422 and "evidence" in answer.text
    assert "weights" not in later(friday)


def test_undo_takes_the_last_not_now_back(friday: Friday) -> None:
    asked = {"key": "rule:no-work-after-10pm", "evidence": "no-work-after-10pm"}
    sent = friday.http.post("/api/c/ask_later", json=asked)
    assert sent.status_code == 200 and "rule:no-work-after-10pm" in later(friday)
    friday.c("undo", command_id=sent.json()["command_id"])
    assert later(friday) == {"durations": "15", "meal-length-lunch": "45"}


def serve_again(first: Friday) -> Friday:
    """The same data folder served again by a new `fridayd serve`."""
    again = Friday.__new__(Friday)
    again.__dict__.update(first.__dict__)
    again.port, again.log = free_port(), (first.folder / "server-again.out").open("w")
    fridayd = [sys.executable, "-m", "friday.server.main", "--data-dir", str(first.folder / "data")]
    again.process = subprocess.Popen([*fridayd, "serve", "--port", str(again.port)], cwd=REPO, env=first.env,
                                     stdout=again.log, stderr=subprocess.STDOUT)  # fmt: skip
    again.http = httpx.Client(base_url=f"http://127.0.0.1:{again.port}", timeout=300)

    def up() -> bool:
        try:
            return again.http.get("/api/q/status").status_code == 200
        except httpx.HTTPError:
            return False

    again.until(up, 300)
    return again


def test_kept_on_the_server_across_a_restart(tmp_path_factory: pytest.TempPathFactory) -> None:
    first = Friday(tmp_path_factory.mktemp("asks-restart"))
    try:
        first.c("ask_later", key="compare", evidence="3")
    finally:
        first.stop()
    again = serve_again(first)  # what you set aside is the server's, not the page's: the Mac and phone count the same
    try:
        assert later(again) == {"compare": "3"}
    finally:
        again.stop()
