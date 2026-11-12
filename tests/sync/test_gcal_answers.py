"""Glass box on what Friday makes of Google Calendar's answers (sync/gcal.py): a list is read over every page, an event
or calendar already gone is fine where that's what was wanted, any other refusal is passed on, a repeat whose rule
can't be read is left out, the "Friday" calendar is made again once deleted, and a published block Google still has
as it was isn't sent again."""

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest
from googleapiclient.errors import HttpError

from friday.sim.fakes import Call, FakeGoogle, event
from friday.sync import gcal


def refused(status: int) -> HttpError:
    return HttpError(SimpleNamespace(status=status, reason="refused"), b"refused")


class Google:
    """A Calendar API whose every call answers from `said`: each method's name, to what it gives back, the error it
    raises, or a function of what was asked giving either. `asked` is every call, in order."""

    def __init__(self, **said: Any) -> None:
        self.said = said
        self.asked: list[tuple[str, dict[str, Any]]] = []

    def events(self) -> "Google":
        return self

    def calendars(self) -> "Google":
        return self

    def calendarList(self) -> "Google":  # noqa: N802 (Google's name)
        return self

    def __getattr__(self, name: str) -> Callable[..., Call]:
        if name.startswith("_"):
            raise AttributeError(name)

        def call(**params: Any) -> Call:
            self.asked.append((name, params))

            def answer() -> Any:
                found = self.said[name]
                found = found(**params) if callable(found) else found
                if isinstance(found, Exception):
                    raise found
                return found

            return Call(answer)

        return call

    def calls(self) -> list[str]:
        return [name for name, _ in self.asked]


class TestReading:
    def test_every_page_of_a_list_is_read(self) -> None:
        pages = {
            None: {"items": [{"id": "me@gmail.com", "summary": "Me", "primary": True}], "nextPageToken": "2"},
            "2": {"items": [{"id": "c@group", "summaryOverride": "Classes", "summary": "x", "accessRole": "reader"}]},
        }
        google = Google(list=lambda pageToken: pages[pageToken])  # noqa: N803
        found = gcal.calendars(google)
        assert [(c["id"], c["name"], c["primary"], c["writable"]) for c in found] == [
            ("me@gmail.com", "Me", True, True),
            ("c@group", "Classes", False, False),
        ]
        assert [params["pageToken"] for _, params in google.asked] == [None, "2"]

    def test_a_repeat_whose_event_cant_be_read_is_left_out(self) -> None:
        def get(calendarId: str, eventId: str) -> Any:  # noqa: N803
            return {
                "gym": {"recurrence": ["EXDATE:20261027", "RRULE:FREQ=WEEKLY;BYDAY=TU"]},
                "gone": refused(404),
                "once": {"recurrence": []},
            }[eventId]

        assert gcal.repeat_rules(Google(get=get), "c", {"gym", "gone", "once"}) == {"gym": "FREQ=WEEKLY;BYDAY=TU"}


class TestChanging:
    def test_making_an_event_passes_on_any_refusal_but_its_id_being_taken(self) -> None:
        with pytest.raises(HttpError):
            gcal.insert_once(Google(insert=refused(403)), "c", "friday1", {"summary": "Gym"})
        google = Google(insert=refused(409), get={"id": "friday1", "summary": "Gym"})
        assert gcal.insert_once(google, "c", "friday1", {"summary": "Gym"}) == {"id": "friday1", "summary": "Gym"}

    @pytest.mark.parametrize("status", [404, 410])
    def test_deleting_an_event_already_gone_is_fine(self, status: int) -> None:
        gcal.delete_event(Google(delete=refused(status)), "c", "e1")

    def test_deleting_an_event_passes_on_any_other_refusal(self) -> None:
        with pytest.raises(HttpError):
            gcal.delete_event(Google(delete=refused(403)), "c", "e1")

    @pytest.mark.parametrize("status", [404, 410])
    def test_deleting_from_a_time_already_gone_asks_nothing_more(self, status: int) -> None:
        google = Google(get=refused(status))
        gcal.delete_from(google, "c", "g_2")
        assert google.calls() == ["get"]

    def test_deleting_from_a_time_passes_on_any_other_refusal(self) -> None:
        with pytest.raises(HttpError):
            gcal.delete_from(Google(get=refused(500)), "c", "g_2")

    def test_deleting_from_a_time_cancelled_already_asks_nothing_more(self) -> None:
        google = Google(get={"id": "g_2", "status": "cancelled", "recurringEventId": "g"})
        gcal.delete_from(google, "c", "g_2")
        assert google.calls() == ["get"]

    def test_deleting_from_a_time_whose_repeat_lists_no_times_deletes_the_whole_repeat(self) -> None:
        google = Google(get={"id": "g_2", "recurringEventId": "g"}, instances={}, delete=None)
        gcal.delete_from(google, "c", "g_2")
        assert google.asked[-1] == ("delete", {"calendarId": "c", "eventId": "g"})


class TestOwnCalendar:
    @pytest.mark.parametrize("status", [404, 410])
    def test_the_friday_calendar_is_made_again_once_you_deleted_it(self, status: int) -> None:
        google = Google(get=refused(status), insert={"id": "friday2@group"})
        assert gcal.own_calendar(google, "friday1@group", "America/New_York") == "friday2@group"
        assert google.asked[-1] == ("insert", {"body": {"summary": "Friday", "timeZone": "America/New_York"}})

    def test_the_friday_calendar_still_there_is_kept(self) -> None:
        google = Google(get={"id": "friday1@group"})
        assert gcal.own_calendar(google, "friday1@group", "America/New_York") == "friday1@group"
        assert google.calls() == ["get"]

    def test_a_first_friday_calendar_is_made(self) -> None:
        google = Google(insert={"id": "friday1@group"})
        assert gcal.own_calendar(google, None, "America/New_York") == "friday1@group" and google.calls() == ["insert"]

    def test_the_friday_calendar_unreadable_otherwise_is_not_made_twice(self) -> None:
        google = Google(get=refused(503))
        with pytest.raises(HttpError):
            gcal.own_calendar(google, "friday1@group", "America/New_York")
        assert google.calls() == ["get"]


class TestPublishing:
    def blocks(self) -> list[gcal.Block]:
        return [
            gcal.Block("t1:0", "Essay", "2026-10-20T14:00:00Z", "2026-10-20T15:00:00Z", tentative=False),
            gcal.Block("t2:0", "Reading", "2026-10-20T16:00:00Z", "2026-10-20T17:00:00Z", tentative=True, link="x"),
        ]

    def test_blocks_google_still_has_as_they_were_are_not_sent_again(self) -> None:
        google = FakeGoogle({"friday@group": []})
        assert gcal.publish(google, "friday@group", self.blocks(), "2026-10-20T00:00:00Z") == (2, 0, 0)
        google.writes.clear()
        # Google gives the times back in the calendar's own offset: the same moments, so nothing changed
        assert gcal.publish(google, "friday@group", self.blocks(), "2026-10-20T00:00:00Z") == (0, 0, 0)
        assert google.writes == []

    def test_an_all_day_event_is_never_the_same_as_a_timed_block(self) -> None:
        body = gcal.event_body(self.blocks()[0])
        all_day = event("x", "Essay", "2026-10-20T10:00", "2026-10-20T11:00") | {
            "start": {"date": "2026-10-20"},
            "end": {"date": "2026-10-21"},
            "status": "confirmed",
        }
        assert not gcal.same(all_day, body)
        assert gcal.same(body, body)
