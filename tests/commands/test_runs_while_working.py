"""Things that run by themselves run while you're working (27 Oct): "all events that are done in the background must
only be scheduled during other work times not during event times" is a rule (`runs_while_working`), and with it a
task that runs by itself is started only where all of its running time misses events and the night."""

from pathlib import Path

import pytest

from friday.core.rule_text import read
from friday.core.time import parse_local, to_utc
from friday.planner.service import replan
from tests.commands.helpers import TZ, App, new_app

SAID = (
    "all events that are done in the background must only be scheduled during other work times not during event times"
)


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=3)


def minute(local: str) -> int:
    return to_utc(parse_local(local), TZ)


@pytest.mark.parametrize(
    ("text", "strength"),
    [
        (SAID, "Always"),
        ("background tasks must not run during class", "Always"),
        ("things that run by themselves only while I'm working", "Prefer"),
        ("tasks that run on their own when I am home", "Prefer"),
    ],
)
def test_it_reads_as_the_rule(text: str, strength: str) -> None:
    reading, said = read(text)
    assert reading is not None and reading.kind == "runs_while_working"
    assert said == strength


@pytest.mark.parametrize("text", ["laundry in the background", "background music while working", "no work after 10pm"])
def test_other_sentences_dont(text: str) -> None:
    reading, _ = read(text)
    assert reading is None or reading.kind != "runs_while_working"


def test_laundry_never_runs_through_a_class_or_the_night(app: App) -> None:
    for day in ("19", "20", "21"):  # classes most of each day, so there's little room
        app.do("add", title="Class", when="fixed", start=f"2026-10-{day}T10:00", end=f"2026-10-{day}T13:00")
        app.do("add", title="Lab", when="fixed", start=f"2026-10-{day}T15:00", end=f"2026-10-{day}T18:00")
    laundry = app.do("add", text="laundry ~2h runs by itself due wed")["item"]["id"]
    app.do("rule_add", text=SAID, strength=read(SAID)[1])  # as the Rules page sends it
    (rule,) = [r for r in app.do("settings")["rules"] if r["type"] == "runs_while_working"]
    assert rule["params"]["price"] == "forbid"
    replan(app.conn, app.now_utc)
    (block,) = [b for b in app.do("plan")["blocks"] if b["item_id"] == laundry]
    start = minute(block["start"])
    running = (start + 15, start + 120)  # its first quarter hour needs you; then it runs until it's done
    busy = [(minute(f"2026-10-{d}T{lo}"), minute(f"2026-10-{d}T{hi}")) for d in ("19", "20", "21")
            for lo, hi in (("10:00", "13:00"), ("15:00", "18:00"))]  # fmt: skip
    assert not any(lo < running[1] and running[0] < hi for lo, hi in busy), block
    hour = int(block["start"][11:13])
    assert hour >= 7 and int(block["end"][11:13]) <= 23  # not through the night either
