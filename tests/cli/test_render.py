"""Terminal output for answers a short scenario rarely gives (cli/render.py): a free gap and what fits it, a block
that can't move, moved and removed blocks, a repeated command, a server not set up, and an answer with no renderer
of its own."""

from friday.cli import render


def test_a_free_gap_says_how_long_what_fits_and_what_must_start_soon() -> None:
    answer = {
        "current": None,
        "gap_minutes": 45,
        "next": None,
        "swaps": [],
        "alerts": [{"latest_start": "2026-10-19T15:30", "title": "essay", "kind": "deadline"}],
        "fits": [{"title": "reading", "minutes": 30}, {"title": "email", "minutes": 15}],
    }
    assert render.now(answer) == [
        "Now  free  45 min",
        "! Start by Mon 15:30:  essay (deadline)",
        "Fits this gap:  reading (30 min) · email (15 min)",
    ]
    nothing = {"current": None, "gap_minutes": 0, "next": None, "swaps": [], "alerts": [], "fits": []}
    assert render.now(nothing) == ["Nothing planned."]


def test_a_block_that_cant_move_says_why() -> None:
    answer = {"key": "T4@2026-10-20T14:00", "to_start": "2026-10-21T09:00", "wall": "it's locked there"}
    assert render.why_not(answer) == ["Can't move T4@Tue14:00 to Wed Oct 21 09:00: it's locked there"]


def test_moved_and_removed_blocks_and_the_plans_notices() -> None:
    answer = {
        "added": [],
        "moved": [{"title": "essay", "before": [["2026-10-19T09:00", "2026-10-19T11:00"]],
                   "after": [["2026-10-20T14:00", "2026-10-20T16:00"]]}],
        "removed": [{"title": "laundry", "start": "2026-10-19T20:00", "end": "2026-10-19T21:00"}],
        "inputs": [{"command_id": 9, "actor": "you", "command": "pin"}, {"kind": "clock"}],
        "notices": ["Rule mine is off"],
    }  # fmt: skip
    assert render.changes(answer) == [
        "Moved    essay  Mon 09:00-11:00 -> Tue 14:00-16:00",
        "Removed  laundry  Mon 20:00-21:00",
        "  because C9 you pin",
        "! Rule mine is off",
    ]
    assert render.changes({"added": [], "moved": [], "removed": [], "inputs": [], "notices": []}) == ["No changes."]


def test_a_repeated_command_and_a_preview_say_so() -> None:
    repeated = {"command_id": 7, "result": {"message": "Saved"}, "repeated": True}
    assert render.command_lines("settings_set", repeated) == [
        "Saved   (C7, undo: friday undo C7)",
        "(already done earlier with this idempotency key)",
    ]
    preview = {"command_id": None, "preview": True, "result": {"message": "Would save"}}
    assert render.command_lines("settings_set", preview) == ["Preview; nothing changed.", "Would save"]


def test_a_server_not_set_up_and_its_problems_are_warnings() -> None:
    answer = {"plan_id": None, "plan_generation": None, "generation": 1, "timer": None, "ready": False,
              "problems": ["Google isn't connected"], "notices": ["Rule mine is off"]}  # fmt: skip
    assert render.status(answer) == [
        "No plan yet",
        "! Not set up yet: run `fridayd init`",
        "! Google isn't connected",
        "! Rule mine is off",
    ]


def test_an_answer_without_a_renderer_prints_its_message_or_its_json() -> None:
    assert render.fallback({}) == ["Done"]
    assert render.fallback({"message": "Saved", "id": 3}) == ["Saved"]
    assert render.fallback({"id": 3}) == ["{", '  "id": 3', "}"]
    assert render.fallback([1]) == ["[", "  1", "]"]


def test_pinned_and_tentative_blocks_are_marked_and_finished_looking_work_asked_about() -> None:
    assert render.block_title({"title": "essay", "pinned": "locked", "tentative": True}) == "essay  [locked, tentative]"
    item = {
        "id": 3,
        "title": "essay",
        "area": "CS",
        "when": "window",
        "remaining_min": 0,
        "status": "todo",
        "due": None,
    }
    assert render.item_row(item) == ["T3", "essay · CS", "0 min", "", "finished?"]


def test_a_paces_period_end_and_a_load_week_that_is_planned() -> None:
    answer = {"default": "Normal", "now_label": "Push", "period_end": "2026-10-23",
              "paces": {"Normal": {"capacity": 1}, "Push": {"capacity": 1.2, "rest": 0.5}}}  # fmt: skip
    assert render.paces(answer)[-1] == "Now: Push through 2026-10-23"
    week = {"start": "2026-10-19", "hours": 12.5, "capacity": 40, "forecast": False, "due": [{"title": "essay"}]}
    assert render.load([week]) == ["2026-10-19  12.5 / 40 h  planned  essay"]
