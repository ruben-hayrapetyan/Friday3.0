"""The simulator's command-line tools: `python -m friday.sim` (a simulated term, its metrics printed),
`python -m friday.sim.agenda NAME` (a Cornell student's plan as they would read it) and `python -m friday.sim.profiles`
(the hosted test profiles' list, and a build that names what it couldn't make). Each works in a scratch folder."""

import json
import runpy
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from friday.planner import service
from friday.sim import agenda, profiles, world
from friday.sim.generate import TermConfig
from friday.sim.history import HISTORY_ENGINE
from friday.sim.profiles import LIVED, PROFILES, build, build_one
from friday.sim.world import Metrics

# python -m friday.sim


def test_a_simulated_term_prints_its_metrics_and_first_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    told: dict[str, Any] = {}

    def lived(folder: Path, config: TermConfig, seed: int, days: int, on_day: Any, family: str) -> Metrics:
        told.update(folder=folder, config=config, seed=seed, days=days, family=family, there=folder.is_dir())
        for day in (6, 7, 8):
            on_day(day, Metrics(plan_seconds=[1.0, 2.0]))
        return Metrics(days=8, errors=["mon add: refused"])

    monkeypatch.setattr(world, "run_term", lived)
    folder = tmp_path / "kept"
    argv = ["friday.sim", "--weeks", "2", "--seed", "3", "--days", "8", "--family", "noisy", "--folder", str(folder)]
    monkeypatch.setattr(sys, "argv", argv)
    runpy.run_module("friday.sim", run_name="__main__")
    out, err = capsys.readouterr()
    assert told == {"folder": folder, "config": TermConfig(weeks=2), "seed": 3, "days": 8, "family": "noisy",
                    "there": True}  # fmt: skip
    assert err == "week 1 lived, 2 replans\n"  # once a week
    summary, errors = out.split("}\n")
    assert json.loads(summary + "}")["days"] == 8 and errors == "mon add: refused\n"


def test_without_a_folder_the_term_is_lived_in_a_scratch_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folders: list[Path] = []
    monkeypatch.setattr(world, "run_term", lambda folder, *rest: folders.append(folder) or Metrics())
    monkeypatch.setattr(sys, "argv", ["friday.sim", "--days", "1"])
    runpy.run_module("friday.sim", run_name="__main__")
    assert len(folders) == 1 and not folders[0].exists()  # gone afterwards
    assert json.loads(capsys.readouterr().out)["days"] == 0


# python -m friday.sim.agenda


def test_a_sitting_is_back_to_back_blocks_of_one_item_and_hours_read_as_hours() -> None:
    blocks = [
        {"item_id": 1, "title": "PS", "start": "2026-10-19T10:00", "end": "2026-10-19T11:00"},
        {"item_id": 1, "title": "PS", "start": "2026-10-19T09:00", "end": "2026-10-19T10:00"},
        {"item_id": 2, "title": "Read", "start": "2026-10-19T11:00", "end": "2026-10-19T11:30"},
        {"item_id": 1, "title": "PS", "start": "2026-10-19T11:30", "end": "2026-10-19T12:00"},
    ]
    assert [(a.hour, b.hour, n) for a, b, _, n in agenda.joined(blocks)] == [(9, 11, 1), (11, 11, 2), (11, 12, 1)]
    assert [agenda.hm(m) for m in (0, 45, 60, 135)] == ["0h", "0h45", "1h", "2h15"]


def test_each_day_lists_its_events_all_day_ones_first_and_its_work_with_the_hours() -> None:
    plan = {
        "fixed": [
            {"title": "Lecture", "start": "2026-10-19T10:10", "end": "2026-10-19T11:25"},
            {"title": "Birthday", "start": "2026-10-19T00:00", "end": "2026-10-20T00:00"},
            {"title": "No time yet", "start": None, "end": None},
        ],
        "blocks": [{"item_id": 1, "title": "PS 3", "start": "2026-10-19T13:00", "end": "2026-10-19T14:30"}],
    }
    lines = agenda.days(plan, datetime(2026, 10, 19), 2)
    assert lines == [
        "\nMon Oct 19   work 1h30",
        "  all day     ☐ Birthday",
        "  10:10–11:25  · Lecture",
        "  13:00–14:30  ▶ PS 3 (1h30)",
        "\nTue Oct 20   work 0h",
    ]


def test_the_work_table_shows_each_pieces_length_cut_and_margin_late_or_open() -> None:
    plan = {
        "blocks": [
            {"item_id": 1, "title": "Essay", "start": "2026-10-20T09:00", "end": "2026-10-20T11:00"},
            {"item_id": 2, "title": "Late PS", "start": "2026-10-21T22:00", "end": "2026-10-22T01:00"},
        ]
    }
    base = {"when": "window", "status": "todo"}
    items = [
        base | {"id": 1, "title": "Essay", "due": "2026-10-22T12:00", "remaining_min": 120},
        base | {"id": 2, "title": "Late PS", "due": "2026-10-21T23:59", "remaining_min": 180},
        base | {"id": 3, "title": "Someday reading", "due": None, "remaining_min": None},
        base | {"id": 4, "title": "Done already", "due": None, "remaining_min": 60, "status": "done"},
        {"id": 5, "title": "Class", "due": None, "remaining_min": 60, "when": "fixed", "status": "todo"},
    ]
    header, late, essay, reading = agenda.work_table(plan, items)
    assert header.startswith("\nwork") and "ends before due" in header
    assert late.startswith("Late PS") and "Wed 21 23:59" in late and late.endswith("LATE")
    assert essay.split()[-2:] == ["2d", "1h"] and " 2h " in essay
    assert reading.split()[2:4] == ["-", "open"]


def test_meals_are_listed_by_day_with_none_planned_and_outside_their_window_said() -> None:
    meal = {"amount": "elastic", "status": "todo", "when": "window", "remaining_min": 45, "firmness": "soft"}
    items = [
        meal | {"id": 1, "title": "Lunch", "release": "2026-10-19T11:00", "due": "2026-10-19T14:00"},
        meal | {"id": 2, "title": "Dinner", "release": "2026-10-19T17:00", "due": "2026-10-19T20:00"},
        meal | {"id": 3, "title": "Lunch", "release": "2026-10-20T11:00", "due": "2026-10-20T14:00"},
    ]
    plan = {
        "blocks": [
            {"item_id": 1, "title": "Lunch", "start": "2026-10-19T12:00", "end": "2026-10-19T12:45"},
            {"item_id": 2, "title": "Dinner", "start": "2026-10-19T20:00", "end": "2026-10-19T20:30"},
        ]
    }
    assert agenda.meal_lines(plan, items, datetime(2026, 10, 21)) == [
        "\nMeals (— is none planned)",
        "  2026-10-19  Lunch 12:00 45m · Dinner 20:00 30m OUTSIDE",
        "  2026-10-20  Lunch —",
    ]


@pytest.mark.filterwarnings("ignore:'friday.sim.agenda' found in sys.modules:RuntimeWarning")  # run as -m
def test_a_students_agenda_prints_their_week_work_meals_and_costs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    planned = service.replan

    def quick(conn: Any, now_utc: int) -> Any:  # the history's small budget: the same plan's shape, sooner
        agenda.ask(conn, now_utc, "settings_set", key="engine", value=HISTORY_ENGINE)
        return planned(conn, now_utc)

    monkeypatch.setattr(service, "replan", quick)
    argv = ["agenda", "maya", "--at", "2026-10-19T09:00", "--days", "2", "--folder", str(tmp_path)]
    monkeypatch.setattr(sys, "argv", argv)
    runpy.run_module("friday.sim.agenda", run_name="__main__")
    out = capsys.readouterr().out
    assert out.startswith("===== Maya (very light): ") and "\nExpect: " in out and "Inbox left: " in out
    assert "\nMon Oct 19   work " in out and "\nTue Oct 20   work " in out and "\nWed Oct 21" not in out
    assert "INFO 4390 Lecture" in out and "\nMeals (— is none planned)" in out
    assert "\nNotices: " in out and "\nRule costs: " in out
    assert (tmp_path / "maya" / "friday.db").exists()  # kept to open with fridayd


# python -m friday.sim.profiles


def test_the_list_names_every_profile_with_its_kind_and_whether_it_is_lived_in(
    capsys: pytest.CaptureFixture[str],
) -> None:
    profiles.main(["list"])
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == len(PROFILES)
    maya = next(line for line in lines if line.startswith("maya "))
    assert maya.split()[1:3] == ["student", "lived" if "maya" in LIVED else "fresh"] and "Maya: " in maya


def test_a_profile_is_never_built_over_an_existing_one_and_the_failure_is_named(tmp_path: Path) -> None:
    (tmp_path / "maya").mkdir()
    (tmp_path / "maya" / "friday.db").write_text("someone's")
    with pytest.raises(FileExistsError, match="already there"):
        build(tmp_path / "maya", "maya", 0)
    key, error = build_one((tmp_path, "maya", 0))
    assert key == "maya" and error.startswith("FileExistsError: ") and "already there" in error
    assert (tmp_path / "maya" / "friday.db").read_text() == "someone's"


def test_a_build_skips_profiles_already_there_and_fails_when_one_cant_be_made(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "maya").mkdir()
    (tmp_path / "maya" / "friday.db").write_text("")
    profiles.main(["build", str(tmp_path), "--only", "maya", "--jobs", "1"])
    assert capsys.readouterr().err == f"0 built in {tmp_path}; 0 failed\n"
    (tmp_path / "jordan").write_text("a file where its folder would go")
    with pytest.raises(SystemExit) as stopped:
        profiles.main(["build", str(tmp_path), "--only", "jordan", "--jobs", "1"])
    out, err = capsys.readouterr()
    assert stopped.value.code == 1 and out.startswith("FAILED jordan: FileExistsError")
    assert err == f"0 built in {tmp_path}; 1 failed\n"
