"""A yearly birthday moved a day later, the whole system (5 Nov: "change jaspers bday to nov 6 yearly" failed): a real
`fridayd serve`, the edit the AI proposes posted over HTTP as the app applies it, the worker replanning, and the plan
and the Repeating list read back as the app reads them."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("moving_repeats"))
    server.c("settings_set", key="sleep", value=SLEEP)
    yield server
    server.stop()


def test_a_yearly_birthday_moved_a_day_later_is_on_the_new_day_in_the_plan_and_says_yearly(friday: Friday) -> None:
    day = (datetime.now(ZoneInfo(TZ)) + timedelta(days=2)).date()
    after = day + timedelta(days=1)
    friday.c("add", title="Jasper's Birthday", when="fixed", start=f"{day}T00:00", end=f"{after}T00:00", every="year")
    (birthday,) = friday.q("events", text="jasper")
    moved = friday.http.post("/api/c/edit", json={"id": birthday["id"], "start": f"{after}T00:00",
                                                   "end": f"{after + timedelta(days=1)}T00:00",
                                                   "from_date": str(day)})  # fmt: skip
    assert moved.status_code == 200, moved.text
    window = {"start": f"{day - timedelta(days=1)}T00:00", "end": f"{after + timedelta(days=2)}T00:00"}

    def read() -> list[dict] | None:
        shown = [f for f in friday.q("plan", **window)["fixed"] if f["title"] == "Jasper's Birthday"]
        return shown if shown and shown[0]["start"].startswith(str(after)) else None

    (shown,) = friday.until(read)
    assert shown["end"] == f"{after + timedelta(days=1)}T00:00"
    (row,) = friday.q("series_list")
    assert row["pattern"] == "Yearly" and row["next"].startswith(str(after))


def test_moving_it_onto_a_day_it_cant_say_is_refused_over_http_with_why(friday: Friday) -> None:
    day = (datetime.now(ZoneInfo(TZ)) + timedelta(days=3)).date()
    friday.c("add", title="Book club", when="fixed", start=f"{day}T19:00", end=f"{day}T20:00",
             every="rrule:FREQ=MONTHLY;BYDAY=1MO,3MO")  # fmt: skip
    found = [e for e in friday.q("events", text="book club")]
    refused = friday.http.post("/api/c/edit", json={"id": found[0]["id"], "start": f"{day + timedelta(days=1)}T19:00",
                                                     "end": f"{day + timedelta(days=1)}T20:00",
                                                     "from_date": found[0]["start"][:10]})  # fmt: skip
    assert refused.status_code != 200 and "repeats on set dates" in refused.text
