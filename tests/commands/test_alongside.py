"""Working on two things at once (2 Nov: "make support for working on two things at once even if friday didn't
originally plan to"). Monday 19 Oct 2026, 9am, New York; the clock moves by hand.

Black box: through the commands and queries only, as the app and the CLI use them. Glass box (marked so below): the
timer rows, the planner's snapshot and its progress, undo's keys, and the migration that made room for them."""

import sqlite3
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from friday.commands.timer import MAX_AT_ONCE
from friday.core.db import MIGRATIONS, connect
from friday.core.items import FieldError
from friday.core.time import parse_utc
from friday.planner.prepare import progress_minutes
from friday.planner.snapshot import take_snapshot
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def task(app: App, title: str, minutes: int = 120) -> int:
    return app.do("add", title=title, duration_min=minutes)["item"]["id"]


def timing(app: App) -> tuple[int | None, list[int]]:
    s = app.do("status")
    return (s["timer"] or {}).get("item_id"), [t["item_id"] for t in s["alongside"]]


def timed_minutes(app: App, item: int) -> int:
    return sum(r["minutes"] for r in app.table("progress") if r["item_id"] == item and r["source"] == "timer")


class TestBlackBox:
    def test_starting_alongside_keeps_what_you_were_timing(self, app: App) -> None:
        reading, laundry = task(app, "reading"), task(app, "laundry", 60)
        app.do("start", id=reading)
        out = app.at("2026-10-19T09:05").do("start", id=laundry, alongside=True)
        assert out["message"] == "Timing laundry, alongside reading" and out["title"] == "laundry"
        assert timing(app) == (laundry, [reading])
        status = app.do("status")
        assert status["alongside"][0]["title"] == "reading" and status["alongside"][0]["minutes"] == 5

    def test_each_gets_the_whole_time_it_ran(self, app: App) -> None:
        reading, laundry = task(app, "reading"), task(app, "laundry", 60)
        app.do("start", id=reading)
        app.at("2026-10-19T09:10").do("start", id=laundry, alongside=True)
        app.at("2026-10-19T10:00").do("stop", id=laundry)
        app.at("2026-10-19T10:30").do("stop")
        assert (timed_minutes(app, reading), timed_minutes(app, laundry)) == (90, 50)
        assert timing(app) == (None, [])

    def test_a_plain_start_still_switches_stopping_everything(self, app: App) -> None:
        a, b, c = task(app, "a"), task(app, "b"), task(app, "c")
        app.do("start", id=a)
        app.do("start", id=b, alongside=True)
        app.at("2026-10-19T09:30").do("start", id=c)
        assert timing(app) == (c, []) and timed_minutes(app, a) == timed_minutes(app, b) == 30

    def test_stop_without_naming_one_stops_the_last_started_and_the_other_takes_over(self, app: App) -> None:
        a, b = task(app, "a"), task(app, "b")
        app.do("start", id=a)
        app.do("start", id=b, alongside=True)
        assert app.at("2026-10-19T09:20").do("stop")["item_id"] == b
        assert timing(app) == (a, [])

    def test_done_on_one_alongside_finishes_only_it(self, app: App) -> None:
        a, b = task(app, "a"), task(app, "b")
        app.do("start", id=a)
        app.do("start", id=b, alongside=True)
        out = app.at("2026-10-19T09:40").do("stop", id=a, done=True)
        assert out["message"] == "Stopped a after 40 min and marked it done"
        assert app.do("item", id=a)["item"]["status"] == "done" and timing(app) == (b, [])

    def test_marking_one_done_from_its_card_stops_its_timer_not_the_other(self, app: App) -> None:
        a, b = task(app, "a"), task(app, "b")
        app.do("start", id=a)
        app.do("start", id=b, alongside=True)
        app.at("2026-10-19T09:15").do("done", id=a)
        assert timing(app) == (b, []) and timed_minutes(app, a) == 15 and timed_minutes(app, b) == 0

    def test_at_most_three_at_once(self, app: App) -> None:
        ids = [task(app, f"t{n}") for n in range(MAX_AT_ONCE + 1)]
        app.do("start", id=ids[0])
        for item in ids[1:MAX_AT_ONCE]:
            app.do("start", id=item, alongside=True)
        with pytest.raises(FieldError, match="3 things are being timed already"):
            app.do("start", id=ids[MAX_AT_ONCE], alongside=True)
        assert len(app.table("timer")) == MAX_AT_ONCE

    def test_starting_one_that_runs_already_makes_it_the_timer_without_a_second_copy(self, app: App) -> None:
        a, b = task(app, "a"), task(app, "b")
        app.do("start", id=a)
        app.do("start", id=b, alongside=True)
        app.at("2026-10-19T09:10").do("start", id=a, alongside=True)
        assert timing(app) == (a, [b]) and timed_minutes(app, a) == 10 and len(app.table("timer")) == 2

    def test_stopping_one_that_isnt_timed_says_so(self, app: App) -> None:
        a, b = task(app, "a"), task(app, "b")
        app.do("start", id=a)
        assert app.do("stop", id=b)["message"] == f"T{b} isn't being timed"
        assert timing(app) == (a, [])

    def test_undo_takes_back_only_the_one_started_alongside(self, app: App) -> None:
        a, b = task(app, "a"), task(app, "b")
        app.do("start", id=a)
        app.do("start", id=b, alongside=True)
        app.do("undo", command_id=app.results[-1].command_id)
        assert timing(app) == (a, [])

    def test_deleting_a_thing_being_timed_alongside_leaves_the_other_running(self, app: App) -> None:
        a, b = task(app, "a"), task(app, "b")
        app.do("start", id=a)
        app.do("start", id=b, alongside=True)
        app.at("2026-10-19T09:20").do("drop", id=b)
        assert timing(app) == (a, []) and timed_minutes(app, b) == 20  # its time is kept

    def test_starting_alongside_teaches_no_choice_of_one_over_another(self, app: App) -> None:
        a, b = task(app, "a"), task(app, "b")
        app.do("replan")
        app.do("start", id=a)
        before = app.conn.execute("SELECT value FROM kv WHERE key = 'order_choices'").fetchone()
        app.do("start", id=b, alongside=True)
        after = app.conn.execute("SELECT value FROM kv WHERE key = 'order_choices'").fetchone()
        assert before == after

    def test_the_plan_counts_what_runs_alongside_as_being_done(self, app: App) -> None:
        reading, laundry = task(app, "reading", 120), task(app, "laundry", 60)
        app.do("start", id=reading)
        app.do("start", id=laundry, alongside=True)
        app.at("2026-10-19T09:45").do("replan")
        plan = app.conn.execute("SELECT id FROM plans WHERE status = 'current'").fetchone()["id"]
        ahead = [
            (r["item_id"], parse_utc(r["end_utc"]) - max(parse_utc(r["start_utc"]), app.now_utc))
            for r in app.table("blocks")
            if r["plan_id"] == plan and parse_utc(r["end_utc"]) > app.now_utc
        ]
        assert sum(m for i, m in ahead if i == reading) <= 120 - 45 + 15  # 45 min of it done while laundry ran
        assert any(i == laundry for i, _ in ahead)  # laundry, the timer, is held from now


class TestGlassBox:
    def test_the_last_started_is_the_snapshot_s_timer_the_rest_alongside_in_order(self, app: App) -> None:
        a, b, c = task(app, "a"), task(app, "b"), task(app, "c")
        app.do("start", id=a)
        app.at("2026-10-19T09:01").do("start", id=b, alongside=True)
        app.at("2026-10-19T09:02").do("start", id=c, alongside=True)
        snapshot = take_snapshot(app.conn, app.now_utc)
        assert snapshot.timer is not None and snapshot.timer[0] == c
        assert [t[0] for t in snapshot.alongside] == [a, b]

    def test_alongside_minutes_count_as_progress_but_only_the_timer_is_held(self, app: App) -> None:
        reading, laundry = task(app, "reading", 120), task(app, "laundry", 60)
        app.do("start", id=reading)
        app.do("start", id=laundry, alongside=True)
        app.at("2026-10-19T09:30")
        total, today = progress_minutes(take_snapshot(app.conn, app.now_utc))
        assert total[reading] == 30 and today[reading] == 30  # alongside: half an hour of reading done
        assert total[laundry] == 30  # the timer: within its hold, all of it counts

    def test_undo_keys_a_timer_by_its_item(self, app: App) -> None:
        from friday.commands.writer import TABLE_KEYS  # noqa: PLC0415

        assert TABLE_KEYS["timer"] == ("user_id", "item_id")

    def test_the_migration_keeps_a_running_timer_and_allows_one_per_item(self, tmp_path: Path) -> None:
        conn = sqlite3.connect(tmp_path / "old.db")
        conn.row_factory = sqlite3.Row
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if int(path.name.split("_")[0]) < 23:
                conn.executescript(f"BEGIN;\n{path.read_text()}\nPRAGMA user_version = {int(path.name[:3])};\nCOMMIT;")
        conn.execute(
            "INSERT INTO items (id, title, when_kind, amount, shape, created_utc, updated_utc) "
            "VALUES (7, 'essay', 'window', 'fixed', 'split', '2026-10-19T13:00Z', '2026-10-19T13:00Z')"
        )
        conn.execute("INSERT INTO timer (item_id, start_utc) VALUES (7, '2026-10-19T13:00:05Z')")
        conn.commit()
        conn.close()
        upgraded = connect(tmp_path / "old.db")
        assert [tuple(r) for r in upgraded.execute("SELECT user_id, item_id, start_utc FROM timer")] == [
            (1, 7, "2026-10-19T13:00:05Z")
        ]
        upgraded.execute(
            "INSERT INTO items (id, title, when_kind, amount, shape, created_utc, updated_utc) "
            "VALUES (8, 'laundry', 'window', 'fixed', 'split', '2026-10-19T13:00Z', '2026-10-19T13:00Z')"
        )
        upgraded.execute("INSERT INTO timer (item_id, start_utc) VALUES (8, '2026-10-19T13:01:00Z')")
        with pytest.raises(sqlite3.IntegrityError):
            upgraded.execute("INSERT INTO timer (item_id, start_utc) VALUES (8, '2026-10-19T13:02:00Z')")


SHORTEST = 5
ACTIONS = st.lists(
    st.tuples(st.sampled_from(["start", "alongside", "stop", "stop_one", "done"]), st.integers(0, 4),
              st.integers(1, 20)),
    max_size=14,
)  # fmt: skip


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(ACTIONS)
def test_any_taps_keep_their_promises(tmp_path_factory: pytest.TempPathFactory, actions: list) -> None:
    """Black box, any order of taps: never more than three at once, nothing twice, the timer the last started, and
    every minute each thing ran recorded for it (five or more at a time), whichever ran beside it."""
    app = new_app(tmp_path_factory.mktemp("taps"))
    ids = [task(app, f"t{n}") for n in range(5)]
    since: dict[int, int] = {}
    owed = dict.fromkeys(ids, 0)
    for action, n, wait in actions:
        app.now_utc += wait
        item = ids[n]
        open_ = app.do("item", id=item)["item"]["status"] == "todo"

        def stop(which: int) -> None:
            ran = app.now_utc - since.pop(which)
            owed[which] += ran if ran >= SHORTEST else 0  # under five minutes isn't a sitting

        if action in ("start", "alongside") and open_:
            if action == "alongside" and item not in since and len(since) >= MAX_AT_ONCE:
                with pytest.raises(FieldError):
                    app.do("start", id=item, alongside=True)
                continue
            app.do("start", id=item, alongside=action == "alongside")
            if item in since:
                stop(item)
            if action == "start":
                for other in list(since):
                    stop(other)
            since[item] = app.now_utc
        elif action == "stop" and since:
            last = max(since, key=lambda k: (since[k], list(since).index(k)))
            app.do("stop")
            stop(last)
        elif action == "stop_one":
            app.do("stop", id=item)
            if item in since:
                stop(item)
        elif action == "done" and open_:
            app.do("done", id=item)
            if item in since:
                stop(item)
        timer, alongside = timing(app)
        assert len(since) <= MAX_AT_ONCE and set(since) == {*alongside, *([timer] if timer else [])}
        assert len(alongside) == len(set(alongside)) and timer not in alongside
        if since:
            assert since[timer] == max(since.values())
    for item in ids:
        assert timed_minutes(app, item) == owed[item]
