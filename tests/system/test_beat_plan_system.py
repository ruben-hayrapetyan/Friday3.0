"""Work your plans show late that you finish on time, the whole system at once (2 Nov; glass box, black box and full
system tests for every feature): a real `fridayd serve` in a folder of its own on the real clock, its worker
replanning, and only HTTP between it and the test, as the app sends it; then the CLI against the same server.

Three things due in two hours that need 2½ each, with the two hours busy, so every plan shows them late; you worked
each for its 2½ hours from 12:30am (an 11:30pm bedtime and its hour of margin) on three nights before today, and
finish them now, on time."""

import json
import os
import socket
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

REPO = Path(__file__).resolve().parents[2]
TZ = "America/New_York"
SLEEP = {d: {"bedtime": "23:30", "wake": "07:30", "margin_min": 60} for d in ("mon", "tue", "wed", "thu", "fri",
                                                                            "sat", "sun")}  # fmt: skip
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Friday:
    def __init__(self, folder: Path) -> None:
        self.port, self.folder = free_port(), folder
        self.env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY") and k != "FRIDAY_AI_KEY"}
        self.env |= {"FRIDAY_DATA_DIR": str(folder / "data"), "FRIDAY_CONFIG": str(folder / "config" / "friday.toml"),
                     "FRIDAY_CLAUDE": "none", "OLLAMA_HOST": "127.0.0.1:9"}  # fmt: skip
        (folder / "config").mkdir(parents=True)
        fridayd = [sys.executable, "-m", "friday.server.main", "--data-dir", str(folder / "data")]
        subprocess.run([*fridayd, "init", "--timezone", TZ], cwd=REPO, env=self.env, check=True, capture_output=True)
        self.log = (folder / "server.out").open("w")
        self.process = subprocess.Popen([*fridayd, "serve", "--port", str(self.port)], cwd=REPO, env=self.env,
                                        stdout=self.log, stderr=subprocess.STDOUT)  # fmt: skip
        self.http = httpx.Client(base_url=f"http://127.0.0.1:{self.port}", timeout=60)
        for _ in range(240):
            try:
                if self.http.get("/api/q/status").status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        raise RuntimeError("fridayd didn't start: " + (folder / "server.out").read_text()[-2000:])

    def q(self, verb: str, /, **params: Any) -> Any:
        answer = self.http.get(f"/api/q/{verb}", params=params)
        assert answer.status_code == 200, answer.text
        return answer.json()

    def c(self, verb: str, /, **body: Any) -> Any:
        answer = self.http.post(f"/api/c/{verb}", json=body)
        assert answer.status_code == 200, answer.text
        return answer.json()["result"]

    def until(self, check: Any, timeout: float = 90) -> Any:
        """What `check()` returns once it's truthy, the worker replanning meanwhile."""
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


def local(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M")


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("beat-plan"))
    yield server
    server.stop()


@pytest.fixture(scope="module")
def evenings(friday: Friday) -> list[str]:
    """Three things shown late, each worked on past 12:30am on a night before today and finished now: the evenings
    worked into."""
    friday.c("settings_set", key="sleep", value=SLEEP)
    now = datetime.now(ZoneInfo(TZ)).replace(second=0, microsecond=0)
    due = local(now + timedelta(hours=2))
    friday.c("add", title="busy", when="fixed", start=local(now), end=due)
    items = [
        friday.c("add", title=f"problem set {n}", preset="Assignment", duration_min=150, firmness="hard", due=due)[
            "item"
        ]["id"]
        for n in (1, 2, 3)
    ]
    friday.c("replan")
    late = friday.until(lambda: {i["item_id"] for i in friday.q("status")["late_items"]} >= set(items))
    assert late
    out = []
    for n, item in enumerate(items):
        evening = (now - timedelta(days=4 - n)).date()  # nights well before today, whatever the hour now
        morning = datetime.combine(evening + timedelta(days=1), datetime.min.time(), ZoneInfo(TZ))
        start, end = morning + timedelta(minutes=30), morning + timedelta(hours=3)  # 12:30–3am: 2½ hours
        friday.c("log", id=item, start=local(start), end=local(end))
        friday.c("done", id=item)
        out.append(WEEKDAYS[evening.weekday()])
    return out


def test_1_friday_says_how_you_beat_its_plans(friday: Friday, evenings: list[str]) -> None:
    out = friday.q("beat_plan")
    assert (out["on_time"], out["late"], out["counts"]) == (3, 0, {"nights": 3})
    assert out["said"][1] == "3 by working later at night"
    assert all(f["late_hours"] > 0 for f in out["finishes"])


def test_2_the_inbox_asks_to_plan_later_nights(friday: Friday, evenings: list[str]) -> None:
    decisions = {d["key"]: d for d in friday.q("status")["decisions"]}
    asked = decisions["learned:beat:nights"]
    assert asked["kind"] == "learned" and asked["options"][0]["label"] == "Plan up to 2h 30m later on those nights"


def test_3_the_cli_reads_the_same_from_the_server(friday: Friday, evenings: list[str]) -> None:
    env = friday.env | {"FRIDAY_SERVER": f"http://127.0.0.1:{friday.port}", "COLUMNS": "400"}
    run = subprocess.run([sys.executable, "-m", "friday.cli.main", "beat-plan", "--json"], cwd=REPO, env=env,
                         capture_output=True, text=True, timeout=60)  # fmt: skip
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout)
    assert out["counts"] == {"nights": 3} and out["asking"] == [
        "You finish work Friday showed late by working later at night"
    ]


def test_4_yes_makes_those_nights_later_and_isnt_asked_again(friday: Friday, evenings: list[str]) -> None:
    assert friday.c("conflict_resolve", key="beat:nights", option="later")["message"].startswith("Later nights on")
    sleep = friday.q("settings")["sleep"]
    assert {d: sleep[d]["margin_min"] for d in WEEKDAYS} == {d: 210 if d in evenings else 60 for d in WEEKDAYS}
    assert "learned:beat:nights" not in {d["key"] for d in friday.q("status")["decisions"]}
