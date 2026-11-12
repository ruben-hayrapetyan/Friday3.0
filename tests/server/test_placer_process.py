"""The quick placement's process and its failures (server/placer.py), in this process: the child's loop fed by hand,
a placement that failed in its process or before Friday is set up placing nothing, and a placement that can't be
kept rolled back."""

from pathlib import Path
from typing import Any

import pytest

from friday.commands.registry import run
from friday.core.db import connect
from friday.server import placer as placing
from friday.server.placer import Placer, child
from tests.commands.helpers import App, new_app


class Pipe:
    def __init__(self, *coming: Any) -> None:
        self.coming, self.said = list(coming), []

    def recv(self) -> Any:
        return self.coming.pop(0)

    def send(self, message: Any) -> None:
        self.said.append(message)


class Heard:
    def __init__(self) -> None:
        self.events: list[tuple[str, Any]] = []

    def publish(self, event: str, data: Any = None) -> None:
        self.events.append((event, data))


def changed(app: App) -> Any:
    """A change as the server makes it, answered before its placement."""
    return run(app.conn, "add", {"text": "essay due wed ~2h"}, now_utc=app.now_utc, provisional=False)._placing


def test_the_child_places_what_its_sent_says_what_failed_and_stops_when_told(tmp_path: Path) -> None:
    app = new_app(tmp_path, horizon_days=3)
    generation, items, left = changed(app)
    pipe = Pipe((app.now_utc, 1, items, left), ("not", "a", "job"), None)
    child(pipe, tmp_path / "friday.db", tmp_path / "rules")  # type: ignore[arg-type]
    (kind, placed), (failed, trace) = pipe.said
    assert kind == "placed" and placed[0] == generation and [b.title for b in placed[2]] == ["essay"]
    assert failed == "error" and "Traceback" in trace


def test_a_placement_that_failed_in_its_process_places_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    app = new_app(tmp_path, horizon_days=3)
    heard = Heard()
    quick = Placer(tmp_path / "friday.db", heard, lambda: app.now_utc)  # type: ignore[arg-type]
    quick.pipe = Pipe(("error", "Traceback: boom"))  # type: ignore[assignment]
    quick.request(1, changed(app))
    assert quick.place(app.conn, 1) is None
    assert heard.events == [] and not app.do("plan")["provisional"]
    assert "quick placement failed in its process" in caplog.text and "boom" in caplog.text


def test_nothing_is_placed_before_friday_is_set_up(tmp_path: Path) -> None:
    conn = connect(tmp_path / "friday.db")
    quick = Placer(tmp_path / "friday.db", Heard(), lambda: 0)  # type: ignore[arg-type]
    assert quick.place(conn, 1) is None


def test_a_placement_that_cant_be_kept_is_rolled_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = new_app(tmp_path, horizon_days=3)
    heard = Heard()
    quick = Placer(tmp_path / "friday.db", heard, lambda: app.now_utc)  # type: ignore[arg-type]
    quick.request(1, changed(app))

    def keep_provisional(*args: Any) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(placing, "keep_provisional", keep_provisional)
    with pytest.raises(RuntimeError, match="disk full"):
        quick.place(app.conn, 1)
    assert not app.conn.in_transaction and heard.events == []
