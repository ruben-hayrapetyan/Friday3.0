"""The quick placement after the answer (server/placer.py): a change answers once saved; the placer then places every
change since the saved plan together, keeps it for the plan view, and tells the app which generation it has seen."""

from pathlib import Path
from typing import Any

from friday.commands.registry import run
from friday.planner.service import replan
from friday.server.placer import Placer
from tests.commands.helpers import App, new_app


class Heard:
    def __init__(self) -> None:
        self.events: list[tuple[str, Any]] = []

    def publish(self, event: str, data: Any = None) -> None:
        self.events.append((event, data))


def change(app: App, name: str, **payload: Any) -> Any:
    """A change as the server makes it: answered without its placement."""
    return run(app.conn, name, payload, now_utc=app.now_utc, provisional=False)


def blocks_of(app: App, item_id: int) -> list[tuple[str, str]]:
    return [(b["start"], b["end"]) for b in app.do("plan")["blocks"] if b["item_id"] == item_id]


def test_changes_since_the_saved_plan_are_placed_together(tmp_path: Path) -> None:
    app = new_app(tmp_path, horizon_days=3)
    essay = app.do("add", text="essay due wed ~2h")["item"]["id"]
    replan(app.conn, app.now_utc)
    (start, end), *_ = blocks_of(app, essay)
    heard = Heard()
    placer = Placer(tmp_path / "friday.db", heard, lambda: app.now_utc)  # type: ignore[arg-type]
    added = change(app, "add", text="laundry due tue ~1h")
    pinned = change(app, "pin", id=essay, start="2026-10-20T15:00", end="2026-10-20T17:00", kind="preferred",
                    from_start=start, from_end=end)  # fmt: skip
    assert added.generation is not None and pinned.generation == added.generation + 1
    assert not app.do("plan")["provisional"]  # answered before any placement: the saved plan shows
    placer.request(1, added._placing)  # type: ignore[arg-type]
    placer.request(1, pinned._placing)  # type: ignore[arg-type]
    assert placer.place(app.conn, 1) is not None
    view = app.do("plan")
    assert view["provisional"] and view["generation"] == pinned.generation
    assert blocks_of(app, essay) == [("2026-10-20T15:00", "2026-10-20T17:00")]
    assert blocks_of(app, added.result["item"]["id"]), "the laundry placed with the pin, not lost to it"
    assert heard.events == [("plan.provisional", {"generation": pinned.generation})]


def test_changes_a_saved_plan_has_seen_are_let_go(tmp_path: Path) -> None:
    app = new_app(tmp_path, horizon_days=3)
    placer = Placer(tmp_path / "friday.db", Heard(), lambda: app.now_utc)  # type: ignore[arg-type]
    first = change(app, "add", text="essay due wed ~2h")
    placer.request(1, first._placing)  # type: ignore[arg-type]
    replan(app.conn, app.now_utc)
    later = change(app, "add", text="laundry ~1h")
    placer.request(1, later._placing)  # type: ignore[arg-type]
    placer.place(app.conn, 1)
    assert [p[0] for p in placer.due[1]] == [later.generation]
    assert app.do("plan")["generation"] == later.generation


def test_the_plan_says_which_changes_it_has_seen(tmp_path: Path) -> None:
    app = new_app(tmp_path, horizon_days=3)
    made = change(app, "add", text="essay due wed ~2h")
    assert app.do("plan")["generation"] < made.generation
    replan(app.conn, app.now_utc)
    assert app.do("plan")["generation"] >= made.generation
