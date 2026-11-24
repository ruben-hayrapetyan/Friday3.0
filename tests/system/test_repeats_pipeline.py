"""Repeating calendar events brought in (tests/features.toml: repeats: calendar_repeats, repeats_import,
repeats_leave_out), the whole pipeline (24 Nov, the user: "go through every single functionality of the app and build
an extensive test suite"): `fridayd demo` serves the sample term with its stand-in Google calendars (the only way a
server reads Google without your account); two of them switched on over HTTP as Settings → Calendars does, the
worker's sync reads them, and each repeating event waits as one repeat until it's brought in or left out, as the
Inbox and Settings → Repeating do. The tests run in order on one server."""

import os
import subprocess
import sys
import time
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from tests.system.test_beat_plan_system import REPO, TZ, Friday, free_port, local

CLASSES = {  # the sample term's classes on "4. School" (sim/sample.py): kind, pattern, tag
    "CHEM 2090, Lecture": "Every Mon, Wed and Fri, 12:20pm–1:10pm",
    "CHEM 2091, Laboratory": "Every Monday, 1:25pm–4:25pm",
    "CS 1110, Discussion": "Every Wednesday, 1:25pm–2:15pm",
    "CS 1110, Lecture": "Every Tue and Thu, 11:15am–12:05pm",
    "ENGRG 1050, Seminar": "Every Thursday, 1:25pm–2:15pm",
    "MATH 1920, Discussion": "Every Tuesday, 2:30pm–3:20pm",
    "MATH 1920, Lecture": "Every Mon, Wed and Fri, 11:15am–12:05pm",
    "PHYS 1110, Laboratory": "Every Tuesday, 12:20pm–2:15pm",
    "PHYS 1110, Lecture": "Every Friday, 2:30pm–3:20pm",
}
PERSONAL = {"Call home": "Every Sunday, 7pm–7:30pm", "Gym": "Every Mon, Wed and Fri, 7am–8am",
            "Sam's Birthday": "Yearly, all day"}  # fmt: skip
WEEKDAY = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}


class Demo(Friday):
    """`fridayd demo` in a folder of its own: the sample term, its Google, Gmail and AI standing in for yours."""

    def __init__(self, folder: Path) -> None:
        self.port, self.folder = free_port(), folder
        self.env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY") and k != "FRIDAY_AI_KEY"}
        self.env |= {"FRIDAY_CLAUDE": "none", "OLLAMA_HOST": "127.0.0.1:9"}
        self.log = (folder / "server.out").open("w")
        command = [sys.executable, "-m", "friday.server.main", "--data-dir", str(folder / "data"), "demo", "--port",
                   str(self.port)]  # fmt: skip
        self.process = subprocess.Popen(command, cwd=REPO, env=self.env, stdout=self.log, stderr=subprocess.STDOUT)
        self.http = httpx.Client(base_url=f"http://127.0.0.1:{self.port}", timeout=300)
        for _ in range(480):
            try:
                if self.http.get("/api/q/status").status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        raise RuntimeError("fridayd demo didn't start: " + (folder / "server.out").read_text()[-2000:])


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Demo]:
    server = Demo(tmp_path_factory.mktemp("repeats"))
    server.until(lambda: server.q("google_calendars"), timeout=120)  # the first sync has listed the calendars
    yield server
    server.stop()


def waiting(friday: Friday) -> dict[str, dict[str, Any]]:
    return {r["title"]: r for r in friday.q("calendar_repeats")}


def refused(friday: Friday, command: str, /, **body: Any) -> dict[str, Any]:
    answer = friday.http.post(f"/api/c/{command}", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()


def events(friday: Friday, title: str) -> list[dict[str, Any]]:
    """`title`'s times in the next five weeks, as the plan draws them."""
    now = datetime.now(ZoneInfo(TZ))
    plan = friday.q("plan", start=local(now - timedelta(days=1)), end=local(now + timedelta(days=35)))
    return [f for f in plan["fixed"] if f["title"] == title]


def test_1_nothing_waits_from_a_calendar_not_read(friday: Demo) -> None:
    assert friday.q("calendar_repeats") == []
    calendars = {c["id"]: c for c in friday.q("google_calendars")}
    assert calendars["school@g"]["on"] is False and calendars["personal@g"]["on"] is False


def test_2_each_repeating_class_waits_as_one_repeat_with_its_days_times_and_tag(friday: Demo) -> None:
    assert friday.c("calendar_set", id="school@g", on=True)["message"] == "Reading 4. School"
    found = friday.until(lambda: len(waiting(friday)) == len(CLASSES) and waiting(friday), timeout=150)
    assert {t: r["pattern"] for t, r in found.items()} == CLASSES
    for title, r in found.items():
        assert (r["kind"], r["calendar"], r["batch"].startswith("repeat:")) == ("Class", "4. School", True)
        assert r["tag"] == title.split(",")[0]  # "MATH 1920, Lecture" goes under MATH 1920
        assert r["count"] >= 1 and r["first"] >= (date.today() - timedelta(days=1)).isoformat()
        days = r["pattern"].removeprefix("Every ").rsplit(", ", 1)[0].replace(",", " ").replace(" and ", " ").split()
        weekdays = {WEEKDAY[d[:3]] for d in days if d[:3] in WEEKDAY}
        assert date.fromisoformat(r["first"][:10]).weekday() in weekdays  # its first time is on one of its days
    listed = friday.q("calendar_repeats")
    assert listed == sorted(listed, key=lambda r: (r["calendar"], r["title"]))


def test_3_repeating_events_and_a_yearly_all_day_one_from_another_calendar(friday: Demo) -> None:
    friday.c("calendar_set", id="personal@g", on=True)
    found = friday.until(lambda: len(waiting(friday)) == len(CLASSES) + len(PERSONAL) and waiting(friday), timeout=150)
    assert {t: found[t]["pattern"] for t in PERSONAL} == PERSONAL
    assert {found[t]["calendar"] for t in PERSONAL} == {"3. Personal"}
    assert found["Sam's Birthday"]["count"] == 1 and found["Gym"]["tag"] is None
    assert events(friday, "MATH 1920, Lecture") == []  # nothing waiting is planned around yet


def test_4_a_class_brought_in_is_one_repeat_with_your_tag(friday: Demo) -> None:
    batch = waiting(friday)["MATH 1920, Lecture"]["batch"]
    count = waiting(friday)["MATH 1920, Lecture"]["count"]
    friday.c("area_add", name="MATH 1920")
    said = friday.c("repeats_import", repeats=[{"batch": batch, "area": "MATH 1920"}])
    assert said["message"] == "Imported 1 repeat"
    assert "MATH 1920, Lecture" not in waiting(friday)
    times = events(friday, "MATH 1920, Lecture")
    assert len(times) >= count and {t["area"] for t in times} == {"MATH 1920"}
    assert {datetime.fromisoformat(t["start"]).weekday() for t in times} <= {0, 2, 4}
    assert {t["start"][11:] for t in times} == {"11:15"} and {t["end"][11:] for t in times} == {"12:05"}
    series = [s for s in friday.q("series_list") if s["title"] == "MATH 1920, Lecture"]
    assert len(series) == 1 and series[0]["area"] == "MATH 1920"  # one repeat, not its times one by one


def test_5_several_at_once_each_with_the_kind_you_pick(friday: Demo) -> None:
    found = waiting(friday)
    picks = [{"batch": found["Gym"]["batch"], "kind": "Meeting"}, {"batch": found["CS 1110, Lecture"]["batch"]}]
    assert friday.c("repeats_import", repeats=picks)["message"] == "Imported 2 repeats"
    assert not {"Gym", "CS 1110, Lecture"} & set(waiting(friday))
    gym, cs = events(friday, "Gym"), events(friday, "CS 1110, Lecture")
    assert gym and {g["preset"] for g in gym} == {"Meeting"}
    assert cs and {c["preset"] for c in cs} == {"Class"}  # the kind Friday read, when you don't pick one
    assert {c["area"] for c in cs} == {None}  # no CS 1110 tag yet: none made up


def test_6_a_repeat_left_out_isnt_planned_around_now_or_later(friday: Demo) -> None:
    batch = waiting(friday)["Call home"]["batch"]
    said = friday.c("repeats_leave_out", batch=batch)
    assert said["message"] == "Left out Call home, its later weeks too"
    assert "Call home" not in waiting(friday) and events(friday, "Call home") == []
    friday.c("sync_now")  # the calendar read again: its weeks are still left out
    time.sleep(35)
    assert "Call home" not in waiting(friday) and events(friday, "Call home") == []
    assert "PHYS 1110, Lecture" in waiting(friday)  # what you didn't answer still waits


def test_7_a_repeat_no_longer_waiting_is_said_so(friday: Demo) -> None:
    gone = {"field": "repeats", "message": "repeats: that repeating event isn't waiting any more; sync and look again"}
    imported = "repeat:math"
    assert refused(friday, "repeats_import", repeats=[{"batch": imported}]) == gone
    assert refused(friday, "repeats_import", repeats=[{"batch": "repeat:nothing"}]) == gone
    left = {"field": "batch", "message": "batch: that repeating event isn't waiting any more; sync and look again"}
    assert refused(friday, "repeats_leave_out", batch="repeat:home") == left
    assert refused(friday, "repeats_leave_out", batch=imported) == left
    assert len(series_named(friday, "MATH 1920, Lecture")) == 1  # nothing was brought in twice


def test_8_an_import_names_at_least_one_repeat(friday: Demo) -> None:
    before = waiting(friday)
    said = refused(friday, "repeats_import", repeats=[])
    assert said["detail"][0]["loc"] == ["body", "repeats"]
    picks = [{"batch": before["PHYS 1110, Lecture"]["batch"]}, {"batch": "repeat:nothing"}]
    refused(friday, "repeats_import", repeats=picks)  # one gone: none of them is brought in
    assert waiting(friday) == before


def series_named(friday: Friday, title: str) -> list[dict[str, Any]]:
    return [s for s in friday.q("series_list") if s["title"] == title]
