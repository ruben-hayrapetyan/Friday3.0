"""The hosted Friday's test profiles, the whole system (HOSTED.md H73–H76): `python -m friday.sim.profiles build`
writes a fresh worker's and a lived-in shift worker's data folders, and `fridayd demo --case` serves each over HTTP
the way S1 will on the server: their own calendars by name, their plan, a sync through the stand-in Google, and the
page marked as sample data."""

import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from friday.sim.people import PEOPLE
from friday.sim.profiles import LIVED
from tests.system.test_beat_plan_system import REPO, free_port

FRESH = "leo"  # a very light project manager, just set up
LIVED_IN = "ivo"  # a barista with three weeks lived


def env(folder: Path) -> dict[str, str]:
    out = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY") and k != "FRIDAY_AI_KEY"}
    return out | {"FRIDAY_CONFIG": str(folder / "none" / "friday.toml"), "FRIDAY_CLAUDE": "none",
                  "OLLAMA_HOST": "127.0.0.1:9", "PYTHONPATH": f"{REPO / 'src'}:{REPO}"}  # fmt: skip


class Served:
    def __init__(self, folder: Path, key: str) -> None:
        self.port = free_port()
        self.log = (folder / f"{key}.out").open("w")
        command = [sys.executable, "-m", "friday.server.main", "--data-dir", str(folder / key), "demo", "--case", key,
                   "--port", str(self.port)]  # fmt: skip
        self.process = subprocess.Popen(command, cwd=REPO, env=env(folder), stdout=self.log, stderr=subprocess.STDOUT)
        self.http = httpx.Client(base_url=f"http://127.0.0.1:{self.port}", timeout=60)
        for _ in range(240):
            try:
                if self.http.get("/api/q/status").status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        raise RuntimeError("the demo didn't start: " + (folder / f"{key}.out").read_text()[-2000:])

    def q(self, verb: str, /, **params: Any) -> Any:
        answer = self.http.get(f"/api/q/{verb}", params=params)
        assert answer.status_code == 200, answer.text
        return answer.json()

    def c(self, verb: str, /, **body: Any) -> Any:
        answer = self.http.post(f"/api/c/{verb}", json=body)
        assert answer.status_code == 200, answer.text
        return answer.json()["result"]

    def stop(self) -> None:
        self.process.terminate()
        self.process.wait(15)
        self.log.close()


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("profiles")
    command = [sys.executable, "-m", "friday.sim.profiles", "build", str(folder), "--only", FRESH, LIVED_IN]
    done = subprocess.run(command, cwd=REPO, env=env(folder), capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-2000:]
    return folder


@pytest.fixture(scope="module")
def fresh(built: Path) -> Iterator[Served]:
    served = Served(built, FRESH)
    yield served
    served.stop()


@pytest.fixture(scope="module")
def lived(built: Path) -> Iterator[Served]:
    served = Served(built, LIVED_IN)
    yield served
    served.stop()


def test_the_builder_writes_one_data_folder_per_profile_and_leaves_an_existing_one_alone(built: Path) -> None:
    assert FRESH not in LIVED and LIVED_IN in LIVED
    for key in (FRESH, LIVED_IN):
        assert (built / key / "friday.db").exists()
    before = (built / FRESH / "friday.db").stat().st_mtime
    again = subprocess.run([sys.executable, "-m", "friday.sim.profiles", "build", str(built), "--only", FRESH],
                           cwd=REPO, env=env(built), capture_output=True, text=True, timeout=120)  # fmt: skip
    assert again.returncode == 0 and "0 built" in again.stderr
    assert (built / FRESH / "friday.db").stat().st_mtime == before


def test_a_served_profile_has_its_own_calendars_and_meetings_and_a_plan(fresh: Served) -> None:
    leo = PEOPLE[FRESH]
    plan = fresh.q("plan")
    assert plan["blocks"], "nothing planned"
    calendars = {f["calendar"] for f in plan["fixed"]}
    assert "Work" in calendars  # the worker's own name for it, not a student's
    series = {s["title"] for s in fresh.q("series_list")}
    assert {m.title for m in leo.meetings} <= series


def test_a_served_profile_syncs_through_its_stand_in_google_and_mail_without_problems(fresh: Served) -> None:
    leo = PEOPLE[FRESH]
    fresh.c("sync_now")
    for _ in range(120):
        accounts = [a["email"] for a in fresh.q("google_connect_status")["accounts"]]
        if accounts:
            break
        time.sleep(0.5)
    assert accounts  # the stand-in Google answers (it lists its calendars by id, as for a Cornell student)
    time.sleep(3)  # a sync's errors land in status
    assert fresh.q("status")["problems"] == []
    subjects = {m["subject"] for m in fresh.q("mail_log")}
    assert {letter.subject for letter in leo.letters} <= subjects


def test_a_lived_profile_has_weeks_of_work_done_and_says_it_is_sample_data(lived: Served) -> None:
    done = lived.q("items", status="done")
    assert done, "three weeks lived, nothing done"
    assert lived.q("status")["demo"] is True
