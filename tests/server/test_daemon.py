"""`fridayd` itself (server/main.py, server/demo.py): `init` without a timezone it can find says how to give one, the
timezone comes from TZ when set, and a lived-in demo is made once in its own folder and served from then on."""

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from friday.core.db import connect
from friday.ingest import llm
from friday.planner.store import kv_get, load_settings
from friday.server import demo, jobs
from friday.server import main as fridayd
from friday.server.app import wall_clock


def test_init_without_a_timezone_says_how_to_give_one(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="pass --timezone, e.g. America/New_York"):
        fridayd.initialize(tmp_path / "friday.db", None, "23:30", "07:30", 60)
    assert not (tmp_path / "friday.db").exists()


def test_the_timezone_is_taken_from_tz_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TZ", "Europe/Paris")
    assert fridayd.local_timezone() == "Europe/Paris"
    monkeypatch.delenv("TZ")
    found = fridayd.local_timezone()
    assert found is None or "/" in found or found == "UTC"


def test_a_lived_in_demo_is_made_once_then_served(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    monkeypatch.setenv("FRIDAY_CONFIG", str(tmp_path / "unused.toml"))  # the demo points it at its own folder
    monkeypatch.setattr(jobs, "SAMPLE_APIS", {})
    monkeypatch.setattr(llm, "client", llm.client)
    lived: list[str] = []

    def open_lived_in(db_path: Path, student: Any, now_utc: int) -> Any:  # three weeks lived, in a moment
        lived.append(student.name)
        fridayd.initialize(db_path, "America/New_York", "23:30", "07:30", 60)
        return connect(db_path)

    monkeypatch.setattr(demo, "open_lived_in", open_lived_in)
    served: list[tuple[Path, str, int]] = []
    folder = tmp_path / "friday-demo-maya-lived"
    for _ in range(2):
        demo.run_demo(folder, 8799, lambda *where: served.append(where), fridayd.initialize, "maya", True)
    assert len(lived) == 1 and "last three weeks (about a minute)" in capsys.readouterr().out
    assert served == [(folder / "friday.db", "127.0.0.1", 8799, wall_clock)] * 2  # the real clock, not shifted
    conn = connect(folder / "friday.db")
    assert kv_get(conn, "demo", False) is True and load_settings(conn)["time"].timezone == "America/New_York"
    assert set(jobs.SAMPLE_APIS) == {"google", "mail", "client"}


def test_a_shifted_demo_is_lived_and_served_days_from_now(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`fridayd demo --shift-days 3` (the screen tests pin their weekday with it): the three weeks are lived up to three
    days from now, the server's clock runs three days ahead, and the stand-in Google and mail are dated from that
    day's Monday."""
    monkeypatch.setenv("FRIDAY_CONFIG", str(tmp_path / "unused.toml"))
    monkeypatch.setattr(jobs, "SAMPLE_APIS", {})
    monkeypatch.setattr(llm, "client", llm.client)
    lived_at: list[int] = []

    def open_lived_in(db_path: Path, student: Any, now_utc: int) -> Any:
        lived_at.append(now_utc)
        fridayd.initialize(db_path, "America/New_York", "23:30", "07:30", 60)
        return connect(db_path)

    monkeypatch.setattr(demo, "open_lived_in", open_lived_in)
    term_days: list[date] = []
    real_term = demo.cornell.term
    monkeypatch.setattr(
        demo.cornell, "term", lambda student, today: (term_days.append(today), real_term(student, today))[1]
    )
    served: list[tuple[Any, ...]] = []
    demo.run_demo(tmp_path / "d", 8799, lambda *where: served.append(where), fridayd.initialize, "maya", True, 3)
    clock = served[0][3]
    assert abs(lived_at[0] - (wall_clock() + 3 * 1440)) <= 1 and abs(clock() - (wall_clock() + 3 * 1440)) <= 1
    assert term_days == [date.today() + timedelta(days=3)]


def test_the_shift_reaches_the_demo_from_the_command_line(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    called: list[tuple[Any, ...]] = []
    monkeypatch.setattr(fridayd, "run_demo", lambda *args: called.append(args))
    fridayd.main(["--data-dir", str(tmp_path / "x"), "demo", "--case", "maya", "--ready", "--shift-days", "-2"])
    assert called[0][-1] == -2
    fridayd.main(["--data-dir", str(tmp_path / "x"), "demo"])
    assert called[1][-1] == 0
