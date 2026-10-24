"""Items, areas, dependencies and series through the commands."""

from pathlib import Path

import pytest

from friday.core.items import FieldError
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def test_quick_add_creates_an_item_in_local_time_with_a_new_area(app: App) -> None:
    out = app.do("add", text="PS5 #cs1110 due tue 5pm ~3h !4")
    item = out["item"]
    assert (item["title"], item["area"], item["due"], item["duration_min"], item["importance"]) == (
        "PS5", "cs1110", "2026-10-20T17:00", 180, 4)  # fmt: skip
    assert item["preset"] == "Assignment" and "new area cs1110" in out["warnings"]
    assert app.table("items")[0]["due_utc"] == "2026-10-20T21:00Z"


def test_fields_given_alongside_a_line_win(app: App) -> None:
    item = app.do("add", text="essay due tue ~2h", duration_min=90, importance=5)["item"]
    assert (item["duration_min"], item["importance"]) == (90, 5)


def test_an_area_is_found_by_its_plain_words(app: App) -> None:
    app.do("area_add", name="CS 1110")
    assert app.do("add", text="PS6 #cs1110 ~1h")["item"]["area"] == "CS 1110"
    with pytest.raises(FieldError, match="exists"):
        app.do("area_add", name="cs 1110")


def test_validation_names_the_field(app: App) -> None:
    with pytest.raises(FieldError) as error:
        app.do("add", title="essay", firmness="hard")
    assert error.value.field == "due_utc"
    with pytest.raises(FieldError) as error:
        app.do("add", title="lunch", amount="elastic", min_min=45, ideal_min=30, max_min=60)
    assert error.value.field == "ideal_units"


def test_edit_changes_only_what_is_given_and_can_clear_a_due(app: App) -> None:
    item_id = app.do("add", text="reading /reading due fri ~1h")["item"]["id"]
    edited = app.do("edit", id=item_id, title="reading ch 4", due=None)["item"]
    assert (edited["title"], edited["due"], edited["duration_min"]) == ("reading ch 4", None, 60)


def test_an_assignment_can_be_shortened_below_its_smallest_piece_and_lengthened_again(app: App) -> None:
    item_id = app.do("add", text="PS5 due tue 5pm ~3h")["item"]["id"]
    assert app.do("edit", id=item_id, duration_min=15)["item"]["duration_min"] == 15
    assert app.table("items")[0]["min_chunk_units"] == 1  # done in one go
    assert app.do("edit", id=item_id, duration_min=120)["item"]["duration_min"] == 120
    assert app.table("items")[0]["min_chunk_units"] == 2  # not split into 15-minute bits
    with pytest.raises(FieldError, match="amount"):
        app.do("edit", id=item_id, duration_min=15, min_chunk_min=60)


def test_done_records_a_completion_with_the_actual_time_and_reopen_removes_it(app: App) -> None:
    item_id = app.do("add", text="essay due wed ~2h")["item"]["id"]
    app.do("done", id=item_id, actual_min=150)
    (completion,) = app.table("completions")
    assert (completion["actual_minutes"], completion["actual_source"]) == (150, "retro")
    assert app.do("reopen", id=item_id)["item"]["status"] == "todo" and app.table("completions") == []


def test_done_without_an_actual_uses_the_timer_else_the_plan_as_assumed(app: App) -> None:
    timed = app.do("add", text="tidy ~1h")["item"]["id"]
    app.do("start", id=timed)
    app.at("2026-10-19T09:40")
    app.do("done", id=timed)
    planned = app.do("add", text="email ~30m")["item"]["id"]
    app.do("done", id=planned)
    sources = [(c["actual_minutes"], c["actual_source"]) for c in app.table("completions")]
    assert sources == [(40, "timer"), (30, "assumed")]


def test_a_dependency_that_closes_a_loop_is_refused(app: App) -> None:
    a = app.do("add", text="draft ~1h")["item"]["id"]
    b = app.do("add", text=f"edit ~1h after:T{a}")["item"]["id"]
    with pytest.raises(FieldError, match="loop"):
        app.do("depend", item_id=a, depends_on_id=b)
    app.do("undepend", item_id=b, depends_on_id=a)
    app.do("depend", item_id=a, depends_on_id=b)


def test_nothing_can_wait_for_an_open_item(app: App) -> None:
    book = app.do("add", title="book", preset="side project")["item"]["id"]
    later = app.do("add", text="blog ~1h")["item"]["id"]
    with pytest.raises(FieldError, match="never finishes"):
        app.do("depend", item_id=later, depends_on_id=book)


def test_a_repeat_makes_occurrences_and_editing_one_detaches_it(app: App) -> None:
    out = app.do("add", text="gym every mon,wed ~1h")
    assert out["occurrences"] > 30
    first = app.conn.execute("SELECT id FROM items WHERE series_id = ? ORDER BY id", [out["series_id"]]).fetchone()[0]
    app.do("edit", id=first, title="gym (short)", duration_min=30)
    assert app.table("items")[0]["detached"] == 1


def test_editing_a_series_from_a_date_keeps_earlier_and_detached_occurrences(app: App) -> None:
    series_id = app.do("add", text="gym every mon,wed ~1h")["series_id"]
    rows = app.conn.execute("SELECT id, occurrence_date FROM items WHERE series_id = ? ORDER BY occurrence_date",
                            [series_id]).fetchall()  # fmt: skip
    detached = rows[3]["id"]
    app.do("edit", id=detached, title="gym with Sam")
    app.do("series_edit", id=series_id, from_date="2026-10-26", duration_min=90)
    lengths = {r["occurrence_date"]: r["duration_units"] for r in app.table("items") if r["status"] == "todo"}
    assert lengths["2026-10-21"] == 4 and lengths["2026-10-28"] == 6
    assert any(r["id"] == detached for r in app.table("items"))


def test_stopping_a_series_removes_its_future_occurrences(app: App) -> None:
    series_id = app.do("add", text="gym every mon,wed ~1h")["series_id"]
    assert app.do("series_stop", id=series_id)["occurrences"] == 0


def test_a_fixed_repeat_keeps_its_local_time_across_daylight_saving(app: App) -> None:
    app.do("add", text="lecture at mon 2pm for 75m every mon")
    starts = [r["start_utc"] for r in app.table("items")]
    assert starts[0] == "2026-10-19T18:00Z" and "2026-11-02T19:00Z" in starts  # EDT, then EST from Nov 1


def test_friday_estimates_a_length_from_similar_finished_items(app: App) -> None:
    for minutes in (200, 210, 190):
        item_id = app.do("add", text=f"PS{minutes} #cs ~3h")["item"]["id"]
        app.do(
            "log", id=item_id, start="2026-10-19T07:00", end=f"2026-10-19T{7 + minutes // 60:02d}:{minutes % 60:02d}"
        )
        app.do("done", id=item_id)
    estimated = app.do("add", text="PS9 #cs")["item"]
    assert estimated["duration_min"] == 210 and estimated["estimate"]["method"] == "similar"
    stored = app.table("items")[-1]
    assert (stored["duration_source"], stored["friday_estimate_units"]) == ("estimate", 14)


def test_a_weekly_goal_repeats_with_a_target_in_each_weeks_window(app: App) -> None:
    app.do("series_add", title="guitar", preset="Goal", every="week", target_min=180)
    first = next(i for i in app.do("items") if i["title"] == "guitar")
    assert (first["amount"], first["release"], first["due"]) == ("target", "2026-10-19T04:00", "2026-10-26T04:00")


def test_quick_add_reads_a_bare_time_and_length_and_a_trailing_open(app: App) -> None:
    call = app.do("add", text="call mom sat 3pm 30m")["item"]
    assert (call["when"], call["start"], call["end"]) == ("fixed", "2026-10-24T15:00", "2026-10-24T15:30")
    book = app.do("add", text="read dune open")["item"]
    assert (book["title"], book["amount"], book["preset"]) == ("read dune", "open", "Side project")


def test_a_repeating_chore_is_soft_so_it_stays_in_its_week(app: App) -> None:
    app.do("series_add", title="laundry", preset="Chore", every="week", duration_min=60)
    first = next(i for i in app.do("items") if i["title"] == "laundry")
    assert first["firmness"] == "soft"
