"""What the web app needs: the calendar (sleep, axis, paces, dues), areas, waiting items, item history, day shoves."""

from pathlib import Path

from tests.commands.helpers import new_app


def test_days_carry_sleep_caps_and_a_pace_off_the_default(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    app.do("pace", name="Easy", for_days=2)
    out = app.do("calendar", days=7)
    assert out["today"] == "2026-10-19" and out["now"] == "2026-10-19T09:00"
    friday, saturday = out["days"][4], out["days"][5]
    night = [friday["bedtime"], friday["core"], friday["wake"]]
    assert night == ["2026-10-23T23:30", "2026-10-24T00:30", "2026-10-24T09:00"]
    assert saturday["bedtime"] == "2026-10-25T00:30"  # after midnight
    assert [d["pace"] for d in out["days"][:3]] == ["Easy", "Easy", None]
    assert out["days"][0]["cap_hours"] == 10


def test_the_axis_runs_from_the_earliest_wake_to_the_latest_core_sleep(tmp_path: Path) -> None:
    out = new_app(tmp_path).do("calendar", days=7)
    assert (out["axis_start_min"], out["axis_end_min"]) == (7 * 60 + 30, 25 * 60 + 30)


def test_due_markers_fall_in_the_range(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    app.do("add", text="essay due wed 17:00 ~2h")
    app.do("add", text="thesis due dec 1 ~10h")
    out = app.do("calendar", days=3)
    assert [(d["title"], d["due"]) for d in out["dues"]] == [("essay", "2026-10-21T17:00")]


def test_areas_list_their_colours(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    app.do("area_add", name="CS", color="#3b82f6")
    assert [(a["name"], a["color"]) for a in app.do("areas")] == [("CS", "#3b82f6")]


def test_items_list_what_they_are_waiting_on(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    draft = app.do("add", text="draft ~1h")["item"]["id"]
    edit = app.do("add", text="edit ~1h", after=[draft])["item"]["id"]
    waiting = {i["id"]: i["waiting_on"] for i in app.do("items")}
    assert waiting == {draft: [], edit: [draft]}
    app.do("done", id=draft)
    assert app.do("items")[0]["waiting_on"] == []


def test_the_log_lists_one_items_commands(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    essay = app.do("add", text="essay ~1h")["item"]["id"]
    app.do("add", text="laundry ~1h")
    app.do("depend", item_id=essay + 1, depends_on_id=essay)
    app.do("done", id=essay)
    assert [e["command"] for e in app.do("log_list", item_id=essay)] == ["done", "depend", "add"]


def test_a_time_range_can_name_its_day(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    created = app.do("shove", range="12:00-13:30 wed")["created"]
    assert [(i["start_utc"], i["end_utc"]) for i in app.table("items") if i["id"] in created] == [
        ("2026-10-21T16:00Z", "2026-10-21T17:30Z")
    ]


def test_a_time_range_can_be_days_from_today(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    out = app.do("shove", range="14:00-16:30 +2d", decision="shove_anyway")
    created = out["created"]
    assert out["message"] == "Cleared Wed Oct 21 2–4:30pm" and out["day"] == "2026-10-21"
    assert [(i["start_utc"], i["end_utc"]) for i in app.table("items") if i["id"] in created] == [
        ("2026-10-21T18:00Z", "2026-10-21T20:30Z")
    ]


def test_only_blocks_on_a_pin_show_as_pinned(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    essay = app.do("add", text="essay ~2h split")["item"]["id"]
    app.do("pin", id=essay, start="2026-10-20T10:00", end="2026-10-20T11:00", kind="preferred")
    app.do("replan")
    shown = {b["start"]: b["pinned"] for b in app.do("plan")["blocks"] if b["item_id"] == essay}
    assert shown["2026-10-20T10:00"] == "preferred" and list(shown.values()).count(None) == len(shown) - 1


def test_a_deleted_items_blocks_leave_the_calendar_before_the_replan(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    essay = app.do("add", text="essay ~2h due fri")["item"]["id"]
    app.do("replan")
    assert any(b["item_id"] == essay for b in app.do("plan")["blocks"])
    app.do("drop", id=essay)  # no replan yet
    assert not any(b["item_id"] == essay for b in app.do("plan")["blocks"])


def test_touching_blocks_of_one_item_show_as_one(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    essay = app.do("add", text="essay ~2h due fri")["item"]["id"]
    app.do("replan")
    plan_id = app.do("plan")["plan_id"]
    (block,) = [b for b in app.do("plan")["blocks"] if b["item_id"] == essay]
    app.conn.execute("DELETE FROM blocks WHERE plan_id = ? AND item_id = ?", [plan_id, essay])
    for start, end in (("14:00", "15:00"), ("15:00", "15:15"), ("15:15", "16:00")):  # as replans leave them
        app.conn.execute(
            "INSERT INTO blocks (plan_id, item_id, start_utc, end_utc, cost) VALUES (?, ?, ?, ?, '{}')",
            [plan_id, essay, f"2026-10-19T{start}Z", f"2026-10-19T{end}Z"],
        )
    shown = [b for b in app.do("plan")["blocks"] if b["item_id"] == essay]
    assert [(b["start"][11:], b["end"][11:]) for b in shown] == [("10:00", "12:00")] and block["title"] == "essay"


def test_events_are_found_by_title_once_per_series_at_their_next_time(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    app.do("add", title="CS 2110 Lecture", when="fixed", start="2026-10-12T11:40", end="2026-10-12T12:55")
    app.do("add", title="CS 2110 Lecture", when="fixed", start="2026-10-21T11:40", end="2026-10-21T12:55")
    app.do("add", title="Dentist", when="fixed", start="2026-10-23T15:00", end="2026-10-23T16:00")
    found = app.do("events", text="lecture")
    assert [(e["title"], e["start"]) for e in found] == [
        ("CS 2110 Lecture", "2026-10-21T11:40"),
        ("CS 2110 Lecture", "2026-10-12T11:40"),
    ]
    assert app.do("events", text="dent")[0]["start"] == "2026-10-23T15:00"
    assert app.do("events", text="") == []


def test_an_event_wears_a_pigment_until_you_clear_it(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    event = app.do("add", title="Chess club", when="fixed", start="2026-10-21T19:00", end="2026-10-21T21:00")["item"]
    assert event["color"] is None
    assert app.do("edit", id=event["id"], color="violet")["item"]["color"] == "violet"
    assert app.do("edit", id=event["id"], color=None)["item"]["color"] is None
    try:
        app.do("edit", id=event["id"], color="chartreuse")
    except Exception as error:
        assert "color" in str(error)
    else:
        raise AssertionError("an unknown pigment was taken")


def test_an_event_says_its_category_and_whether_it_counts_as_busy(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    app.do(
        "settings_set",
        key="categories",
        value={"categories": [{"name": "Advising", "color": "green", "pattern": "office hours"}],
               "filter": {"label": "TA hours", "pattern": "office hours"}},
    )  # fmt: skip
    app.do("add", title="CS 2110 Office Hours", when="fixed", start="2026-10-21T13:00", end="2026-10-21T15:00")
    app.do("add", title="Lunch", when="fixed", start="2026-10-21T12:00", end="2026-10-21T13:00", free=True)
    hours, lunch = app.do("events", text="office")[0], app.do("events", text="lunch")[0]
    assert (hours["category"], hours["category_color"], hours["left_out"]) == ("Advising", "green", "filtered")
    assert lunch["left_out"] == "free"
    app.do("settings_set", key="busy", value={"count_filtered": True})
    assert app.do("events", text="office")[0]["left_out"] is None


def test_events_left_out_block_no_time_when_planning(tmp_path: Path) -> None:
    from friday.core.items import Item
    from friday.core.settings import DEFAULTS
    from friday.planner.snapshot import busy_as_you_count

    reminder = Item(title="PS 8 due", when="fixed", start_utc="2026-10-21T16:00Z", end_utc="2026-10-21T17:00Z", id=1)
    lecture = Item(title="Lecture", when="fixed", start_utc="2026-10-21T16:00Z", end_utc="2026-10-21T17:00Z", id=2)
    assert not busy_as_you_count(reminder, DEFAULTS, {}).blocks_time
    assert busy_as_you_count(lecture, DEFAULTS, {}).blocks_time
    assert not busy_as_you_count(lecture, DEFAULTS, {2: "Library Rooms"}).blocks_time


def test_a_shove_after_midnight_belongs_to_the_night_before(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    out = app.do("shove", range="01:00-02:00 +3d", decision="shove_anyway")
    assert out["day"] == "2026-10-21"  # Thursday 1am is Wednesday night until the day starts at 4am


def test_status_lists_what_will_be_late_soonest_due_first(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    app.do("add", text="essay ~6h", release="2026-10-19T09:00", due="2026-10-19T11:00")
    app.do("add", text="lab report ~5h", release="2026-10-19T09:00", due="2026-10-19T10:00")
    app.do("replan")
    late = app.do("status")["late_items"]
    assert [i["title"] for i in late] == ["lab report", "essay"] and late[0]["due"] == "2026-10-19T10:00"
    assert all(i["hours"] > 0 for i in late) and set(app.do("status")["late"]) == {"lab report", "essay"}


def test_the_plan_shows_what_you_timed_when_you_did_it(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    essay = app.do("add", text="essay ~2h due fri")["item"]["id"]
    app.do("start", id=essay)
    app.at("2026-10-19T09:19").do("stop")
    app.at("2026-10-19T09:30").do("start", id=essay)
    app.at("2026-10-19T09:45").do("stop")
    # A replan cuts a running timer's record in two; touching pieces read as one sitting.
    app.conn.execute(
        "INSERT INTO progress (user_id, item_id, start_utc, end_utc, minutes, source, created_utc) "
        "VALUES (1, ?, '2026-10-19T13:45Z', '2026-10-19T13:50Z', 5, 'timer', '2026-10-19T13:50Z')",
        [essay],
    )
    plan = app.do("plan", start="2026-10-19T00:00", end="2026-10-20T00:00")
    assert [(s["key"], s["start"], s["end"]) for s in plan["sessions"]] == [
        (f"S{essay}@2026-10-19T09:00", "2026-10-19T09:00", "2026-10-19T09:19"),
        (f"S{essay}@2026-10-19T09:30", "2026-10-19T09:30", "2026-10-19T09:50"),
    ]
    assert plan["sessions"][0]["title"] == "essay"
    assert app.do("plan", start="2026-10-20T00:00", end="2026-10-21T00:00")["sessions"] == []
