"""While your AI thinks, Friday keeps working (3 Nov, the CS 2112 UI lecture: past ten seconds "the app must support
parallel activities"). A real `fridayd serve` asking the stand-in model on this Mac (tests/fake_ollama.py), which holds
its answer: meanwhile the page's other requests answer at once; stopping the wait (the app's Stop button aborts its
request) leaves the server well; and the answer, when it comes, is whole."""

import json
import threading
import time
from collections.abc import Iterator

import httpx
import pytest

from tests.system.test_ai_system import Friday, Ollama

PROPOSES = {"reply": "Moved it.", "actions": [{"sentence": "No mornings", "command": "rule_add",
                                               "input": {"text": "no work before 10am"}}]}  # fmt: skip


@pytest.fixture(scope="module")
def system(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Friday, Ollama]]:
    ollama = Ollama(["llama3.2:3b"])
    friday = Friday(tmp_path_factory.mktemp("meanwhile"), ollama)
    friday.c("local_model_use", name="llama3.2:3b")
    ollama.tell("answer " + json.dumps(PROPOSES))
    yield friday, ollama
    friday.stop()
    ollama.stop()


def asking(friday: Friday, out: dict, timeout: float = 60) -> threading.Thread:
    """Ask in the background, as the page does, keeping what comes back (or that it was given up on) in `out`."""

    def ask() -> None:
        try:
            with httpx.Client(base_url=str(friday.http.base_url), timeout=timeout) as http:
                out["answer"] = http.post("/api/c/ask_claude", json={"text": "no mornings", "purpose": "rule"})
        except httpx.TimeoutException:
            out["stopped"] = True

    thread = threading.Thread(target=ask)
    thread.start()
    return thread


def test_while_the_ai_thinks_everything_else_answers_at_once(system: tuple[Friday, Ollama]) -> None:
    friday, ollama = system
    ollama.tell("think")
    out: dict = {}
    thread = asking(friday, out)
    time.sleep(0.5)
    assert thread.is_alive()  # still thinking
    began = time.perf_counter()
    assert friday.q("status")["timer"] is None
    task = friday.c("add", title="Problem set", duration_min=60, due="2026-12-01T17:00")["item"]
    friday.c("start", id=task["id"])
    friday.c("stop", id=task["id"])
    assert time.perf_counter() - began < 5  # not held up by the question
    ollama.tell("answered")
    thread.join(30)
    answer = out["answer"]
    assert answer.status_code == 200 and answer.json()["result"]["reply"] == "Moved it."


def test_stopping_the_wait_leaves_friday_well_and_changes_nothing(system: tuple[Friday, Ollama]) -> None:
    friday, ollama = system
    rules_before = friday.q("rules")
    ollama.tell("think")
    out: dict = {}
    thread = asking(friday, out, timeout=1)  # the page gives up, as Stop does
    thread.join(10)
    assert out.get("stopped")
    ollama.tell("answered")
    time.sleep(0.5)
    assert friday.q("rules") == rules_before  # an answer nobody waited for applies nothing
    out2: dict = {}
    asking(friday, out2).join(30)
    assert out2["answer"].status_code == 200  # and the next question is answered as usual
