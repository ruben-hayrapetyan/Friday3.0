"""The mail log and "Read it anyway", the whole pipeline (tests/features.toml: mail). `fridayd demo` serves the sample
term in a folder of its own, with its stand-in Gmail and AI: the server's job loop reads the mail (some read, some
skipped as bulk), `mail_log` shows each and why, and `mail_retry` is sent over HTTP as Settings → Integrations' mail
log sends it; the next reading of the mail reads that message again, and the log says so."""

import os
import subprocess
import sys
import time
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from friday.sim.history import ZONE as SAMPLE_ZONE
from tests.system.test_beat_plan_system import REPO, free_port

WAIT = 240


def to_tuesday_2pm() -> int:
    """Minutes from now to this week's Tuesday at 2pm in Alex's zone: the sample's mail is due that Thursday and Friday
    (sim/sample.py mailbox), so run from Friday on, A5 was already past and rightly not suggested, and this file failed
    every weekend whatever the code (27 Nov). The term is Alex's week; the test runs in the middle of it."""
    zone = ZoneInfo(SAMPLE_ZONE.key)
    now = datetime.now(zone)
    tuesday = (now - timedelta(days=now.weekday() - 1)).replace(hour=14, minute=0, second=0, microsecond=0)
    return round((tuesday - now).total_seconds() / 60)


class Demo:
    def __init__(self, folder: Path) -> None:
        self.port, self.folder = free_port(), folder
        env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY") and k != "FRIDAY_AI_KEY"}
        env |= {"FRIDAY_CONFIG": str(folder / "none" / "friday.toml"), "FRIDAY_CLAUDE": "none",
                "OLLAMA_HOST": "127.0.0.1:9"}  # fmt: skip
        self.log = (folder / "server.out").open("w")
        command = [sys.executable, "-m", "friday.server.main", "--data-dir", str(folder / "data"), "demo", "--port",
                   str(self.port), "--shift-minutes", str(to_tuesday_2pm())]  # fmt: skip
        self.process = subprocess.Popen(command, cwd=REPO, env=env, stdout=self.log, stderr=subprocess.STDOUT)
        self.http = httpx.Client(base_url=f"http://127.0.0.1:{self.port}", timeout=300)
        self.until(self.up, 120)

    def up(self) -> bool:
        try:
            return self.http.get("/api/q/status").status_code == 200
        except httpx.HTTPError:
            return False

    def q(self, verb: str, /, **params: Any) -> Any:
        answer = self.http.get(f"/api/q/{verb}", params=params)
        assert answer.status_code == 200, answer.text
        return answer.json()

    def c(self, verb: str, /, **body: Any) -> Any:
        answer = self.http.post(f"/api/c/{verb}", json=body)
        assert answer.status_code == 200, answer.text
        return answer.json()["result"]

    def until(self, check: Any, timeout: float = WAIT) -> Any:
        end = time.time() + timeout
        while time.time() < end:
            found = check()
            if found:
                return found
            time.sleep(0.5)
        raise TimeoutError("waited too long: " + (self.folder / "server.out").read_text()[-2000:])

    def stop(self) -> None:
        self.process.terminate()
        self.process.wait(15)
        self.log.close()


@pytest.fixture(scope="module")
def demo(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Demo]:
    server = Demo(tmp_path_factory.mktemp("mail"))
    server.until(lambda: len(server.q("mail_log")) >= 10)  # the sample's mail, read by the job loop
    yield server
    server.stop()


def mail(demo: Demo) -> dict[str, dict[str, Any]]:
    return {m["subject"]: m for m in demo.q("mail_log")}


def refused(demo: Demo, **body: Any) -> str:
    answer = demo.http.post("/api/c/mail_retry", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()["message"].removeprefix("id: ")


ADMISSIONS = "Your future is waiting"  # bulk, no keyword: skipped
NOTHING = "[CS 1110] Prelim 1, Support Sessions, and A4"  # read, nothing in it to plan
FOUND = "[CS 1110] New Assignment Released"  # read, A5 found


def test_the_log_says_what_was_read_and_skipped_and_why(demo: Demo) -> None:
    log = mail(demo)
    assert log[ADMISSIONS]["status"] == "skipped" and log[ADMISSIONS]["why"].startswith("Bulk mail")
    assert log[ADMISSIONS]["sender"] == "Admissions <hello@college.edu>"
    assert (log[NOTHING]["status"], log[NOTHING]["found"]) == ("read", 0)
    assert (log[FOUND]["status"], log[FOUND]["found"]) == ("read", 1)
    assert any(s["input"].get("title") == "CS 1110 A5" for s in demo.q("inbox")["suggestions"])


def test_the_log_is_newest_first_and_as_long_as_asked(demo: Demo) -> None:
    every = demo.q("mail_log")
    assert [m["id"] for m in every] == sorted((m["id"] for m in every), reverse=True)
    assert [m["id"] for m in demo.q("mail_log", limit=2)] == [m["id"] for m in every[:2]]
    assert demo.http.get("/api/q/mail_log", params={"limit": 0}).status_code == 422


def test_read_it_anyway_reads_a_skipped_message_with_its_pdfs_on_the_next_sync(demo: Demo) -> None:
    skipped = mail(demo)[ADMISSIONS]
    said = demo.c("mail_retry", id=skipped["id"])
    assert said["message"] == "It's read on the next sync, with its PDFs"
    now = mail(demo)[ADMISSIONS]
    assert now["status"] == "skipped" and "PDFs" in (now["why"] or "")  # waiting for the next reading of the mail
    demo.c("sync_now")
    read = demo.until(lambda: (m := mail(demo)[ADMISSIONS])["status"] == "read" and m)
    assert read["id"] == skipped["id"] and read["why"] is None  # the same message, read by the AI this time


def test_read_it_again_reads_one_with_nothing_found_on_the_next_sync(demo: Demo) -> None:
    nothing = mail(demo)[NOTHING]
    assert demo.c("mail_retry", id=nothing["id"])["message"] == "It's read on the next sync"
    assert mail(demo)[NOTHING]["status"] == "waiting"
    demo.c("sync_now")
    again = demo.until(lambda: (m := mail(demo)[NOTHING])["status"] == "read" and m)
    assert again["found"] == 0


def test_one_that_found_something_cant_be_read_again(demo: Demo) -> None:
    found = mail(demo)[FOUND]
    said = refused(demo, id=found["id"])
    assert said == "only a skipped or failed message, or one with nothing found, can be read again"
    assert mail(demo)[FOUND]["status"] == "read"


def test_only_mail_can_be_read_again(demo: Demo) -> None:
    assert refused(demo, id=99999) == "only a message from your mail can be read again"
    demo.c("document_add", name="notes.txt", content="Nothing due here.")
    upload = next(d for d in demo.q("documents") if d["name"] == "notes.txt")
    assert refused(demo, id=upload["id"]) == "only a message from your mail can be read again"
