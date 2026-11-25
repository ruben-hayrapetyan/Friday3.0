"""Naps, the whole pipeline (tests/features.toml: napping; 24 Nov, the user: "build an extensive test suite ... i want
to make sure that absolutely nothing can break without our tests flagging it"): a real `fridayd serve` with sleep
tracking on; "Taking a nap" and "I'm up", a nap logged after the fact, put right and taken back, each sent over HTTP as
the Now bar and Sleep & meals send them, and read back through `sleep` (what Sleep & meals shows) and the plan, which
keeps the time you usually nap clear of work.

The tests run in order on one server and build on each other."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from friday.core.time import clock_time
from tests.system.test_beat_plan_system import SLEEP, TZ, Friday


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("napping"))
    now = datetime.now(ZoneInfo(TZ))
    away = {"bedtime": f"{now + timedelta(hours=8):%H:%M}", "wake": f"{now + timedelta(hours=15):%H:%M}",
            "margin_min": 60}  # fmt: skip
    server.c("settings_set", key="sleep", value=dict.fromkeys(SLEEP, away))  # never asleep while the tests run
    server.c("settings_set", key="time", value=server.q("settings")["time"] | {"day_start": "04:00"})
    server.c("settings_set", key="sleep_tracking", value={"on": True})
    yield server
    server.stop()


def now() -> datetime:
    return datetime.now(ZoneInfo(TZ)).replace(second=0, microsecond=0)


def local(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M")


def yesterday(clock: str) -> str:
    return f"{(datetime.now(ZoneInfo(TZ)) - timedelta(hours=4)).date() - timedelta(days=1)}T{clock}"


def said(moment: str) -> str:
    return clock_time(moment[11:16])


def refused(friday: Friday, verb: str, **body: Any) -> str:
    """A command Friday turns down: the 422 and the words it gives ("field: words")."""
    answer = friday.http.post(f"/api/c/{verb}", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()["message"]


def naps(friday: Friday) -> dict[str, dict]:
    """The naps Sleep & meals lists, by when you lay down."""
    return {n["start"]: n for n in friday.q("sleep")["naps"]}


def test_01_with_sleep_tracking_off_a_nap_is_refused(friday: Friday) -> None:
    friday.c("settings_set", key="sleep_tracking", value={"on": False})
    assert friday.q("sleep")["on"] is False
    words = "at: sleep tracking is off; turn it on in Settings → Schedule"
    assert refused(friday, "nap_start") == words
    assert refused(friday, "nap_end") == words
    assert refused(friday, "nap_log", start=yesterday("14:00"), end=yesterday("14:30")) == words
    friday.c("settings_set", key="sleep_tracking", value={"on": True})
    out = friday.q("sleep")
    assert out["on"] is True and out["naps"] == [] and out["napping"] is None


def test_02_taking_a_nap_then_up_records_it(friday: Friday) -> None:
    base = now()
    lay = local(base - timedelta(minutes=20))
    assert friday.c("nap_start", at=lay)["message"] == f"Napping since {said(lay)}"
    napping = friday.q("sleep")["napping"]
    assert (napping["start"], napping["end"]) == (lay, None)
    assert (
        refused(friday, "nap_start", at=local(base - timedelta(minutes=10))) == f"at: you're napping since {said(lay)}"
    )
    assert refused(friday, "nap_end", at=local(base - timedelta(minutes=25))) == "at: that's before you lay down"
    assert refused(friday, "nap_end", at=local(base + timedelta(minutes=10))) == "at: that's later than now"
    assert friday.q("sleep")["napping"]["start"] == lay  # nothing refused was kept
    assert friday.c("nap_end", at=local(base))["message"] == "Nap: 20 min"
    out = friday.q("sleep")
    assert out["napping"] is None
    nap = naps(friday)[lay]
    assert (nap["end"], nap["minutes"]) == (local(base), 20)
    assert refused(friday, "nap_end") == "at: you aren't napping"


def test_03_im_up_tapped_hours_later_counts_the_usual_nap(friday: Friday) -> None:
    lay = local(now() - timedelta(minutes=200))
    friday.c("nap_start", at=lay)
    out = friday.c("nap_end")["message"]
    assert out == (
        "Nap: counted as your usual 30 min (I'm up came 3 h 20 min after you lay down); change it in Sleep & meals"
    )
    nap = naps(friday)[lay]
    assert nap["minutes"] == 30 and nap["end"] == local(datetime.fromisoformat(lay) + timedelta(minutes=30))


def test_04_a_nap_left_running_for_hours_ends_at_the_usual_when_the_next_starts(friday: Friday) -> None:
    base = now()
    forgotten, then = local(base - timedelta(minutes=300)), local(base - timedelta(minutes=60))
    friday.c("nap_start", at=forgotten)
    assert friday.c("nap_start", at=then)["message"] == f"Napping since {said(then)}"
    assert naps(friday)[forgotten]["minutes"] == 30
    assert friday.q("sleep")["napping"]["start"] == then
    assert friday.c("nap_end", at=local(base - timedelta(minutes=40)))["message"] == "Nap: 20 min"


def test_05_a_nap_ended_over_four_hours_on_is_refused_and_can_be_taken_back(friday: Friday) -> None:
    base = now()
    lay = local(base - timedelta(minutes=250))
    friday.c("nap_start", at=lay)
    assert refused(friday, "nap_end", at=local(base)) == "end: a nap ends after it starts, within four hours"
    running = friday.q("sleep")["napping"]
    assert running["start"] == lay  # still napping: nothing refused was kept
    assert friday.c("nap_remove", id=running["id"])["message"] == f"Removed the nap at {said(lay)}"
    assert friday.q("sleep")["napping"] is None and lay not in naps(friday)
    assert refused(friday, "nap_remove", id=running["id"]) == f"id: no nap {running['id']}"


def test_06_a_nap_logged_after_the_fact_shows_and_cant_overlap_another(friday: Friday) -> None:
    start, end = yesterday("14:00"), yesterday("14:45")
    assert friday.c("nap_log", start=start, end=end)["message"] == "Logged a nap, 2pm to 2:45pm"
    nap = naps(friday)[start]
    assert (nap["date"], nap["end"], nap["minutes"]) == (start[:10], end, 45)
    before = len(naps(friday))
    assert refused(friday, "nap_log", start=yesterday("14:30"), end=yesterday("15:00")) == (
        "start: you were napping from 2pm then"
    )
    assert refused(friday, "nap_log", start=yesterday("13:30"), end=yesterday("16:00")) == (
        "start: you were napping from 2pm then"  # around it
    )
    words = "end: a nap ends after it starts, within four hours"
    assert refused(friday, "nap_log", start=yesterday("10:00"), end=yesterday("10:00")) == words
    assert refused(friday, "nap_log", start=yesterday("10:00"), end=yesterday("09:00")) == words
    assert refused(friday, "nap_log", start=yesterday("08:00"), end=yesterday("12:01")) == words
    assert refused(friday, "nap_log", start=local(now()), end=local(now() + timedelta(hours=1))) == (
        "end: that's later than now"
    )
    assert len(naps(friday)) == before
    # right after it is fine
    friday.c("nap_log", start=yesterday("14:45"), end=yesterday("15:00"))
    assert naps(friday)[yesterday("14:45")]["minutes"] == 15


def test_07_a_nap_put_right_moves_its_times_not_onto_another(friday: Friday) -> None:
    nap = naps(friday)[yesterday("14:00")]
    assert (
        refused(friday, "nap_edit", id=nap["id"], end=yesterday("15:10")) == "start: you were napping from 2:45pm then"
    )
    assert friday.c("nap_edit", id=nap["id"], start=yesterday("13:15"))["message"] == "Nap now 1:15pm to 2:45pm"
    moved = naps(friday)[yesterday("13:15")]
    assert (moved["id"], moved["minutes"]) == (nap["id"], 90) and yesterday("14:00") not in naps(friday)
    assert refused(friday, "nap_edit", id=nap["id"], end=yesterday("13:00")) == (
        "end: a nap ends after it starts, within four hours"
    )
    assert refused(friday, "nap_edit", id=nap["id"], start=local(now() + timedelta(hours=1))) == (
        "start: that's later than now"
    )
    assert refused(friday, "nap_edit", id=999_999, start=yesterday("10:00")) == "id: no nap 999999"
    assert naps(friday)[yesterday("13:15")]["end"] == yesterday("14:45")  # unchanged by what was refused


def test_08_times_given_to_the_nap_youre_taking_end_it(friday: Friday) -> None:
    base = now()
    friday.c("nap_start", at=local(base - timedelta(minutes=110)))
    nap = friday.q("sleep")["napping"]
    start, end = base - timedelta(minutes=120), base - timedelta(minutes=100)
    out = friday.c("nap_edit", id=nap["id"], start=local(start), end=local(end))
    assert out["message"] == f"Nap now {said(local(start))} to {said(local(end))}"
    assert friday.q("sleep")["napping"] is None
    assert naps(friday)[local(start)]["minutes"] == 20


def test_09_friday_learns_how_long_you_nap_and_keeps_that_clear_of_work(friday: Friday) -> None:
    out = friday.q("sleep")
    lengths = [n["minutes"] for n in out["naps"]]
    assert len(lengths) >= 3
    usual = max(5, round(median(lengths) / 5) * 5)
    assert out["usual_nap_min"] == usual
    # Work due soon wants the time now: a nap keeps it clear for as long as you usually nap
    due = now() + timedelta(minutes=105)  # 90 minutes of it: it can't wait
    task = friday.c("add", title="Problem set 9", duration_min=90, firmness="hard", due=local(due))["item"]
    lay = now()
    friday.c("nap_start", at=local(lay))
    clear_until = (lay + timedelta(minutes=usual)).replace(tzinfo=None)

    def blocks() -> list[dict] | None:
        status = friday.q("status")
        if status["plan_generation"] is None or status["plan_generation"] < status["generation"]:
            return None
        found = [b for b in friday.q("plan", start=local(lay), end=local(due))["blocks"] if b["item_id"] == task["id"]]
        return found or None

    found = friday.until(blocks)
    assert all(datetime.fromisoformat(b["start"]) >= clear_until for b in found), (clear_until, found)
    friday.c("nap_remove", id=friday.q("sleep")["napping"]["id"])
    friday.c("drop", id=task["id"])
