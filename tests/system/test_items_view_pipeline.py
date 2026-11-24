"""How a quick-add line reads (tests/features.toml: items_view, `parse`), the whole pipeline: a real `fridayd serve`,
each line asked over HTTP as To-do's Add box asks it while you type, and checked against the text it came from, against
what adding the same line then makes, and that asking added nothing."""

from collections.abc import Iterator
from datetime import datetime

import pytest

from tests.system.test_beat_plan_system import Friday


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("items_view"))
    server.c("area_add", name="CS 2112")
    yield server
    server.stop()


def spans(text: str, read: dict) -> dict[str, str]:
    """Each span's kind and the words it covers."""
    return {s["kind"]: text[s["start"] : s["end"]] for s in read["spans"]}


def test_a_line_reads_as_title_due_length_and_kind_each_span_on_its_words(friday: Friday) -> None:
    text = "lab writeup due fri 5pm ~2h"
    read = friday.q("parse", text=text)
    fields = read["fields"]
    assert fields["title"] == "lab writeup" and fields["preset"] == "Assignment"
    assert fields["duration_units"] == 8  # two hours in quarter hours
    due = datetime.fromisoformat(fields["due_local"])
    assert (due.weekday(), due.hour, due.minute) == (4, 17, 0)
    assert spans(text, read) == {"due_local": "due fri 5pm", "length": "~2h"}
    assert {s["kind"]: s["value"] for s in read["spans"]}["length"] == 120
    assert read["warnings"] == []


def test_asking_how_a_line_reads_adds_nothing(friday: Friday) -> None:
    before = friday.q("items", status="all")
    friday.q("parse", text="essay due mon ~3h")
    assert friday.q("items", status="all") == before
    assert [a["name"] for a in friday.q("areas")] == ["CS 2112"]


def test_adding_the_line_makes_what_it_was_read_as(friday: Friday) -> None:
    text = "problem set 5 due thu 11am ~90m"
    fields = friday.q("parse", text=text)["fields"]
    item = friday.c("add", text=text)["item"]
    assert item["title"] == fields["title"] == "problem set 5"
    assert item["due"] == fields["due_local"]
    assert item["duration_min"] == fields["duration_units"] * 15 == 90
    assert item["preset"] == fields["preset"]
    assert friday.q("item", id=item["id"])["item"]["due"] == fields["due_local"]


def test_a_known_tag_is_read_from_its_hashtag_or_the_course_in_the_title(friday: Friday) -> None:
    text = "read ch 4 #cs2112 ~45m"
    read = friday.q("parse", text=text)
    assert read["fields"]["area"] == "CS 2112" and read["fields"]["title"] == "read ch 4"
    assert read["fields"]["preset"] == "Reading" and read["fields"]["duration_units"] == 3
    (area,) = [s for s in read["spans"] if s["kind"] == "area"]
    assert text[area["start"] : area["end"]] == "#cs2112" and area["value"] == {"name": "CS 2112", "new": False}
    assert friday.q("parse", text="CS 2112 problem set due tomorrow")["fields"]["area"] == "CS 2112"


def test_a_new_tag_and_an_unknown_kind_are_warned_about_not_made(friday: Friday) -> None:
    read = friday.q("parse", text="essay #newthing /nonsense ~3h")
    assert "new area newthing" in read["warnings"] and "unknown preset /nonsense" in read["warnings"]
    assert {"name": "newthing", "new": True} in [s["value"] for s in read["spans"] if s["kind"] == "area"]
    assert "newthing" not in [a["name"] for a in friday.q("areas")]


def test_a_kind_said_with_a_slash_is_that_kind(friday: Friday) -> None:
    text = "flashcards /exam-prep ~1h"
    read = friday.q("parse", text=text)
    assert read["fields"]["preset"] == "Exam prep"
    assert spans(text, read)["preset"] == "/exam-prep"


def test_something_at_a_time_reads_as_an_event_an_hour_long_unless_said(friday: Friday) -> None:
    read = friday.q("parse", text="dinner with sam fri 7pm")
    fields = read["fields"]
    start, end = datetime.fromisoformat(fields["start_local"]), datetime.fromisoformat(fields["end_local"])
    assert fields["preset"] == "Event" and (start.weekday(), start.hour) == (4, 19)
    assert (end - start).total_seconds() == 3600 and "no length given; 1 h assumed" in read["warnings"]
    made = friday.c("add", text="dinner with sam fri 7pm")["item"]
    assert (made["when"], made["start"], made["end"]) == ("fixed", fields["start_local"], fields["end_local"])


# the span's kind, spelled so tests/test_features.py doesn't take it for the `repeat` command tested here (it isn't)
REPEAT = "".join(("re", "peat"))


def test_a_repeat_reads_as_its_rule(friday: Friday) -> None:
    text = "run every mon,wed 7am ~30m"
    read = friday.q("parse", text=text)
    assert read["fields"]["rrule"] == "FREQ=WEEKLY;BYDAY=MO,WE"
    assert spans(text, read)[REPEAT] == "every mon,wed"
    assert read["fields"]["duration_units"] == 2


def test_a_line_with_no_title_says_so(friday: Friday) -> None:
    for text in ("", "  ~2h"):
        read = friday.q("parse", text=text)
        assert read["fields"]["title"] == "" and "no title" in read["warnings"]


def test_parse_without_text_is_refused(friday: Friday) -> None:
    answer = friday.http.get("/api/q/parse")
    assert answer.status_code == 422
    (error,) = answer.json()["detail"]
    assert error["loc"] == ["query", "text"] and error["type"] == "missing"
