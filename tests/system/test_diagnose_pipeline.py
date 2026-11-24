"""Report a problem through the whole of Friday (tests/features.toml: diagnose; 24 Nov, the user: "build an extensive
test suite"): a real `fridayd serve`, the app's `report` of what went wrong on screen sent over HTTP as the page
sends it, and `diagnose` read back the same way: what you did, each plan the worker made, and what the app
reported, in order."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday, local


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("diagnose_pipeline"))
    server.c("settings_set", key="sleep", value=SLEEP)
    yield server
    server.stop()


def kinds(friday: Friday, kind: str, **params: float) -> list[str]:
    return [h["summary"] for h in friday.q("diagnose", **params) if h["kind"] == kind]


def test_a_command_you_sent_is_listed_with_its_id_and_what_it_was_given(friday: Friday) -> None:
    answer = friday.http.post("/api/c/add", json={"title": "Water the plants", "duration_min": 15})
    command_id = answer.json()["command_id"]
    (line,) = [s for s in kinds(friday, "command") if s.startswith(f"C{command_id} ")]
    assert " add " in line and 'title="Water the plants"' in line and "duration_min=15" in line


def test_a_long_input_is_cut_short_and_empty_fields_are_left_out(friday: Friday) -> None:
    title = "x" * 300
    command_id = friday.http.post("/api/c/add", json={"title": title, "notes": ""}).json()["command_id"]
    (line,) = [s for s in kinds(friday, "command") if s.startswith(f"C{command_id} ")]
    given = line.split(" add ", 1)[1]
    assert len(given) == 90 and given.startswith('title="xxx')
    assert "notes=" not in line


def test_an_undone_command_says_what_undid_it(friday: Friday) -> None:
    command_id = friday.http.post("/api/c/add", json={"title": "Call the bank"}).json()["command_id"]
    undo_id = friday.http.post("/api/c/undo", json={"command_id": command_id}).json()["command_id"]
    (line,) = [s for s in kinds(friday, "command") if s.startswith(f"C{command_id} ")]
    assert line.endswith(f"(undone by C{undo_id})")
    assert any(s.startswith(f"C{undo_id} ") and " undo " in s for s in kinds(friday, "command"))


def test_each_plan_the_worker_made_is_listed_with_its_reason(friday: Friday) -> None:
    due = local(datetime.now(ZoneInfo(TZ)) + timedelta(days=2))
    friday.c("add", title="Read chapter 2", duration_min=60, due=due)
    friday.c("replan")
    plans = friday.until(lambda: kinds(friday, "plan"))
    assert all(p.startswith("P") and " s, " in p for p in plans)
    latest = friday.q("plan")["plan_id"]
    friday.until(lambda: any(p.startswith(f"P{friday.q('plan')['plan_id']} ") for p in kinds(friday, "plan")))
    assert latest is not None


def test_a_report_from_the_app_is_noted_and_listed_but_not_as_a_command(friday: Friday) -> None:
    said = friday.c("report", where="Calendar", message="the week view went blank", detail="TypeError: x is null")
    assert said["message"] == "Noted"
    assert "Calendar: the week view went blank" in kinds(friday, "report")
    assert not any(" report " in s for s in kinds(friday, "command"))  # its own sending isn't a command you did


def test_the_timeline_is_in_order(friday: Friday) -> None:
    friday.c("report", where="To-do", message="a row overlapped")
    out = friday.q("diagnose")
    assert [h["at"] for h in out] == sorted(h["at"] for h in out)
    assert {h["kind"] for h in out} >= {"command", "plan", "report"}
    assert out[-1]["kind"] in ("report", "plan", "command")


def test_only_the_last_fifty_reports_are_kept(friday: Friday) -> None:
    for n in range(55):
        friday.c("report", where="Flood", message=f"report {n}")
    flood = [s for s in kinds(friday, "report", hours=24) if s.startswith("Flood:")]
    assert len(flood) == 50 and flood[0] == "Flood: report 5" and flood[-1] == "Flood: report 54"


def test_how_far_back_is_checked(friday: Friday) -> None:
    for hours in (0, -1, 24 * 14 + 1):
        answer = friday.http.get("/api/q/diagnose", params={"hours": hours})
        assert answer.status_code == 422, (hours, answer.text)
        assert "hours" in answer.text
    assert friday.http.get("/api/q/diagnose", params={"hours": "lots"}).status_code == 422
    assert kinds(friday, "command", hours=24 * 14)  # two weeks is fine


def test_a_report_needs_where_and_what(friday: Friday) -> None:
    for body in ({"where": "Calendar"}, {"message": "it broke"}, {}):
        answer = friday.http.post("/api/c/report", json=body)
        assert answer.status_code == 422, answer.text
    assert not any("it broke" in s for s in kinds(friday, "report"))
