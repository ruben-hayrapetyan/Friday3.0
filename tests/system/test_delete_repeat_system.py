"""A yearly birthday deleted in Friday goes from the Mac's calendar every year, the whole system (8 Nov: deleting
twenty-two birthdays here would have left every later year in Google): a real `fridayd serve` with the Mac app's side
played over HTTP as it plays it. The birthday is made on your Gmail calendar through the Mac; deleted here, the Mac
app is asked to delete it from that time on, and once it has, nothing more is waiting."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import TZ, Friday

GMAIL = {"id": "gmail-cal", "name": "you@gmail.com", "account": "Google", "type": "caldav",
         "color": "#3a5a8c", "writable": True}  # fmt: skip


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("delete_repeat"))
    yield server
    server.stop()


def test_a_birthday_deleted_here_is_deleted_on_the_mac_from_then_on(friday: Friday) -> None:
    now = datetime.now(ZoneInfo(TZ))
    friday.c("mac_sync", calendars=[GMAIL], events=[], since=(now - timedelta(days=1)).isoformat(),
             until=(now + timedelta(days=60)).isoformat())  # fmt: skip
    friday.c("settings_set", key="gcal", value={"new_events_to": "gmail-cal"})
    day = (now + timedelta(days=3)).date()
    made = friday.c("add", title="Remy's Birthday", when="fixed", start=f"{day}T00:00",
                    end=f"{day + timedelta(days=1)}T00:00", every="rrule:FREQ=YEARLY", after=[], before=[],
                    exceptions=[])  # fmt: skip
    (create,) = [j for j in friday.q("mac_writes") if j["op"] == "create"]
    friday.c("mac_written", id=create["id"], ok=True, event={
        "id": "ray1@1", "calendar": "gmail-cal", "title": "Remy's Birthday", "start": create["start"],
        "end": create["end"], "all_day": True})  # fmt: skip
    assert friday.q("mac_writes") == []
    friday.c("series_delete", id=made["series_id"])
    (gone,) = friday.q("mac_writes")
    assert gone["op"] == "delete_from" and gone["calendar"] == "gmail-cal"
    friday.c("mac_written", id=gone["id"], ok=True)
    assert friday.q("mac_writes") == []
