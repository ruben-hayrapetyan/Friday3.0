"""Commands in random orders, on an isolated app: whatever you do and in whatever order, a refused command leaves no
trace, undo puts back every row a command changed (or refuses cleanly), What if and a preview change nothing, every
item kept is one `add` would accept, and each plan a replan saves keeps its walls: no work on an event's time or in the
night, on something done or dropped, or past what's left of it."""

import contextlib
import json
import sqlite3
from collections.abc import Callable
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from friday.commands import whatif
from friday.core.items import FieldError, validate
from friday.core.rows import item_from_row
from friday.core.time import UNIT_MIN, format_utc, parse_utc
from friday.planner.build import build_problem
from friday.planner.prepare import build_input
from friday.planner.service import replan
from friday.planner.snapshot import take_snapshot
from friday.planner.store import current_plan
from tests.commands.helpers import App, new_app

DAYS = ["2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23"]  # Mon 9am is "now"
TITLES = ["Essay", "PS 5", "Lab report", "Reading ch 4", "Laundry", "Groceries", "Gym", "Climbing club", "Lunch"]
PRESETS = [None, "Assignment", "Reading", "Chore", "Errand", "Habit", "Exam prep"]
LINES = [
    "essay draft due wed 5pm ~3h",
    "laundry every week ~2h runs by itself",
    "gym every mon,wed 7pm 1h",
    "lunch every day 11:30am-2pm 30-45m",
    "groceries sat",
    "salsa friday from 6:15 to 7:30",
    "store run maybe tue-thu ~2h",
    "read dune open",
    "reading by tues 1:25pm ~5h",
    "climbing club every tue 7pm 2h",
    "problem set every week due fri 5pm ~3h",
    "office hours wed 3-4pm",
    "water plants every day ~15m",
    "study session tmrw 4pm 2h",
    "call mom ~20m /errand",
    "PS6 due thu ~90m one-sitting !4",
]
RULES = [
    "no work after 10pm",
    "no work before 9am on weekdays",
    "deep work in the morning",
    "keep saturday mornings free",
    "at most 6 hours a day",
    "finish things a day early",
    "gym right after class",
    "climbing club is optional",
    "30 minutes before and after gym",
    "go easier on wednesday",
    "never skip lunch",
    "readings as late as possible",
    "fit tasks to the gaps",
    "no work between 12pm and 1pm",
]
SHOVES = ["30m", "1h", "12:00-13:30", "15:00-16:00 tue", "day wed", "rest"]
EVERY = ["day", "week", "mon,wed,fri", "tue and thu", "other week", "weekdays"]
STRENGTHS = ["Prefer", "Strongly", "Always"]
DECISIONS = ["ask", "shove_anyway", "keep_must_dos", "cancel"]

Action = tuple[Any, ...]
ref = st.integers(0, 60)  # an item by its place among the items so far (modulo how many there are)
quarter = st.one_of(st.integers(8 * 4, 21 * 4), st.integers(0, 24 * 4 - 2))  # mostly 8am to 9pm, in quarter hours


def at(day: int, q: int) -> str:
    return f"{DAYS[day]}T{q // 4:02d}:{q % 4 * 15:02d}"


tasks = st.tuples(
    st.just("task"),
    st.sampled_from(TITLES),
    st.integers(1, 16).map(lambda n: n * 15),
    st.one_of(st.none(), st.tuples(st.integers(0, 4), quarter)),
    st.sampled_from(PRESETS),
    st.sampled_from([None, "one_sitting", "split"]),
)
events = st.tuples(
    st.just("event"), st.sampled_from(TITLES), st.integers(0, 4), quarter, st.integers(1, 12), st.booleans()
)
lines = st.tuples(st.just("line"), st.sampled_from(LINES))
series = st.tuples(st.just("series"), st.sampled_from(TITLES), st.sampled_from(EVERY), st.booleans(), quarter)
edits = st.tuples(
    st.just("edit"),
    ref,
    st.sampled_from(["duration", "due", "importance", "title", "times", "preset", "elastic"]),
    st.integers(0, 1000),
)
simple = st.tuples(st.sampled_from(["drop", "done", "reopen", "skip", "unpin", "start"]), ref)
pins = st.tuples(st.just("pin"), ref, st.integers(0, 3), quarter, st.one_of(st.none(), st.integers(1, 8)),
                 st.sampled_from(["locked", "preferred"]))  # fmt: skip
shoves = st.tuples(st.just("shove"), st.sampled_from(SHOVES), st.sampled_from(DECISIONS))
rules = st.tuples(st.just("rule"), st.sampled_from(RULES), st.sampled_from(STRENGTHS))
progress = st.tuples(st.just("progress"), ref, st.sampled_from([0.0, 0.25, 0.5, 0.9, 1.0]))
stops = st.tuples(st.just("stop"), st.booleans())
undos = st.tuples(st.just("undo"), st.one_of(st.just(1), st.integers(1, 6)))  # the newest, or one before it
ticks = st.tuples(st.just("tick"), st.integers(1, 32).map(lambda n: n * 15))
replans = st.tuples(st.just("replan"))
depends = st.tuples(st.sampled_from(["depend", "undepend"]), ref, ref, st.sampled_from([0.5, 1.0]))
repeats = st.tuples(
    st.sampled_from(["series_stop", "series_delete", "series_edit", "edit_from", "repeat"]),
    ref,
    st.sampled_from(EVERY),
    st.integers(1, 16).map(lambda n: n * 15),
)
logs = st.tuples(st.just("log"), ref, st.integers(0, 1), quarter, st.integers(1, 8))
rule_changes = st.tuples(st.sampled_from(["rule_set", "rule_remove"]), st.integers(0, 30), st.sampled_from(STRENGTHS))
day_overrides = st.tuples(
    st.just("day_override"),
    st.integers(0, 4),
    st.sampled_from(["21:00", "23:00", "01:30"]),
    st.sampled_from([None, "06:00", "10:00"]),
    st.sampled_from([None, 2.0, 8.0]),
)
staged = st.lists(st.one_of(tasks, events, lines, edits, simple, pins, shoves, rules), min_size=1, max_size=3)
whatifs = st.tuples(st.sampled_from(["whatif", "keep"]), staged)
previews = st.tuples(
    st.just("preview"),
    st.one_of(tasks, events, lines, edits, simple, pins, rules, progress),
    st.sampled_from([True, "full"]),
)

# Undo and replan come up three and two times as often as the rest.
ACTIONS = st.one_of(
    tasks, events, lines, series, edits, simple, pins, shoves, rules, progress, stops, ticks, whatifs, depends, repeats,
    logs, rule_changes, day_overrides, previews, undos, undos, undos, replans, replans,
)  # fmt: skip


# Items an action can name: all but the far occurrences of a repeat (a daily one makes months of them).
NEAR_ITEMS = (
    "SELECT id FROM items i WHERE series_id IS NULL "
    "OR (SELECT count(*) FROM items j WHERE j.series_id = i.series_id AND j.id < i.id) < 3 ORDER BY id"
)


def change_of(app: App, action: Action) -> tuple[str, dict[str, Any]] | None:
    """The command (and its input) an action is, or None when it names an item and there are none."""
    kind = action[0]
    if kind == "task":
        _, title, minutes, due, preset, shape = action
        payload: dict[str, Any] = {"title": title, "duration_min": minutes}
        if due is not None:
            payload["due"] = at(*due)
        if preset is not None:
            payload["preset"] = preset
        if shape is not None:
            payload["shape"] = shape
        return "add", payload
    if kind == "event":
        _, title, day, q, length, blocks = action
        end = min(q + length, 24 * 4 - 1)
        return "add", {"title": title, "when": "fixed", "start": at(day, q), "end": at(day, end), "blocks_time": blocks}
    if kind == "line":
        return "add", {"text": action[1]}
    if kind == "series":
        _, title, every, fixed, q = action
        if fixed:
            start, end = at(0, q), at(0, min(q + 4, 24 * 4 - 1))
            return "series_add", {"title": title, "every": every, "when": "fixed", "start": start, "end": end}
        return "series_add", {"title": title, "every": every, "duration_min": 45}
    if kind == "shove":
        return "shove", {"range": action[1], "decision": action[2]}
    if kind == "rule":
        return "rule_add", {"text": action[1], "strength": action[2]}
    if kind == "stop":
        return "stop", {"done": action[1]}
    if kind == "day_override":
        _, day, bedtime, wake, cap = action
        return "day_override", {"date": DAYS[day], "bedtime": bedtime, "wake": wake, "cap_hours": cap}
    if kind in ("rule_set", "rule_remove"):
        names = [r["name"] for r in app.do("rules")]
        name = names[action[1] % len(names)]
        return kind, {"name": name} | ({"strength": action[2]} if kind == "rule_set" else {})
    ids = [r[0] for r in app.conn.execute(NEAR_ITEMS)]
    if not ids:
        return None
    item = ids[action[1] % len(ids)]
    if kind in ("drop", "done", "reopen", "skip", "start"):
        return kind, {"id": item}
    if kind == "unpin":
        return "unpin", {"id": item}
    if kind == "progress":
        return "progress", {"id": item, "share": action[2]}
    if kind == "pin":
        _, _, day, q, length, pin_kind = action
        payload = {"id": item, "start": at(day, q), "kind": pin_kind}
        if length is not None:
            payload["end"] = at(day, min(q + length, 24 * 4 - 1))
        return "pin", payload
    if kind in ("depend", "undepend"):
        other = ids[action[2] % len(ids)]
        return kind, {"item_id": item, "depends_on_id": other, "fraction": action[3], "lag_min": 0}
    if kind == "log":
        _, _, day, q, length = action
        return "log", {"id": item, "start": at(day, q), "end": at(day, min(q + length, 24 * 4 - 1))}
    if kind in ("series_stop", "series_delete", "series_edit", "edit_from", "repeat"):
        _, _, every, minutes = action
        found = app.conn.execute("SELECT series_id, occurrence_date FROM items WHERE id = ?", [item]).fetchone()
        if kind == "repeat":
            return "repeat", {"id": item, "every": every}
        if found["series_id"] is None:
            return None
        if kind == "edit_from":
            return "edit", {"id": item, "from_date": found["occurrence_date"], "duration_min": minutes}
        if kind == "series_edit":
            return "series_edit", {"id": found["series_id"], "every": every}
        return kind, {"id": found["series_id"]}
    if kind == "edit":
        _, _, field, n = action
        values: dict[str, Any] = {
            "duration": {"duration_min": 15 * (1 + n % 16)},
            "due": {"due": at(n % 5, 32 + n % 56)},
            "importance": {"importance": 1 + n % 5},
            "title": {"title": TITLES[n % len(TITLES)]},
            "times": {"start": at(n % 5, 32 + n % 48), "end": at(n % 5, 32 + n % 48 + 1 + n % 8)},
            "preset": {"preset": PRESETS[1 + n % (len(PRESETS) - 1)]},
            "elastic": {"amount": "elastic", "min_min": 30, "ideal_min": 45, "max_min": 60 + 15 * (n % 4)},
        }[field]
        return "edit", {"id": item} | values
    raise AssertionError(kind)


def tables(conn: sqlite3.Connection) -> dict[str, list[tuple]]:
    names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    return {name: sorted(map(tuple, conn.execute(f"SELECT * FROM {name}")), key=repr) for name in names}


def row(conn: sqlite3.Connection, table: str, key: dict[str, Any]) -> dict[str, Any] | None:
    found = conn.execute(f"SELECT * FROM {table} WHERE {' AND '.join(f'{k} = ?' for k in key)}", list(key.values()))
    first = found.fetchone()
    return dict(first) if first is not None else None


def before_each_row(undo_data: str | None) -> dict[str, tuple[str, dict[str, Any], dict[str, Any] | None]]:
    """For each row a command wrote: its table, key and what it was before the command (None: it didn't exist)."""
    out: dict[str, tuple[str, dict[str, Any], dict[str, Any] | None]] = {}
    for change in json.loads(undo_data or "[]"):
        name = json.dumps([change["table"], change["key"]], sort_keys=True)
        if name not in out:  # the first write to a row saw it as it was before the command
            out[name] = (change["table"], change["key"], None if change["op"] == "insert" else change["before"])
    return out


# What a replan writes, and the log itself: not what a command or its undo is about.
NOT_UNDONE = {"command_log", "plans", "blocks", "comparisons", "sqlite_sequence"}
# Notes for the next replan, which takes them, and the plan generation, which only ever counts up (undo too).
PASSING = ("next_stability", "next_cold", "generation")


def kept(conn: sqlite3.Connection) -> dict[str, list[tuple]]:
    """Every table a command or an undo writes."""
    out = {name: found for name, found in tables(conn).items() if name not in NOT_UNDONE}
    out["kv"] = [r for r in out["kv"] if r[1] not in PASSING]
    return out


def run_undo(app: App, back: int, setup: int, before: dict[int, dict[str, list[tuple]]]) -> None:
    """Undo a random earlier command (not the app's setup): afterwards each row it wrote is as it was before it, or
    undo was refused and nothing changed. Undoing the newest command puts every table back as it was before it."""
    logged = [r[0] for r in app.conn.execute("SELECT id FROM command_log WHERE id > ? ORDER BY id", [setup])]
    if not logged:
        return
    target = logged[-min(back, len(logged))]
    (undo_data,) = app.conn.execute("SELECT undo FROM command_log WHERE id = ?", [target]).fetchone()
    was = tables(app.conn)
    try:
        app.do("undo", command_id=target)
    except FieldError:
        assert tables(app.conn) == was, f"a refused undo of C{target} changed the database"
        return
    for table, key, then in before_each_row(undo_data).values():
        if table == "kv" and key.get("key") in PASSING:
            continue
        assert row(app.conn, table, key) == then, f"undo of C{target} left {table} {key} as it was after"
    if target == logged[-1] and target in before:
        now = kept(app.conn)
        changed = {t for t in now if now[t] != before[target][t]}
        assert not changed, f"undoing C{target}, the newest command, left {sorted(changed)} changed"
    check_items(app)


def run_whatif(app: App, staged_actions: list[Action], keep: bool, before: dict[int, dict[str, list[tuple]]]) -> None:
    changes = []
    for action in staged_actions:
        change = change_of(app, action)
        if change is not None and change[0] in ("add", "edit", "series_add", "shove", "rule_add", "pin", "unpin",
                                                "skip", "drop"):  # fmt: skip
            changes.append({"command": change[0], "input": change[1]})
    if not changes:
        return
    if keep:
        run_command(app, "whatif_keep", {"changes": changes}, before)
        return
    was = tables(app.conn)
    app.do("whatif", changes=changes, start=f"{DAYS[0]}T00:00", end="2026-10-26T00:00")
    assert tables(app.conn) == was, "What if changed the database"


def run_preview(app: App, action: Action, how: bool | str) -> None:
    """A command previewed (as the app does before you confirm) changes nothing, whether it would succeed or not."""
    change = change_of(app, action)
    if change is None:
        return
    was = tables(app.conn)
    with contextlib.suppress(FieldError):
        app.full(change[0], payload=change[1], preview=how)
    assert tables(app.conn) == was, f"previewing {change[0]} changed the database"


def run_command(app: App, name: str, payload: dict[str, Any], before: dict[int, dict[str, list[tuple]]]) -> None:
    """Run it; a refusal (FieldError) must leave the database exactly as it was, and what it keeps must be items
    `add` and `edit` would accept. `before` gets the tables as they were before it, by its command id."""
    was = tables(app.conn)
    try:
        app.do(name, **payload)
    except FieldError:
        assert tables(app.conn) == was, f"a refused {name} changed the database"
    else:
        if app.results[-1].command_id is not None:
            before[app.results[-1].command_id] = {t: r for t, r in was.items() if t not in NOT_UNDONE} | {
                "kv": [r for r in was["kv"] if r[1] not in PASSING]
            }
    check_items(app)


def check_items(app: App) -> None:
    for found in app.conn.execute("SELECT * FROM items WHERE status = 'todo'"):
        try:
            validate(item_from_row(dict(found)))
        except FieldError as error:
            raise AssertionError(f"T{found['id']} {found['title']!r} is kept but invalid: {error}") from error


def walls(conn: sqlite3.Connection, now_utc: int) -> list[tuple[int, int, str]]:
    """The time the planner walls off, as it builds the problem: each event that blocks time with the time kept around
    it, and each night's sleep."""
    problem = build_problem(build_input(take_snapshot(conn, now_utc)))
    events = [(f.blocked_lo, f.blocked_hi, f.title) for f in problem.fixed if f.blocks_time]
    return events + [(*night.core, f"the night of {day}") for day, night in problem.nights.items()]


def left_minutes(conn: sqlite3.Connection, now_utc: int) -> dict[int, int]:
    """What's left of each fixed-length or flexible item, from its (cushioned) length less the work recorded on it."""
    snapshot = take_snapshot(conn, now_utc)
    done: dict[int, int] = {}
    for r in conn.execute("SELECT item_id, minutes FROM progress"):
        done[r[0]] = done.get(r[0], 0) + r[1]
    out = {}
    for item in snapshot.items:
        size = {"fixed": item.duration_units, "elastic": item.max_units}.get(item.amount)
        if item.when != "fixed" and size is not None:
            out[item.id] = size * UNIT_MIN - done.get(item.id, 0)
    return out


def check_plan(app: App) -> None:
    """The saved plan's blocks from now on: only items still to do, never on a walled-off event, never more than
    what's left of an item (a quarter hour more where a half-hour slot holds the last quarter)."""
    saved = current_plan(app.conn, 1)
    if saved is None:
        return
    statuses = {r[0]: (r[1], r[2]) for r in app.conn.execute("SELECT id, status, when_kind FROM items")}
    walled = walls(app.conn, app.now_utc)
    left = left_minutes(app.conn, app.now_utc)
    planned: dict[int, int] = {}
    for b in app.conn.execute("SELECT * FROM blocks WHERE plan_id = ?", [saved["id"]]):
        start, end = max(parse_utc(b["start_utc"]), app.now_utc), parse_utc(b["end_utc"])
        if end <= start:
            continue  # the past: what was planned then
        status, when = statuses[b["item_id"]]
        assert status == "todo" and when != "fixed", f"T{b['item_id']} ({status}, {when}) planned {b['start_utc']}"
        for lo, hi, title in walled:
            assert not (lo < end and start < hi), (
                f"T{b['item_id']} planned {format_utc(start)}–{format_utc(end)} over {title} "
                f"{format_utc(lo)}–{format_utc(hi)}"
            )
        planned[b["item_id"]] = planned.get(b["item_id"], 0) + end - start
    for item_id, minutes in planned.items():
        if item_id in left:
            assert minutes <= max(0, left[item_id]) + UNIT_MIN, (
                f"T{item_id}: {minutes} min planned, {left[item_id]} left"
            )


def play(app: App, actions: list[Action]) -> None:
    (setup,) = app.conn.execute("SELECT coalesce(max(id), 0) FROM command_log").fetchone()
    before: dict[int, dict[str, list[tuple]]] = {}
    for action in actions:
        kind = action[0]
        if kind == "undo":
            run_undo(app, action[1], setup, before)
        elif kind == "tick":
            app.now_utc += action[1]
        elif kind == "replan":
            replan(app.conn, app.now_utc)
            check_plan(app)
        elif kind in ("whatif", "keep"):
            run_whatif(app, action[1], kind == "keep", before)
        elif kind == "preview":
            run_preview(app, action[1], action[2])
        else:
            change = change_of(app, action)
            if change is not None:
                run_command(app, *change, before)
    replan(app.conn, app.now_utc)
    check_plan(app)


@pytest.fixture
def fresh(tmp_path_factory: pytest.TempPathFactory) -> Callable[[], App]:
    def make() -> App:
        app = new_app(tmp_path_factory.mktemp("sequence"), horizon_days=4)
        app.do(
            "settings_set",
            key="engine",
            value={"chains": 1, "step_budgets": [{"max_items": 1000, "cold": 8000, "warm": 4000}],
                   "repair_steps": 20_000, "fallback_s": 0.5},
        )  # fmt: skip
        whatif.BEFORE.clear()
        return app

    return make


@settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large, HealthCheck.function_scoped_fixture],
)
@given(actions=st.lists(ACTIONS, min_size=2, max_size=12))
def test_random_command_sequences_keep_their_promises(fresh: Callable[[], App], actions: list[Action]) -> None:
    play(fresh(), actions)
