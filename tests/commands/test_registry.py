"""Every mutating command applies, previews without a trace, undoes to the same rows, refuses a stale undo, and
returns its stored result for a repeated idempotency key (DESIGN §9.2, §24.1)."""

import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from friday.commands.all import REGISTRY
from friday.commands.notify import make_token
from friday.core.items import FieldError
from friday.planner.service import replan
from tests.commands.helpers import App, new_app

# Tables a command's undo doesn't restore: the log itself, the plan generation, and derived plans.
DERIVED = {"command_log", "kv", "plans", "blocks", "users", "sqlite_sequence"}
KV_STATE = {
    "sleep_skip",
    "not_duplicates",  # kept in kv
    "review_again",
    "reviewed",
    "import_chroma_colors",  # the colours, kept in kv
    "report",  # the last 50 reports, kept in kv
    "stuck",  # the latest friction, kept in kv
    "rule_win",
    "learn_module",
    "sync_now",
    "token_remove",
    "week_note",
    "reorder",
    "rule_add",
    "event_going",
}  # commands whose whole effect is in kv, which other commands only use for counters


def state(app: App) -> dict[str, list[dict[str, Any]]]:
    tables = [r["name"] for r in app.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    return {t: app.table(t) for t in sorted(tables) if t not in DERIVED}


def essay(app: App) -> int:
    return app.do("add", text="essay due wed 5pm ~2h")["item"]["id"]


def chore(app: App) -> int:
    return app.do("add", text="laundry ~1h")["item"]["id"]


def slept(app: App) -> int:
    app.do("settings_set", key="sleep_tracking", value={"on": True})
    app.do("sleep_mark", kind="up")
    return app.do("sleep")["nights"][0]["up_id"]


def eating(app: App) -> int:
    app.do("settings_set", key="meal_tracking", value={"on": True})
    app.do("meal_log", kind="breakfast", start="2026-10-19T07:40", end="2026-10-19T08:00")
    return app.do("meals")["days"][0]["meals"][0]["id"]


def longer_lunches(app: App) -> dict[str, Any]:
    app.do("settings_set", key="meal_tracking", value={"on": True})
    app.do("series_add", title="Lunch", preset="Routine", every="day", release_offset_min=450, due_offset_min=630,
           min_min=15, ideal_min=15, max_min=15)  # fmt: skip
    for day in range(12, 19):
        app.do("meal_log", kind="lunch", start=f"2026-10-{day}T12:00", end=f"2026-10-{day}T12:45")
    return {"kind": "lunch"}


def late_lunches(app: App) -> dict[str, Any]:
    app.do("settings_set", key="meal_tracking", value={"on": True})
    app.do("series_add", title="Lunch", preset="Routine", every="day", release_offset_min=450, due_offset_min=630,
           min_min=15, ideal_min=15, max_min=15)  # fmt: skip
    for day in range(12, 19):  # 11:30am to 2:30pm planned, eaten at 1:45
        app.do("meal_log", kind="lunch", start=f"2026-10-{day}T13:45", end=f"2026-10-{day}T14:15")
    return {"kind": "lunch"}


def breakfasts(app: App) -> dict[str, Any]:
    app.do("settings_set", key="meal_tracking", value={"on": True})
    for day in range(12, 19):
        app.do("meal_log", kind="breakfast", start=f"2026-10-{day}T08:00", end=f"2026-10-{day}T08:15")
    return {"kind": "breakfast", "plan": True}


def gym(app: App) -> dict[str, Any]:
    return app.do("add", text="gym every mon,wed ~1h")


def planned(app: App) -> int:
    item_id = essay(app)
    replan(app.conn, app.now_utc)
    return item_id


def occurrence(app: App) -> int:
    series_id = gym(app)["series_id"]
    return app.conn.execute("SELECT id FROM items WHERE series_id = ? ORDER BY id LIMIT 1", [series_id]).fetchone()[0]


def a_shove(app: App) -> dict[str, Any]:
    app.do("shove", range="30m")
    return {}


def a_pin(app: App) -> int:
    item_id = chore(app)
    app.do("pin", id=item_id, start="2026-10-19T15:00")
    return item_id


def reopen_sample(app: App) -> dict[str, Any]:
    item_id = essay(app)
    app.do("done", id=item_id)
    return {"id": item_id}


def undepend_sample(app: App) -> dict[str, Any]:
    a, b = essay(app), chore(app)
    app.do("depend", item_id=a, depends_on_id=b)
    return {"item_id": a, "depends_on_id": b}


def add_sample(app: App) -> dict[str, Any]:
    return {"text": f"PS5 #cs due tue 5pm ~3h after:T{chore(app)}"}


def review_sample(app: App) -> dict[str, Any]:
    planned(app)
    app.at("2026-10-19T18:00")
    return {"entries": []}


def stop_sample(app: App) -> dict[str, Any]:
    app.do("start", id=chore(app))
    app.at("2026-10-19T09:40")
    return {"done": True}


def materialize_sample(app: App) -> dict[str, Any]:
    gym(app)
    app.at("2026-10-26T09:00")
    return {}


def close_day_sample(app: App) -> dict[str, Any]:
    app.do("pin", id=essay(app), start="2026-10-19T10:00", kind="locked")
    replan(app.conn, app.now_utc)
    app.at("2026-10-20T09:00")
    return {}


def settle_sample(app: App) -> dict[str, Any]:
    item = chore(app)
    app.do("pin", id=item, start="2026-10-19T10:00", kind="locked")
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00")
    key = next(b["key"] for b in app.do("review")["blocks"] if b["item_id"] == item)
    return {"block_key": key, "status": "not_done"}


def act_sample(app: App) -> dict[str, Any]:
    item = chore(app)
    app.conn.execute(
        "INSERT INTO notifications (kind, dedup_key, channel, sent_utc) "
        "VALUES ('slack_low', 'k', 'app', '2026-10-19T13:00Z')"
    )
    return {"token": make_token(app.conn, 1, f"start:{item}", app.now_utc)}


def subscribed(app: App) -> str:
    app.do("push_subscribe", endpoint="https://push.example/1", keys={"p256dh": "k", "auth": "a"})
    return "https://push.example/1"


def compare_sample(app: App) -> dict[str, Any]:
    app.conn.execute(
        "INSERT INTO comparisons (asked_utc, plan_a, plan_b, features_a, features_b, source, dials) "
        "VALUES ('2026-10-19T13:00Z', '{}', '{}', '{}', '{}', 'question', '{}')"
    )
    return {"id": 1, "answer": "a"}


def profile_row(app: App, status: str) -> int:
    app.conn.execute(
        "INSERT INTO learned_profile (version, created_utc, theta, proposals, wall_decisions, evidence, status) "
        "VALUES (1, 'x', '{}', ?, ?, '{}', ?)",
        [
            '{"pending": "fri_sat:late:any", "accepted": [], "refused": []}',
            '{"pending": null, "decided": {}}',
            status,
        ],
    )
    return 1


def proposal_sample(app: App) -> dict[str, Any]:
    profile_row(app, "suggested")
    return {"kind": "rule", "name": "fri_sat:late:any", "yes": True}


def learn_module_sample(app: App) -> dict[str, Any]:
    app.conn.execute("INSERT INTO kv (key, value) VALUES ('learned_energy', '{\"prices\": [], \"observations\": 0}')")
    return {"module": "energy", "use": True}


def a_source(app: App) -> int:
    app.do("source_add", name="Canvas", url="https://example.edu/feed.ics")
    return app.table("sources")[0]["id"]


def a_suggestion(app: App, batch: str | None = None) -> int:
    source = a_source(app)
    app.conn.execute(
        "INSERT INTO raw_inputs (source_id, external_id, received_utc, content_hash, content) "
        "VALUES (?, 'e', '2026-10-19T13:00Z', 'h', 'x')",
        [source],
    )
    cursor = app.conn.execute(
        "INSERT INTO suggestions (raw_input_id, batch, command, input, created_utc) VALUES (1, ?, 'add', ?, ?)",
        [batch, '{"title": "PS1", "preset": "Assignment", "due": "2026-10-23T17:00"}', "2026-10-19T13:00Z"],
    )
    return int(cursor.lastrowid or 0)


def a_batch(app: App) -> str:
    a_suggestion(app, "syllabus 1")
    return "syllabus 1"


def a_skipped_mail(app: App) -> int:
    source = app.conn.execute("INSERT INTO sources (user_id, kind, name) VALUES (1, 'gmail', 'Gmail')").lastrowid
    return int(
        app.conn.execute(
            "INSERT INTO raw_inputs (user_id, source_id, external_id, received_utc, content_hash, content, status) "
            "VALUES (1, ?, 'm1', '2026-10-19T12:00Z', 'h', 'From: a@b.c', 'ignored')",
            [source],
        ).lastrowid
        or 0
    )


def a_waiting_repeat(app: App) -> str:
    source = app.conn.execute("INSERT INTO sources (user_id, kind, name) VALUES (1, 'gcal', 'School')").lastrowid
    raw = app.conn.execute(
        "INSERT INTO raw_inputs (user_id, source_id, external_id, received_utc, content_hash, content, status) "
        "VALUES (1, ?, 'chem_1', '2026-10-19T12:00Z', 'h', '{}', 'extracted')",
        [source],
    ).lastrowid
    lecture = '{"title": "CHEM", "preset": "Class", "start": "2026-10-20T12:20", "end": "2026-10-20T13:10"}'
    app.conn.execute(
        "INSERT INTO suggestions (user_id, raw_input_id, batch, command, input, quotes, created_utc) "
        "VALUES (1, ?, 'repeat:chem', 'add', ?, '{}', '2026-10-19T12:00Z')",
        [raw, lecture],
    )
    return "repeat:chem"


def a_calendar(app: App) -> str:
    app.conn.execute(
        "INSERT INTO kv (user_id, key, value) VALUES (1, 'google_calendars', ?)",
        ['[{"id": "school@group", "name": "School", "primary": false}]'],
    )
    return "school@group"


def template_project(app: App) -> int:
    return app.do("template_apply", template="Essay", title="essay", hours=6, due="2026-10-30T17:00")["item"]["id"]


ALL_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def import_sample(app: App) -> dict[str, Any]:
    folder = Path(tempfile.mkdtemp())
    (folder / "todos.json").write_text(json.dumps([{"id": "A", "title": "PS 3", "horizon": "shortTerm"}]))
    rules = {"categories": [{"name": "Classes", "color": "blue", "pattern": "lec"}]}
    (folder / "categories.json").write_text(json.dumps(rules))
    return {"todos_path": str(folder / "todos.json"), "categories_path": str(folder / "categories.json")}


def chroma_sample(app: App) -> dict[str, Any]:
    folder = Path(tempfile.mkdtemp())
    (folder / "colors.json").write_text(json.dumps({"CAL:EVENT": "blue"}))
    return {"colors_path": str(folder / "colors.json")}


SAMPLES: dict[str, Callable[[App], dict[str, Any]]] = {
    "import_personal": import_sample,
    "import_chroma_colors": chroma_sample,
    "duplicates_merge": lambda app: {
        "groups": [{"keep": essay(app), "drop": [app.do("add", title="Copy", duration_min=30)["item"]["id"]]}]
    },
    "not_duplicates": lambda app: {"ids": [essay(app), essay(app)]},
    "review_again": lambda app: {},
    "reviewed": lambda app: (app.do("review_again"), {"ids": [essay(app)], "keep": False})[1],
    "event_going": lambda app: {"title": "Poker night"},
    "sleep_mark": lambda app: (app.do("settings_set", key="sleep_tracking", value={"on": True}), {"kind": "up"})[1],
    "sleep_mark_edit": lambda app: {"id": slept(app), "at": "2026-10-19T07:30"},
    "sleep_mark_remove": lambda app: {"id": slept(app)},
    "sleep_skip": lambda app: {"date": "2026-10-18", "kind": "bed"},
    "meal_start": lambda app: (app.do("settings_set", key="meal_tracking", value={"on": True}), {})[1],
    "meal_end": lambda app: (
        app.do("settings_set", key="meal_tracking", value={"on": True}),
        app.do("meal_start", at="2026-10-19T08:30"),
        {},
    )[2],
    "meal_log": lambda app: (eating(app), {"kind": "lunch", "start": "2026-10-18T12:00", "end": "2026-10-18T12:30"})[1],
    "meal_skip": lambda app: (eating(app), {"kind": "lunch"})[1],
    "meal_edit": lambda app: {"id": eating(app), "start": "2026-10-19T07:30"},
    "meal_remove": lambda app: {"id": eating(app)},
    "meal_use_length": longer_lunches,
    "meal_use_time": late_lunches,
    "meal_plan": breakfasts,
    "other_way_pick": lambda app: {"weights": {"energy": 2.0}, "seed": 1, "rule_totals": {"energy": 100}},
    "add": add_sample,
    "edit": lambda app: {"id": essay(app), "title": "long essay", "duration_min": 180},
    "drop": lambda app: {"id": essay(app)},
    "reopen": reopen_sample,
    "done": lambda app: {"id": essay(app), "actual_min": 100},
    "stuck": lambda app: {"id": essay(app), "note": "can't find the reading"},
    "rule_win": lambda app: {"winner": "deep_run", "loser": "chunk_cost"},
    "depend": lambda app: {"item_id": essay(app), "depends_on_id": chore(app)},
    "undepend": undepend_sample,
    "area_add": lambda app: {"name": "Psych"},
    "area_edit": lambda app: {"id": app.do("area_add", name="Psych")["id"], "name": "Psychology"},
    "progress": lambda app: {"id": essay(app), "share": 0.5},
    "start": lambda app: {"id": chore(app)},
    "stop": stop_sample,
    "log": lambda app: {"id": essay(app), "start": "2026-10-19T07:45", "end": "2026-10-19T08:30"},
    "review_submit": review_sample,
    "pin": lambda app: {"id": chore(app), "start": "2026-10-19T15:00", "kind": "locked"},
    "unpin": lambda app: {"id": a_pin(app)},
    "shove": lambda app: {"range": "1h"},
    "unshove": a_shove,
    "series_add": lambda app: {"title": "gym", "every": "mon,wed", "duration_min": 60},
    "series_edit": lambda app: {"id": gym(app)["series_id"], "from_date": "2026-10-26", "duration_min": 90},
    "series_stop": lambda app: {"id": gym(app)["series_id"]},
    "series_delete": lambda app: {"id": gym(app)["series_id"]},
    "report": lambda app: {"where": "plan", "message": "the calendar went blank"},
    "series_resume": lambda app: {"id": app.do("series_stop", id=gym(app)["series_id"])["id"]},
    "skip": lambda app: {"id": occurrence(app)},
    "settings_set": lambda app: {"key": "daily_cap", "value": dict.fromkeys(ALL_DAYS, 8)},
    "setup_save": lambda app: app.do("setup")["answers"] | {"focus_hours": 2},
    "pace": lambda app: {"name": "easy", "for_days": 3},
    "pace_save": lambda app: {"name": "Gentle", "capacity": 0.8},
    "pace_delete": lambda app: {"name": "Push"},
    "day_override": lambda app: {"date": "2026-10-20", "bedtime": "01:00", "cap_hours": 6},
    "materialize": materialize_sample,
    "close_day": close_day_sample,
    "settle": settle_sample,
    "compare_answer": compare_sample,
    "proposal_answer": proposal_sample,
    "checkin": lambda app: {"state": "tired"},
    "learn_apply": lambda app: {"version": profile_row(app, "suggested")},
    "learn_reject": lambda app: {"version": profile_row(app, "suggested")},
    "learn_reset": lambda app: {"module": "all"},
    "learn_module": learn_module_sample,
    "source_add": lambda app: {"name": "Canvas", "url": "https://example.edu/feed.ics"},
    "source_edit": lambda app: {"id": a_source(app), "trusted": True},
    "source_remove": lambda app: {"id": a_source(app), "forget": True},
    "sync_now": lambda app: {},
    "week_note": lambda app: {"week": "2026-10-19", "feel": "Busy"},
    "reorder": lambda app: {"parent_id": essay(app), "ids": []},
    "rule_add": lambda app: {"text": "lunch before 1pm"},
    "rule_set": lambda app: {"name": "daily_load", "enabled": False},
    "rule_remove": lambda app: {"name": "cluster"},
    "mail_retry": lambda app: {"id": a_skipped_mail(app)},
    "repeats_import": lambda app: {"repeats": [{"batch": a_waiting_repeat(app)}]},
    "calendar_set": lambda app: {"id": a_calendar(app), "on": True, "kind": "Class"},
    "kind_add": lambda app: {"name": "Lab report", "like": "Assignment"},
    "kind_remove": lambda app: {"name": "Errand", "move_to": "Chore"},
    "token_remove": lambda app: {"name": app.do("token_add", name="claude")["name"]},
    "document_add": lambda app: {"name": "syllabus", "content": "PS1 due Friday"},
    "document_retry": lambda app: {"id": a_failed_document(app)},
    "suggestion_accept": lambda app: {"id": a_suggestion(app)},
    "suggestion_reject": lambda app: {"id": a_suggestion(app)},
    "batch_accept": lambda app: {"batch": a_batch(app)},
    "act": act_sample,
    "push_subscribe": lambda app: {"endpoint": "https://push.example/1", "keys": {"p256dh": "k", "auth": "a"}},
    "push_unsubscribe": lambda app: {"endpoint": subscribed(app)},
    "template_apply": lambda app: {"template": "Essay", "title": "essay", "hours": 6, "due": "2026-10-30T17:00"},
    "template_save": lambda app: {"name": "Mine", "project_id": template_project(app)},
    "undo": lambda app: {"command_id": app.full("add", payload={"text": "x ~30m"}).command_id},
}
NOT_UNDOABLE = {"resolve"}  # needs a waiting plan; tested with scenario 3
UNLOGGED = {name for name, spec in REGISTRY.items() if not spec.logged}


def a_failed_document(app: App) -> int:
    app.do("document_add", name="syllabus.pdf", media_type="application/pdf", content="JVBERi0=")
    raw = app.table("raw_inputs")[-1]["id"]
    app.conn.execute("UPDATE raw_inputs SET status = 'failed', error = 'no key' WHERE id = ?", [raw])
    return raw


def test_every_mutating_command_has_a_sample() -> None:
    mutating = {name for name, spec in REGISTRY.items() if spec.mutates and spec.logged}
    assert mutating - NOT_UNDOABLE == set(SAMPLES)


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_preview_leaves_no_trace(app: App, name: str) -> None:
    payload = SAMPLES[name](app)
    before, logged = state(app), len(app.table("command_log"))
    result = app.full(name, payload=payload, preview=True, provisional=False)
    assert result.preview and result.command_id is None
    assert state(app) == before and len(app.table("command_log")) == logged


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_undo_restores_every_row(app: App, name: str) -> None:
    payload = SAMPLES[name](app)
    kv = lambda: [r for r in app.table("kv") if r["key"] != "generation"]  # noqa: E731  (undo bumps the counter)
    seen = (lambda: state(app) | {"kv": kv()}) if name in KV_STATE else (lambda: state(app))
    before = seen()
    applied = app.full(name, payload=payload, provisional=False)
    assert seen() != before
    app.do("undo", command_id=applied.command_id)
    assert seen() == before


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_a_repeated_idempotency_key_returns_the_stored_result(app: App, name: str) -> None:
    payload = SAMPLES[name](app)
    first = app.full(name, payload=payload, idempotency_key="k1", provisional=False)
    after_first = state(app)
    again = app.full(name, payload=payload, idempotency_key="k1", provisional=False)
    assert again.repeated and again.command_id == first.command_id and again.result == first.result
    assert state(app) == after_first


def test_undo_is_refused_when_a_later_command_changed_the_rows(app: App) -> None:
    item_id = essay(app)
    first = app.full("edit", payload={"id": item_id, "title": "draft"}, provisional=False)
    later = app.full("edit", payload={"id": item_id, "title": "final"}, provisional=False)
    with pytest.raises(FieldError, match=f"undo C{later.command_id} \\(edit\\) first"):
        app.do("undo", command_id=first.command_id)
    app.do("undo", command_id=later.command_id)
    app.do("undo", command_id=first.command_id)
    assert app.do("item", id=item_id)["item"]["title"] == "essay"


def test_an_undo_can_be_undone_and_a_command_is_undone_only_once(app: App) -> None:
    added = app.full("add", payload={"text": "x ~30m"}, provisional=False)
    undone = app.full("undo", payload={"command_id": added.command_id}, provisional=False)
    with pytest.raises(FieldError, match="already undone"):
        app.do("undo", command_id=added.command_id)
    app.do("undo", command_id=undone.command_id)
    assert [i["title"] for i in app.do("items")] == ["x"]
    app.do("undo", command_id=added.command_id)
    assert app.do("items") == []


def test_unlogged_commands_are_only_those_with_no_undo_or_a_secret_result() -> None:
    assert {
        "replan",
        "notify_test",
        "ask_ai",
        "ask_claude",
        "mac_sync",
        "mac_written",
        "token_add",
        "google_connect",
        "google_client_save",
        "google_remove",
    } == UNLOGGED
