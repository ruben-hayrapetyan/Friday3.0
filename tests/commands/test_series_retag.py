"""A repeat's tag changed from its row in Settings → Repeating (3 Nov): it stays one repeat, retagged with its open
times, rather than splitting into an ended one and a new one from today. A time change, or a tag change from a date
you give, still splits it, so the past keeps what it was."""

from pathlib import Path

import pytest

from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    app = new_app(tmp_path)
    app.do("area_add", name="Fitness")
    app.do("area_add", name="Health")
    return app


def runs(app: App, status: str = "todo") -> list[dict]:
    return [i for i in app.do("items", status=status) if i["title"] == "Run"]


class TestGlassBox:
    def test_only_a_tag_retags_in_place(self, app: App) -> None:
        sid = app.do("series_add", title="Run", every="mon,wed", duration_min=30)["id"]
        assert app.do("series_edit", id=sid, area="Fitness")["id"] == sid
        assert [r["id"] for r in app.do("series_list") if r["title"] == "Run"] == [sid]

    def test_a_kind_or_notes_too(self, app: App) -> None:
        sid = app.do("series_add", title="Run", every="mon", duration_min=30)["id"]
        app.do("series_edit", id=sid, notes="easy pace")
        assert len([r for r in app.do("series_list") if r["title"] == "Run"]) == 1

    def test_with_a_date_it_changes_from_then_as_before(self, app: App) -> None:
        sid = app.do("series_add", title="Run", every="mon,wed", duration_min=30)["id"]
        new = app.do("series_edit", id=sid, area="Fitness", from_date="2026-11-01")["id"]
        assert new != sid

    def test_a_new_time_still_splits(self, app: App) -> None:
        sid = app.do("series_add", title="Run", every="mon,wed", duration_min=30)["id"]
        assert app.do("series_edit", id=sid, every="tue")["id"] != sid


class TestBlackBox:
    def test_every_open_run_wears_the_new_tag_and_a_finished_one_keeps_its_own(self, app: App) -> None:
        sid = app.do("series_add", title="Run", every="mon,wed,fri", duration_min=30, area="Health")["id"]
        first = runs(app)[0]
        app.do("done", id=first["id"])
        app.do("series_edit", id=sid, area="Fitness")
        assert runs(app) and all(r["area"] == "Fitness" for r in runs(app))
        assert [r["area"] for r in runs(app, "done")] == ["Health"]

    def test_tag_changes_back_and_forth_leave_one_row(self, app: App) -> None:
        sid = app.do("series_add", title="Run", every="mon,wed", duration_min=30)["id"]
        for tag in ["Fitness", "Health", None, "Fitness"]:
            app.do("series_edit", id=sid, area=tag)
        rows = [r for r in app.do("series_list") if r["title"] == "Run"]
        assert [(r["id"], r["area"]) for r in rows] == [(sid, "Fitness")]

    def test_undo_gives_the_old_tag_back(self, app: App) -> None:
        sid = app.do("series_add", title="Run", every="mon", duration_min=30, area="Health")["id"]
        changed = app.full("series_edit", payload={"id": sid, "area": "Fitness"})
        app.do("undo", command_id=changed.command_id)
        assert all(r["area"] == "Health" for r in runs(app))
