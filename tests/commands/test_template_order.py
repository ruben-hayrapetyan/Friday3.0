"""A project saved as a template keeps the steps in the order you put them (3 Nov: "Save as template" got a button on
a project's page, and `template_save` read the steps in the order they were made, not the order shown)."""

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def essay(app: App) -> tuple[int, list[int]]:
    project = app.do("template_apply", template="Essay", title="Essay", hours=4, due="2026-11-02T17:00")["item"]
    kids = [i["id"] for i in app.do("items") if i["parent_id"] == project["id"]]
    return project["id"], kids


def saved(app: App, name: str = "Mine") -> list[str]:
    return [s["title"] for s in app.do("settings")["templates"][name]]


class TestGlassBox:
    def test_without_a_reorder_it_is_the_order_made(self, app: App) -> None:
        project, _ = essay(app)
        app.do("template_save", name="Mine", project_id=project)
        assert saved(app) == ["Outline", "Draft", "Revise"]

    def test_a_reorder_is_kept(self, app: App) -> None:
        project, (outline, draft, revise) = essay(app)
        app.do("reorder", parent_id=project, ids=[revise, outline, draft])
        app.do("template_save", name="Mine", project_id=project)
        assert saved(app) == ["Revise", "Outline", "Draft"]

    def test_a_step_added_after_the_reorder_goes_last(self, app: App) -> None:
        project, (outline, draft, revise) = essay(app)
        app.do("reorder", parent_id=project, ids=[draft, outline, revise])
        app.do("add", title="Print it", parent_id=project, duration_min=15)
        app.do("template_save", name="Mine", project_id=project)
        assert saved(app) == ["Draft", "Outline", "Revise", "Print it"]

    def test_another_project_s_order_doesn_t_leak_in(self, app: App) -> None:
        first, (a, b, c) = essay(app)
        second, _ = essay(app)
        app.do("reorder", parent_id=first, ids=[c, b, a])
        app.do("template_save", name="Second", project_id=second)
        assert saved(app, "Second") == ["Outline", "Draft", "Revise"]


class TestBlackBox:
    @settings(max_examples=12, deadline=None)
    @given(order=st.permutations([0, 1, 2]))
    def test_whatever_the_order_the_template_is_what_the_project_shows(self, tmp_path_factory, order) -> None:  # type: ignore[no-untyped-def]
        app = new_app(tmp_path_factory.mktemp("t"))
        project, kids = essay(app)
        titles = ["Outline", "Draft", "Revise"]
        app.do("reorder", parent_id=project, ids=[kids[i] for i in order])
        app.do("template_save", name="Mine", project_id=project)
        assert saved(app) == [titles[i] for i in order]
        shares = [s["share"] for s in app.do("settings")["templates"]["Mine"]]
        assert sum(shares) == pytest.approx(1, abs=0.01)

    def test_a_template_saved_in_your_order_makes_projects_in_that_order(self, app: App) -> None:
        project, (outline, draft, revise) = essay(app)
        app.do("reorder", parent_id=project, ids=[outline, revise, draft])
        app.do("template_save", name="Mine", project_id=project)
        made = app.do("template_apply", template="Mine", title="Next essay", hours=4, due="2026-11-10T17:00")["item"]
        assert [i["title"] for i in app.do("items") if i["parent_id"] == made["id"]] == ["Outline", "Revise", "Draft"]
