"""The generated CLI: arguments and options from each input model, ids with their letter, JSON for mappings, and
plain rendering."""

from typing import Any

import pytest
from typer.testing import CliRunner

from friday.api.commands import AddInput, SettingsSetInput, UndoInput
from friday.cli import main, render
from friday.cli.main import app, takes_json, value_of


def test_every_verb_is_a_command_with_hyphens() -> None:
    names = {c.name for c in app.registered_commands}
    assert {"add", "why-not", "review-submit", "pace-save", "undo"} <= names


def test_required_fields_are_arguments_and_add_takes_its_line() -> None:
    runner = CliRunner()
    assert "COMMAND_ID" in runner.invoke(app, ["undo", "--help"]).output.upper()
    assert "[TEXT]" in runner.invoke(app, ["add", "--help"]).output.upper()


def test_a_required_list_takes_each_value_as_its_own_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    # `friday late-accept T3 T4` was "unexpected extra argument", and one id went as "3", not a list (audit, 12 Nov)
    sent: list[dict[str, Any]] = []
    monkeypatch.setattr(main, "call", lambda verb, payload, preview=False: sent.append(payload) or {"message": "ok"})
    ran = CliRunner().invoke(app, ["late-accept", "T3", "T4"])
    assert ran.exit_code == 0, ran.output
    ran = CliRunner().invoke(app, ["reorder", "T1", "T5"])
    assert ran.exit_code == 0, ran.output
    assert sent == [{"item_ids": ["3", "4"]}, {"parent_id": "1", "ids": ["5"]}]


def test_ids_lose_their_letter_and_mappings_are_json() -> None:
    assert value_of("command_id", UndoInput.model_fields["command_id"], "C881") == "881"
    assert value_of("after", AddInput.model_fields["after"], ["T4", "5"]) == ["4", "5"]
    assert value_of("value", SettingsSetInput.model_fields["value"], '{"debounce_s": 1}') == {"debounce_s": 1}
    assert value_of("title", AddInput.model_fields["title"], "T42") == "T42"  # only id fields
    assert not takes_json(AddInput.model_fields["tags"].annotation)


def test_blocks_print_with_short_keys_and_lengths_read_naturally() -> None:
    assert render.short_key("T42@2026-10-20T14:00") == "T42@Tue14:00"
    assert render.short_key("T42@Tue14:00") == "T42@Tue14:00"
    assert [render.length(m) for m in (45, 60, 90, 100, None)] == ["45 min", "1 h", "1.5 h", "1:40 h", "open"]
    assert render.span("2026-10-19T19:00", "2026-10-19T22:00") == "Mon 7pm-10pm"


def test_a_command_prints_its_undo_hint() -> None:
    response = {"command_id": 7, "result": {"message": "Saved planner"}, "provisional": None}
    assert render.command_lines("settings_set", response) == ["Saved planner   (C7, undo: friday undo C7)"]


def test_why_not_prints_the_total_and_each_rules_change() -> None:
    answer = {"key": "T4@2026-10-20T14:00", "to_start": "2026-10-21T09:00", "wall": None,
              "difference": {"late_night": 0, "minimize_changes": 400, "spread": -150}, "total": 250}  # fmt: skip
    lines = render.why_not(answer)
    assert lines[0] == "Moving T4@Tue14:00 to Wed Oct 21 9am costs +2.5"
    assert [line.split() for line in lines[1:]] == [["minimize_changes", "+4.0"], ["spread", "-1.5"]]
