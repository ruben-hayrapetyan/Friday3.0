"""Notifications (DESIGN §20): what goes out when, buttons that work once, settling a block early, the brief and
the weekly review."""

from pathlib import Path

import pytest

from friday.commands.delivery import deliver
from friday.commands.notify import due_notifications, make_token
from friday.core.items import FieldError
from friday.planner.service import replan
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, now="2026-10-19T08:05", horizon_days=3)


def kinds(app: App) -> list[str]:
    return sorted(o.kind for o in due_notifications(app.conn, app.now_utc))


def sent(app: App, tmp_path: Path) -> list[dict]:
    deliver(app.conn, app.now_utc, tmp_path)
    return app.do("notifications")


def test_the_brief_goes_out_half_an_hour_after_waking_once(app: App, tmp_path: Path) -> None:
    app.do("add", text="essay due tue 17:00 ~2h")
    replan(app.conn, app.now_utc)
    assert kinds(app) == ["morning_brief"]
    assert [n["title"] for n in sent(app, tmp_path)] == ["Today"]
    assert kinds(app) == []  # once a day


def test_quiet_hours_hold_back_all_but_urgent_ones(app: App) -> None:
    app.do("notify_test")
    app.at("2026-10-19T23:45")
    assert kinds(app) == ["test"]


def test_the_evening_review_waits_until_an_hour_before_bed_and_only_if_not_reviewed(app: App) -> None:
    app.at("2026-10-19T22:35")
    assert "evening_review" in kinds(app)
    app.do("review_submit")
    assert "evening_review" not in kinds(app)


def test_low_slack_offers_start_and_its_button_works_once(app: App, tmp_path: Path) -> None:
    item = app.do("add", text="essay due mon 11:30 ~2h")["item"]["id"]
    replan(app.conn, app.now_utc)
    outgoing = {o.kind: o for o in due_notifications(app.conn, app.now_utc)}
    assert outgoing["slack_low"].actions[0] == ("Start", f"start:{item}")
    deliver(app.conn, app.now_utc, tmp_path)
    notification = app.table("notifications")[-1]["id"]  # its token rides on the push; mint one the same way
    pressed = make_token(app.conn, notification, f"start:{item}", app.now_utc)
    assert app.do("act", token=pressed)["message"] == "Timer started"
    assert app.do("status")["timer"]["item_id"] == item
    assert app.table("notifications")[-1]["acted"] == 1
    with pytest.raises(FieldError, match="already used"):
        app.do("act", token=pressed)
    with pytest.raises(FieldError, match="not a Friday token"):
        app.do("act", token=pressed[:-2] + "xx")


def test_after_the_last_block_before_a_hard_due_it_asks_and_not_yet_puts_the_work_back(app: App) -> None:
    item = app.do("add", text="essay due mon 17:00 ~1h")["item"]["id"]
    app.do("pin", id=item, start="2026-10-19T09:00", kind="locked")
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T10:20")
    check = next(o for o in due_notifications(app.conn, app.now_utc) if o.kind == "check")
    assert check.title == "Did you finish essay?" and check.urgent
    replan(app.conn, app.now_utc)
    assert future_blocks(app, item) == []  # assumed done until told otherwise
    _, action = check.actions[1]
    app.do("settle", block_key=action.split(":", 1)[1].rsplit(":", 1)[0], status="not_done")
    replan(app.conn, app.now_utc)
    assert future_blocks(app, item) and all(end <= "2026-10-19T17:00" for end in future_blocks(app, item))
    assert "check" not in kinds(app)


def future_blocks(app: App, item: int) -> list[str]:
    return [b["end"] for b in app.do("plan")["blocks"] if b["item_id"] == item and b["start"] >= app.local_now()]


def test_a_settled_block_keeps_its_answer_through_the_review(app: App) -> None:
    item = app.do("add", text="essay due tue 17:00 ~1h")["item"]["id"]
    app.do("pin", id=item, start="2026-10-19T09:00", kind="locked")
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00")
    key = f"T{item}@2026-10-19T09:00"
    app.do("settle", block_key=key, status="partial", share=0.5)
    assert app.do("review")["settled"] == {key: 30}
    app.do("review_submit")
    assert app.do("item", id=item)["item"]["done_min"] == 30


def test_the_daily_cap_holds_back_the_ordinary_ones(app: App) -> None:
    app.do("settings_set", key="notify", value={"max_per_day": 0})
    app.do("notify_test")
    assert kinds(app) == ["test"]  # the brief waits; a test isn't counted


def test_the_brief_names_todays_big_rocks(app: App) -> None:
    app.do("add", text="essay due tue 17:00 ~2h")
    app.do("add", text="lecture at mon 14:00 for 1h")
    replan(app.conn, app.now_utc)
    brief = app.do("brief")
    assert [r["title"] for r in brief["rocks"]] == ["essay"] and len(brief["fixed"]) == 1
    assert brief["text"].startswith(brief["summary"]) and "essay" in brief["text"]


def test_the_week_compares_plan_and_record_by_area_and_scores_deadlines(app: App) -> None:
    app.do("area_add", name="CS")
    item = app.do("add", text="PS1 #CS due mon 17:00 ~1h")["item"]["id"]
    app.do("pin", id=item, start="2026-10-19T09:00", kind="locked")
    replan(app.conn, app.now_utc)
    app.do("log", id=item, start="2026-10-19T09:00", end="2026-10-19T10:30")
    app.at("2026-10-19T11:00").do("done", id=item)
    week = app.do("week_review")
    assert (week["start"], week["end"]) == ("2026-10-19", "2026-10-25")
    assert [(a["area"], a["actual_h"]) for a in week["areas"]] == [("CS", 1.5)]
    assert [(d["title"], d["outcome"]) for d in week["deadlines"]] == [("PS1", "on_time")]
    assert week["moves"] == 1


def test_the_weekly_review_lists_finished_carried_and_coming_and_keeps_a_note(app: App) -> None:
    done = app.do("add", text="PS1 due mon 17:00 ~1h")["item"]["id"]
    app.do("add", text="essay due mon 23:00 ~3h")  # planned today, so it carries over
    app.do("add", title="next essay", due="2026-10-27T17:00", duration_min=60)
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T11:00").do("done", id=done)
    app.do("week_note", week="2026-10-19", feel="Busy", notes="Start essays earlier")
    week = app.do("week_review")
    assert [f["title"] for f in week["finished"]] == ["PS1"]
    assert [c["title"] for c in week["carried"]] == ["essay"]
    assert [c["title"] for c in week["coming"]] == ["next essay"]
    assert week["note"] == {"feel": "Busy", "notes": "Start essays earlier"}


def test_quiet_hours_hold_all_but_urgent_ones_and_a_running_timer_holds_the_rest(app: App, tmp_path: Path) -> None:
    app.do("add", text="essay due tue 17:00 ~2h")
    replan(app.conn, app.now_utc)
    app.do("settings_set", key="notify", value={"quiet": ("08:00", "09:00")})
    assert kinds(app) == []  # 08:05: the morning brief waits
    app.do("settings_set", key="notify", value={"quiet": None, "hold_while_timing": True})
    app.do("start", id=1)
    assert kinds(app) == []  # timing: only deadline warnings get through
    app.do("stop")
    assert kinds(app) == ["morning_brief"]
