"""The Inbox's whole pipeline (tests/features.toml: inbox; 24 Nov, the user: "go through every single functionality of
the app and build an extensive test suite"): a real `fridayd serve` on the real clock, its job loop reading what you
gave it, and only HTTP between it and the test. A calendar link and a stand-in AI service (OpenAI's chat API, as a
service you'd name in Settings → AI speaks it) are served from this test, so a feed is fetched, a document is read
by "the AI", and what they found comes into the Inbox to accept, reject, set aside and bring back."""

import json
import threading
import time
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import TZ, Friday

WAIT = 240  # the job loop reads sources once a minute, waking every 30 s


class Served:
    """A calendar link and an OpenAI-style AI service, both on 127.0.0.1."""

    def __init__(self) -> None:
        self.feeds: dict[str, str] = {}
        self.ai_fails = False  # the AI refuses each document (a 422 about the input: the document fails)
        self.asked: list[dict[str, Any]] = []
        served = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: Any) -> None:
                pass

            def do_GET(self) -> None:  # noqa: N802
                body = served.feeds.get(self.path)
                self.send_response(200 if body is not None else 404)
                self.send_header("content-type", "text/calendar")
                self.end_headers()
                self.wfile.write((body or "not here").encode())

            def do_POST(self) -> None:  # noqa: N802
                asked = json.loads(self.rfile.read(int(self.headers["content-length"])))
                served.asked.append(asked)
                status, answer = served.answer(asked)
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(answer).encode())

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def answer(self, asked: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        schema = ((asked.get("response_format") or {}).get("json_schema") or {}).get("schema") or {}
        said = json.dumps(asked["messages"])
        fields = schema.get("properties", {})
        if "is_syllabus" in fields:  # a document
            if self.ai_fails:
                return 422, {"error": {"message": "this input can't be read"}}
            found = [lab_report(text) for text in LAB_LINES if text.split(" is due")[0] in said]
            out: dict[str, Any] = {"is_syllabus": False, "items": [f for f in found if f]}
        elif "items" in fields:  # sorting a calendar's events: left as the feed has them
            out = {"items": []}
        else:  # a quick-add line (Ask AI)
            out = {"title": "Call the dentist", "preset": "Errand", "area": None, "due": None, "start": None,
                   "end": None, "duration_min": 15, "pages": None, "every": None, "before": None, "quotes": [],
                   "confidence": 0.8}  # fmt: skip
        return 200, {"choices": [{"message": {"content": json.dumps(out)}}],
                     "usage": {"prompt_tokens": 300, "completion_tokens": 50}}  # fmt: skip

    def stop(self) -> None:
        self.server.shutdown()


def day(n: int) -> datetime:
    """Midnight n days from today, here."""
    return datetime.now(ZoneInfo(TZ)).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=n)


DUE = day(6).replace(hour=17)
LAB_LINES = [f"Lab report 7 is due {DUE:%Y-%m-%d} at 5pm.", f"Reading response 3 is due {DUE:%Y-%m-%d} at 5pm."]


def lab_report(text: str) -> dict[str, Any] | None:
    title = text.split(" is due")[0]
    return {"title": title, "preset": "Assignment", "area": None, "due": f"{DUE:%Y-%m-%dT%H:%M}", "start": None,
            "end": None, "duration_min": 90, "pages": None, "every": None, "before": None,
            "quotes": [{"field": "due", "words": text.split(" is ")[1].rstrip(".")}], "confidence": 0.9}  # fmt: skip


def ics(*events: tuple[str, str, datetime]) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//test//EN"]
    for uid, title, start in events:
        utc = start.astimezone(ZoneInfo("UTC"))
        lines += ["BEGIN:VEVENT", f"UID:{uid}", f"SUMMARY:{title}", f"DTSTART:{utc:%Y%m%dT%H%M%SZ}",
                  f"DTEND:{utc + timedelta(hours=1):%Y%m%dT%H%M%SZ}", "END:VEVENT"]  # fmt: skip
    return "\r\n".join([*lines, "END:VCALENDAR", ""])


@pytest.fixture(scope="module")
def served() -> Iterator[Served]:
    out = Served()
    out.feeds["/robotics.ics"] = ics(("social-1", "Robotics Club Social", day(3).replace(hour=18)),
                                     ("demo-1", "Robotics Demo Day", day(4).replace(hour=15)))  # fmt: skip
    out.feeds["/talks.ics"] = ics(("talk-1", "Guest talk on compilers", day(5).replace(hour=16)))
    yield out
    out.stop()


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("inbox"))
    yield server
    server.stop()


def refused(friday: Friday, verb: str, **body: Any) -> dict[str, Any]:
    answer = friday.http.post(f"/api/c/{verb}", json=body)
    assert answer.status_code == 422, answer.text
    out = answer.json()
    return out | {"message": out["message"].removeprefix(f"{out['field']}: ")}  # the words, without "field: "


def waited(friday: Friday, check: Callable[[], Any]) -> Any:
    """`check()` once truthy, nudging the job loop awake every few seconds meanwhile."""
    last = [0.0]

    def nudged() -> Any:
        found = check()
        if not found and time.time() - last[0] > 5:
            friday.c("sync_now")
            last[0] = time.time()
        return found

    return friday.until(nudged, WAIT)


def source(friday: Friday, name: str) -> dict[str, Any] | None:
    return next((s for s in friday.q("inbox")["sources"] if s["name"] == name), None)


def pending(friday: Friday, title: str) -> list[dict[str, Any]]:
    return [s for s in friday.q("inbox")["suggestions"] if s["input"].get("title") == title]


def document(friday: Friday, name: str) -> dict[str, Any] | None:
    return next((d for d in friday.q("documents") if d["name"] == name), None)


def items_titled(friday: Friday, title: str) -> list[dict[str, Any]]:
    return [i for i in friday.q("items", status="all") if i["title"] == title]


def events_titled(friday: Friday, title: str) -> list[dict[str, Any]]:
    return [i for i in friday.q("events", text=title) if i["title"] == title]


# --- calendar links: source_add, source_edit, source_remove ---


def test_a_link_added_is_read_and_its_events_come_into_the_inbox_untrusted(friday: Friday, served: Served) -> None:
    said = friday.c("source_add", name="Robotics", url=f"{served.url}/robotics.ics")
    assert said["message"] == "Added Robotics; it syncs within a minute"
    added = source(friday, "Robotics")
    assert added and (added["kind"], added["enabled"], added["trusted"]) == ("ics", True, False)
    social = waited(friday, lambda: pending(friday, "Robotics Club Social"))
    assert social[0]["source"] == "Robotics" and social[0]["source_kind"] == "ics"
    assert social[0]["input"]["start"] == f"{day(3):%Y-%m-%d}T18:00"
    assert pending(friday, "Robotics Demo Day")
    assert source(friday, "Robotics")["last_sync"] is not None
    assert not events_titled(friday, "Robotics Club Social")  # nothing reaches the plan until you accept it


def test_the_same_name_twice_is_refused(friday: Friday, served: Served) -> None:
    out = refused(friday, "source_add", name="Robotics", url=f"{served.url}/talks.ics")
    assert out["field"] == "name" and "already read a link called Robotics" in out["message"]
    assert [s["name"] for s in friday.q("inbox")["sources"]].count("Robotics") == 1


def test_an_unknown_service_is_refused(friday: Friday, served: Served) -> None:
    out = refused(friday, "source_add", name="Mystery", url=f"{served.url}/talks.ics", service="nope")
    assert out["field"] == "service" and "doesn't know" in out["message"]
    assert source(friday, "Mystery") is None


def test_a_broken_link_says_so_and_a_new_link_reads_it(friday: Friday, served: Served) -> None:
    friday.c("source_add", name="Talks", url=f"{served.url}/missing.ics")
    broken = waited(friday, lambda: (s := source(friday, "Talks")) and s["last_error"] and s)
    assert "404" in broken["last_error"] or "calendar link" in broken["last_error"].lower()
    assert not pending(friday, "Guest talk on compilers")
    said = friday.c("source_edit", id=broken["id"], url=f"{served.url}/talks.ics")
    assert said["message"] == "Saved Talks"
    talk = waited(friday, lambda: pending(friday, "Guest talk on compilers"))
    assert talk[0]["source"] == "Talks"
    assert source(friday, "Talks")["last_error"] is None


def test_a_link_renamed_trusted_and_switched_off(friday: Friday) -> None:
    talks = source(friday, "Talks")
    assert friday.c("source_edit", id=talks["id"], name="Compiler talks")["message"] == "Saved Compiler talks"
    friday.c("source_edit", id=talks["id"], trusted=True)
    friday.c("source_edit", id=talks["id"], enabled=False)
    after = source(friday, "Compiler talks")
    assert after and (after["id"], after["trusted"], after["enabled"]) == (talks["id"], True, False)
    assert source(friday, "Talks") is None
    friday.c("source_edit", id=talks["id"], enabled=True, trusted=False)
    again = source(friday, "Compiler talks")
    assert (again["trusted"], again["enabled"]) == (False, True)


def test_renaming_to_a_name_taken_or_a_source_not_there_is_refused(friday: Friday) -> None:
    talks = source(friday, "Compiler talks")
    out = refused(friday, "source_edit", id=talks["id"], name="Robotics")
    assert out["field"] == "name" and "already read one called Robotics" in out["message"]
    assert source(friday, "Compiler talks") is not None
    assert refused(friday, "source_edit", id=9999, name="x")["message"] == "no source 9999"
    assert refused(friday, "source_remove", id=9999)["message"] == "no source 9999"


def test_removed_without_forgetting_it_stops_and_what_it_brought_waits(friday: Friday, served: Served) -> None:
    talks = source(friday, "Compiler talks")
    said = friday.c("source_remove", id=talks["id"])
    assert said["message"] == "Stopped reading Compiler talks"
    assert source(friday, "Compiler talks")["enabled"] is False
    assert pending(friday, "Guest talk on compilers")  # still yours to answer
    # added again by its name (10 Nov: refused, the name taken), it's read again at its new address
    assert friday.c("source_add", name="Compiler talks", url=f"{served.url}/talks.ics")["message"].startswith("Added")
    back = source(friday, "Compiler talks")
    assert back["id"] == talks["id"] and back["enabled"] is True


def test_removed_and_forgotten_its_waiting_suggestions_go_and_the_accepted_one_stays(friday: Friday) -> None:
    robotics = source(friday, "Robotics")
    social = pending(friday, "Robotics Club Social")[0]
    assert friday.c("suggestion_accept", id=social["id"])["message"].startswith("Accepted")
    assert events_titled(friday, "Robotics Club Social")
    said = friday.c("source_remove", id=robotics["id"], forget=True)
    assert said["message"] == "Removed Robotics and what it brought in; the one you accepted stays"
    assert source(friday, "Robotics") is None
    assert not pending(friday, "Robotics Demo Day")
    kept = events_titled(friday, "Robotics Club Social")
    assert kept and kept[0]["status"] == "todo"


# --- Ask AI ---


def test_ask_ai_without_an_ai_says_how_to_get_one(friday: Friday) -> None:
    out = refused(friday, "ask_ai", text="call the dentist sometime next week")
    assert out["field"] == "text" and "No AI" in out["message"]


def test_ask_ai_reads_the_line_with_the_ai_and_counts_the_call(friday: Friday, served: Served) -> None:
    friday.c("settings_set", key="llm", value={"provider": "compatible", "base_url": f"{served.url}/v1",
                                               "model": "stand-in", "small_model": "stand-in"})  # fmt: skip
    before = friday.q("inbox")["llm"]
    assert before["ready"] is True
    fields = friday.c("ask_ai", text="call the dentist sometime next week")
    assert fields["title"] == "Call the dentist" and fields["duration_min"] == 15 and fields["preset"] == "Errand"
    assert "quotes" not in fields and "confidence" not in fields  # the add's fields only, for you to confirm
    assert "call the dentist sometime next week" in json.dumps(served.asked[-1]["messages"])
    after = friday.q("inbox")["llm"]
    assert after["calls"] == before["calls"] + 1 and after["tokens"] == before["tokens"] + 350
    assert not items_titled(friday, "Call the dentist")  # nothing is added until you confirm it


def test_ask_ai_past_the_days_budget_is_refused(friday: Friday) -> None:
    used = friday.q("inbox")["llm"]["calls"]
    friday.c("settings_set", key="llm", value={"daily_calls": used})
    out = refused(friday, "ask_ai", text="buy stamps")
    assert "budget is spent" in out["message"]
    friday.c("settings_set", key="llm", value={"daily_calls": 50})
    assert friday.c("ask_ai", text="buy stamps")["title"]


# --- documents: document_add, document_retry ---


def test_a_document_that_cant_be_read_says_so_and_read_again_finds_its_work(friday: Friday, served: Served) -> None:
    served.ai_fails = True
    said = friday.c("document_add", name="Lab handout.txt", content=f"CHEM 2090 lab. {LAB_LINES[0]} Bring goggles.")
    assert said["message"] == "Reading Lab handout.txt; its suggestions come into the inbox within a minute"
    assert document(friday, "Lab handout.txt")["status"] == "reading"
    failed = waited(friday, lambda: (d := document(friday, "Lab handout.txt")) and d["status"] == "failed" and d)
    assert "can't be read" in failed["error"] and failed["found"] == 0
    assert not pending(friday, "Lab report 7")
    served.ai_fails = False
    said = friday.c("document_retry", id=failed["id"])
    assert said["message"] == "Reading Lab handout.txt again; what it finds comes into the inbox within a minute"
    assert document(friday, "Lab handout.txt")["status"] == "reading"
    read = waited(friday, lambda: (d := document(friday, "Lab handout.txt")) and d["status"] == "read" and d)
    assert (read["found"], read["waiting"], read["error"]) == (1, 1, None)
    found = pending(friday, "Lab report 7")
    assert found and found[0]["source"] == "Uploads" and found[0]["origin"] == "Lab handout.txt"
    assert found[0]["input"]["due"] == f"{DUE:%Y-%m-%dT%H:%M}"


def test_read_again_is_refused_for_one_that_didnt_fail_or_isnt_there(friday: Friday) -> None:
    read = document(friday, "Lab handout.txt")
    assert refused(friday, "document_retry", id=read["id"])["message"] == "Lab handout.txt isn't one that failed"
    assert refused(friday, "document_retry", id=9999)["message"] == "no uploaded document 9999"
    assert document(friday, "Lab handout.txt")["status"] == "read"


def test_the_same_document_again_says_what_became_of_it(friday: Friday) -> None:
    again = friday.c("document_add", name="Lab handout.txt",
                     content=f"CHEM 2090 lab. {LAB_LINES[0]} Bring goggles.")  # fmt: skip
    assert again["message"] == "You uploaded Lab handout.txt already: it found 1: 1 waiting in your Inbox"
    assert [d["name"] for d in friday.q("documents")].count("Lab handout.txt") == 1


def test_a_web_page_with_no_text_is_refused(friday: Friday) -> None:
    out = refused(friday, "document_add", name="blank.html", media_type="text/html",
                  content="<html><body><script>x()</script></body></html>")  # fmt: skip
    assert out["field"] == "content" and out["message"] == "blank.html has no text in it"
    assert document(friday, "blank.html") is None


# --- suggestions: suggestion_reject, suggestion_restore ---


def test_a_rejected_suggestion_leaves_the_inbox_and_isnt_added(friday: Friday) -> None:
    friday.c("document_add", name="Reading list.txt", content=f"HIST 1500. {LAB_LINES[1]}")
    found = waited(friday, lambda: pending(friday, "Reading response 3"))
    assert friday.c("suggestion_reject", id=found[0]["id"])["message"] == "Rejected"
    assert not pending(friday, "Reading response 3")
    assert not items_titled(friday, "Reading response 3")
    out = refused(friday, "suggestion_reject", id=found[0]["id"])  # answered already
    assert out["message"] == f"no pending suggestion {found[0]['id']}"
    said = friday.c("document_add", name="Reading list.txt", content=f"HIST 1500. {LAB_LINES[1]}")
    assert said["message"] == "You uploaded Reading list.txt already: it found 1: 1 turned down"


def test_what_you_have_already_is_set_aside_and_add_anyway_brings_it_back(friday: Friday) -> None:
    lab = pending(friday, "Lab report 7")[0]
    friday.c("suggestion_accept", id=lab["id"])
    assert len(items_titled(friday, "Lab report 7")) == 1
    friday.c("document_add", name="Lab handout v2.txt", content=f"CHEM 2090, updated. {LAB_LINES[0]}")

    def aside() -> dict[str, Any] | None:
        return next((s for s in friday.q("inbox")["set_aside"] if s["title"] == "Lab report 7"), None)

    found = waited(friday, aside)
    assert found["why"] == "You have Lab report 7"
    assert not pending(friday, "Lab report 7")
    assert document(friday, "Lab handout v2.txt")["aside"] == 1
    assert friday.c("suggestion_restore", id=found["id"])["message"] == "Back in your inbox"
    back = pending(friday, "Lab report 7")
    assert [s["id"] for s in back] == [found["id"]] and back[0]["duplicate_of"] is None
    assert aside() is None
    out = refused(friday, "suggestion_restore", id=found["id"])  # waiting now, not set aside
    assert out["message"] == f"no suggestion {found['id']} set aside"
    assert refused(friday, "suggestion_restore", id=9999)["message"] == "no suggestion 9999 set aside"


def test_one_brought_back_is_never_set_aside_again(friday: Friday) -> None:
    back = [s["id"] for s in pending(friday, "Lab report 7")]
    read = source(friday, "Compiler talks")["last_sync"]
    waited(friday, lambda: source(friday, "Compiler talks")["last_sync"] != read)  # a sync checked what waits again
    assert [s["id"] for s in pending(friday, "Lab report 7")] == back
