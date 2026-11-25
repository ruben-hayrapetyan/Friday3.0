"""Input speed (24 Nov, the user: "make sure to stress test on very loaded schedules as well as varying input speeds"):
a real `fridayd serve` with a loaded week is sent the same forty changes four ways: slowly (each planned before the
next), back to back (none waited for), from six threads at once, and while it's planning. However fast they come,
each lands once, nothing errs, the plan catches up and has no overlap, and the week ends as it does sent slowly; a
burst undone as fast brings back the week it started from."""

import threading
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from tests.system.test_beat_plan_system import TZ, Friday

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
N = 40  # changes sent each way


def day(n: int, clock: str) -> str:
    return f"{(datetime.now(ZoneInfo(TZ)) + timedelta(days=n)).date()}T{clock}"


def loaded(friday: Friday) -> None:
    """A full week: awake around the clock (so the hour the test runs doesn't matter), a class every weekday,
    forty to-dos of two to five hours due over the week."""
    now = datetime.now(ZoneInfo(TZ))
    away = {"bedtime": f"{now + timedelta(hours=20):%H:%M}", "wake": f"{now + timedelta(hours=22):%H:%M}",
            "margin_min": 0}  # fmt: skip
    friday.c("settings_set", key="sleep", value=dict.fromkeys(WEEKDAYS, away))
    for d in range(1, 6):
        friday.c("add", title=f"Lecture {d}", when="fixed", start=day(d, "10:00"), end=day(d, "11:15"))
    for n in range(N):
        friday.c("add", title=f"Load {n}", duration_min=120 + 30 * (n % 7), due=day(1 + n % 6, "23:00"))


def planned(friday: Friday, timeout: float = 300) -> None:
    friday.until(lambda: (s := friday.q("status"))["plan_generation"] is not None
                 and s["plan_generation"] >= s["generation"], timeout=timeout)  # fmt: skip


def changes() -> list[tuple[str, dict[str, Any]]]:
    """Forty changes that don't depend on each other's order: new to-dos, and edits, finishes and drops of the loaded
    ones, each touching its own to-do (so six threads at once have one right answer)."""
    out: list[tuple[str, dict[str, Any]]] = []
    for n in range(N):
        kind = n % 4
        if kind == 0:
            out.append(
                ("add", {"title": f"Quick {n}", "duration_min": 30 + 15 * (n % 5), "due": day(2 + n % 4, "18:00")})
            )
        elif kind == 1:
            out.append(("edit", {"title": f"Load {n}", "duration_min": 60 + 15 * (n % 6)}))
        elif kind == 2:
            out.append(("done", {"title": f"Load {n}"}))
        else:
            out.append(("drop", {"title": f"Load {n}"}))
    titles = [body["title"] for verb, body in out if verb != "add"]
    assert len(titles) == len(set(titles)), "two changes touch one to-do"
    return out


def send(http: httpx.Client, ids: dict[str, int], verb: str, body: dict[str, Any]) -> httpx.Response:
    if verb == "add":
        return http.post("/api/c/add", json=body)
    payload = {k: v for k, v in body.items() if k != "title"} | {"id": ids[body["title"]]}
    return http.post(f"/api/c/{verb}", json=payload)


def the_week(friday: Friday) -> list[tuple]:
    """What the changes leave, by title: each to-do's status, length and due."""
    return sorted((i["title"], i["status"], i["duration_min"], i["due"]) for i in friday.q("items", status="all")
                  if i["when"] != "fixed")  # fmt: skip


def overlaps(friday: Friday) -> list[str]:
    blocks = sorted((b["start"], b["end"], b["title"]) for b in friday.q("plan", start=day(0, "00:00"),
                    end=day(8, "00:00"))["blocks"] if not b.get("background") and not b.get("state"))  # fmt: skip
    return [f"{a[2]} {a[0]}–{a[1]} and {b[2]} {b[0]}" for a, b in zip(blocks, blocks[1:], strict=False) if b[0] < a[1]]


@pytest.fixture(scope="module")
def slowly(tmp_path_factory: pytest.TempPathFactory) -> list[tuple]:
    """The answer: the changes sent one at a time, each planned before the next."""
    friday = Friday(tmp_path_factory.mktemp("speed-slow"))
    try:
        loaded(friday)
        planned(friday)
        ids = {i["title"]: i["id"] for i in friday.q("items", status="all")}
        for verb, body in changes():
            answer = send(friday.http, ids, verb, body)
            assert answer.status_code == 200, answer.text
            planned(friday)
        return the_week(friday)
    finally:
        friday.stop()


@pytest.fixture
def fresh(tmp_path: Path) -> Iterator[Friday]:
    friday = Friday(tmp_path)
    loaded(friday)
    planned(friday)
    yield friday
    friday.stop()


def same_as_slowly(friday: Friday, slowly: list[tuple], sent: list[httpx.Response]) -> None:
    errors = [f"{r.request.url.path}: {r.status_code} {r.text[:200]}" for r in sent if r.status_code != 200]
    assert errors == [], errors
    planned(friday)
    assert the_week(friday) == slowly
    assert sum(1 for i in friday.q("items", status="all") if i["title"].startswith("Quick ")) == N // 4  # each once
    assert overlaps(friday) == []
    status = friday.q("status")
    assert status["plan_generation"] >= status["generation"]


def test_back_to_back_none_waited_for(fresh: Friday, slowly: list[tuple]) -> None:
    ids = {i["title"]: i["id"] for i in fresh.q("items", status="all")}
    sent = [send(fresh.http, ids, verb, body) for verb, body in changes()]
    same_as_slowly(fresh, slowly, sent)


def at_once(friday: Friday, work: list[tuple[str, dict[str, Any]]], threads: int = 6,
            before: Callable[[], None] | None = None) -> list[httpx.Response]:  # fmt: skip
    ids = {i["title"]: i["id"] for i in friday.q("items", status="all")}
    sent: list[httpx.Response] = []
    lock = threading.Lock()
    go = threading.Barrier(threads)

    def run(part: list[tuple[str, dict[str, Any]]]) -> None:
        with httpx.Client(base_url=str(friday.http.base_url), timeout=300) as http:
            go.wait()  # all at the same moment
            for verb, body in part:
                answer = send(http, ids, verb, body)
                with lock:
                    sent.append(answer)

    workers = [threading.Thread(target=run, args=(work[n::threads],)) for n in range(threads)]
    if before:
        before()
    for w in workers:
        w.start()
    for w in workers:
        w.join(timeout=600)
    assert not any(w.is_alive() for w in workers), "a sender never got its answers"
    return sent


def test_six_at_once(fresh: Friday, slowly: list[tuple]) -> None:
    same_as_slowly(fresh, slowly, at_once(fresh, changes()))


def test_while_it_plans(fresh: Friday, slowly: list[tuple]) -> None:
    """A replan asked for, then everything sent while it runs: none of it is lost when that plan is saved."""
    sent = at_once(fresh, changes(), before=lambda: fresh.c("replan"))
    same_as_slowly(fresh, slowly, sent)


def test_a_burst_undone_as_fast_brings_the_week_back(fresh: Friday) -> None:
    start = the_week(fresh)
    ids = {i["title"]: i["id"] for i in fresh.q("items", status="all")}
    sent = [send(fresh.http, ids, verb, body) for verb, body in changes()]
    assert all(r.status_code == 200 for r in sent)
    for answer in reversed(sent):  # newest first, as ⌘Z does, without waiting
        undone = fresh.http.post("/api/c/undo", json={"command_id": answer.json()["command_id"]})
        assert undone.status_code == 200, undone.text
    planned(fresh)
    assert the_week(fresh) == start
    assert overlaps(fresh) == []
