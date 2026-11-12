"""The CLI end to end against the HTTP API (a TestClient stands in for the network): each verb's arguments sent as
the server takes them, its answer printed by its renderer, and the server's refusals said with their exit codes."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from friday.cli import main
from friday.server.app import create_app
from tests.commands.helpers import App, new_app

HERE = "http://127.0.0.1:9"  # a closed port: nothing is reached if a call slipped past the stand-in


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=3)


@pytest.fixture
def friday(app: App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """`friday` talks to this server: its httpx calls are answered by the app in-process."""
    served = create_app(tmp_path / "friday.db", clock=lambda: app.now_utc, background=False, plugin_dir=tmp_path)
    monkeypatch.setenv("FRIDAY_SERVER", HERE + "/")
    with TestClient(served, base_url=HERE) as client:

        def get(url: str, params: Any, headers: dict[str, str], timeout: Any) -> httpx.Response:
            return client.get(url, params=params, headers=headers)

        def post(url: str, json: Any, params: Any, headers: dict[str, str], timeout: Any) -> httpx.Response:
            return client.post(url, json=json, params=params, headers=headers)

        monkeypatch.setattr(httpx, "get", get)
        monkeypatch.setattr(httpx, "post", post)
        yield client


def says(*args: str, code: int = 0) -> list[str]:
    ran = CliRunner().invoke(main.app, list(args))
    assert ran.exit_code == code, ran.output
    return ran.output.splitlines()


def test_a_new_task_says_its_id_how_to_undo_it_and_where_it_probably_goes(friday: TestClient) -> None:
    assert says("add", "essay due tue 17:00 ~2h") == [
        "Added T1  essay   2 h   due Tue Oct 20 17:00   (C4, undo: friday undo C4)",
        "Probably Mon 09:00-11:00 (planning…)",
    ]
    assert says("add", "talk mon 13:00-14:00") == ["Added T2  talk   Mon 13:00-14:00   (C5, undo: friday undo C5)"]


def test_a_repeating_task_says_its_series_and_a_preview_changes_nothing(friday: TestClient) -> None:
    assert says("add", "reading ~1h every mon")[0].startswith("Repeats as S1: ")
    before = says("items")
    preview, added = says("add", "laundry ~1h", "--preview")[:2]
    assert preview == "Preview; nothing changed." and added.startswith("Added T") and added.endswith("  laundry   1 h")
    assert says("items") == before


def test_before_the_first_plan_it_says_so_then_the_plan_reads_by_day(friday: TestClient) -> None:
    assert says("plan") == ["No plan yet."]
    assert says("status") == ["No plan yet"]
    says("add", "essay due mon 11:00 ~5h")
    says("add", "talk mon 13:00-14:00")
    assert says("replan") == ["Plan P1"]
    plan = says("plan")
    assert plan[:2] == ["Plan P1", "Mon Oct 19   5 h"]
    assert "  13:00-14:00  talk  (fixed)" in plan
    assert "  09:00-13:00  essay   T1@Mon09:00" in plan


def test_an_item_lists_its_blocks_the_work_done_and_what_it_waits_for(friday: TestClient) -> None:
    says("add", "essay due tue 17:00 ~3h")
    says("add", "lab report due wed 12:00 ~2h", "--after", "T1")
    says("replan")
    says("log", "2026-10-19T07:00", "2026-10-19T08:00", "--id", "T1")
    essay = says("item", "T1")
    assert essay[0].split()[:4] == ["T1", "essay", "2", "h"]
    assert any(line.startswith("  planned  Mon ") for line in essay)
    assert "  done     1 h (retro)" in essay
    assert "  after    T1" in says("item", "T2")


def test_items_lists_each_with_its_length_and_due_and_an_empty_list_says_so(friday: TestClient) -> None:
    assert says("items") == ["Nothing here."]
    says("add", "essay due tue 17:00 ~2h")
    says("add", "laundry ~90m")
    assert says("items") == ["T1  essay    2 h    due Tue Oct 20 17:00", "T2  laundry  1.5 h"]
    assert says("done", "T2")[0] == "T2  laundry  1.5 h    done   (C6, undo: friday undo C6)"


def test_now_says_the_block_on_whats_next_and_what_is_safe_to_switch_to(friday: TestClient) -> None:
    says("add", "reading due tue 17:00 ~1h")
    says("add", "essay due tue 17:00 ~2h")
    says("replan")
    now, upcoming, switch = says("now")
    assert now.startswith("Now ") and now.endswith(" left") and upcoming.startswith("Next ")
    assert switch.startswith("Safe to switch to:  ")


def test_late_work_is_triaged_and_a_shove_that_makes_it_later_asks_first(friday: TestClient) -> None:
    assert says("triage") == ["Nothing is late."]
    says("add", "essay due mon 11:00 ~5h")
    says("replan")
    late, *options = says("triage")
    hours = late.removeprefix("! essay: ").removesuffix(" h late")
    assert float(hours) > 0 and options and all(f"saves {hours} h" in o for o in options)
    asked = says("shove", "rest")
    assert asked[1].startswith("! essay: ") and asked[1].endswith("h later (5 h planned)")
    assert asked[2] == "Send it again with --decision shove_anyway, keep_must_dos or cancel."


def test_a_shove_with_nothing_in_the_way_says_what_it_cleared(friday: TestClient) -> None:
    says("add", "essay due fri 17:00 ~2h")
    says("replan")
    assert says("shove", "day tue")[0].startswith("Cleared all of Tue Oct 20")


def test_why_gives_the_reason_and_costs_and_why_not_the_cost_of_moving(friday: TestClient) -> None:
    says("add", "essay due tue 17:00 ~2h")
    says("replan")
    key = next(line.split()[-1] for line in says("plan") if "essay" in line)
    why = says("why", key)
    assert why[0] == key and why[-1].split() == ["total", "0.0"]
    moved = says("why-not", key, "--start", "2026-10-20T14:00")
    assert moved[0].startswith(f"Moving {key} to Tue Oct 20 14:00 costs ")


def test_changes_lists_what_the_plan_added_and_the_commands_behind_it(friday: TestClient) -> None:
    says("add", "essay due tue 17:00 ~2h")
    says("replan")
    changed = says("changes")
    assert changed[0].startswith("Added    essay  Mon ")
    assert "  because C4 cli add" in changed


def test_the_log_says_what_undid_what_and_diagnose_lists_commands_and_plans(friday: TestClient) -> None:
    says("add", "essay ~2h")
    says("undo", "C4")
    log = says("log-list")
    assert log[0].split()[:6] == ["C5", "Mon", "Oct", "19", "09:00", "cli"] and log[0].endswith("command_id=4")
    assert log[1].startswith("C4 ") and log[1].endswith("undone by C5") and 'text="essay ~2h"' in log[1]
    says("replan")
    assert any(" plan " in line and "P1 replan by cli" in line for line in says("diagnose"))


def test_paces_fits_rule_totals_load_and_projects(friday: TestClient) -> None:
    paces = says("paces")
    assert paces[0].split() == ["capacity", "rest", "spread", "growth"]
    assert paces[1].split()[:2] == ["Default", "Normal"] and paces[-1] == "Now: Normal"
    assert says("fits", "--minutes", "5") == ["Nothing fits."]
    assert says("projects") == ["No projects."]
    says("add", "thesis due fri 17:00 ~4h")
    says("add", "outline ~1h", "--parent-id", "T1")
    says("replan")
    assert ["T2", "outline", "1", "h"] in [line.split() for line in says("fits", "--minutes", "60")]
    assert all(len(line.split()) == 2 for line in says("rule-totals"))
    assert says("load")[0].startswith("2026-10-19  ")
    project, child = says("projects")
    assert project.startswith("T1  thesis  due Fri Oct 23 17:00  ")
    assert child == "  T2  outline  1 h left"


def test_a_timer_shows_in_the_status(friday: TestClient) -> None:
    says("add", "essay ~2h")
    says("add", "reading ~1h")
    says("start", "T1")
    says("start", "T2", "--alongside")
    _, timer, also = says("status")
    assert {timer, also} == {"Timer on T2 for 0 min", "Also timing T1 for 0 min"}


def test_json_prints_the_answer_as_the_server_sent_it(friday: TestClient) -> None:
    says("add", "essay ~2h")
    assert [i["title"] for i in json.loads("\n".join(says("items", "--json")))] == ["essay"]


def test_what_the_server_refuses_is_said_with_exit_code_1(friday: TestClient) -> None:
    assert says("edit", "T99", "--title", "x", code=1)[0].startswith("friday: ")
    bad_choice = says("items", "--status", "bogus", code=1)
    assert bad_choice[0].startswith("friday: status: Input should be 'todo'")
    not_json = says("settings-set", "sleep", "not json", code=1)  # sent as typed: the server names what's wrong
    assert not_json[0].startswith("friday: ")


def test_the_server_comes_from_the_cli_config_when_friday_server_isnt_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("FRIDAY_SERVER", raising=False)
    monkeypatch.setattr(main, "CONFIG", tmp_path / "cli.toml")
    assert main.server() == main.DEFAULT_SERVER
    (tmp_path / "cli.toml").write_text('server = "http://mac.tailnet:8765/"\n')
    assert main.server() == "http://mac.tailnet:8765"


def test_an_error_page_is_said_in_its_own_words() -> None:
    request = httpx.Request("GET", HERE)
    assert main.error_message(httpx.Response(404, text="Not Found", request=request)) == "Not Found"
    assert main.error_message(httpx.Response(400, json={"message": "no"}, request=request)) == "no"
    assert main.error_message(httpx.Response(400, json={"detail": "Bad"}, request=request)) == "Bad"
    listed = {"detail": [{"loc": ["body"], "msg": "Field required"}, {"loc": ["query", "id"], "msg": "not a number"}]}
    assert main.error_message(httpx.Response(422, json=listed, request=request)) == (
        "input: Field required; id: not a number"
    )


def test_a_failing_server_exits_3_and_a_missing_one_2(friday: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(url: str, params: Any, headers: dict[str, str], timeout: Any) -> httpx.Response:
        return httpx.Response(500, text="boom", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", broken)
    assert says("items", code=3) == ["friday: Friday failed (500): boom"]

    def gone(url: str, params: Any, headers: dict[str, str], timeout: Any) -> httpx.Response:
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", gone)
    assert says("items", code=2)[0] == f"friday: can't reach Friday at {HERE} (ConnectError); is fridayd running?"


def test_the_days_review_lists_its_blocks_and_asks_about_work_that_looks_finished(friday: TestClient, app: App) -> None:
    says("add", "essay due tue 17:00 ~2h")
    says("add", "reading ~1h")
    says("replan")
    app.at("2026-10-19T21:00")
    says("log", "2026-10-19T07:00", "2026-10-19T08:00", "--id", "T2")
    assert says("items")[1].split()[-1] == "finished?"
    review = says("review")
    assert review[0] == "Review of 2026-10-19"
    assert any(line.startswith("  ") and "essay   T1@Mon" in line for line in review)
    assert "  finished?  T2 reading  (friday done T2)" in review, review
