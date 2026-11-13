"""`fridayd demo`: the sample student's term (sim/sample.py) in a folder of its own, served like the real thing, with
its Google, Gmail and AI standing in for yours. It never reads your friday.toml, secrets or data."""

import os
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

from friday.commands.registry import run
from friday.core.db import connect
from friday.ingest import llm
from friday.planner.store import kv_set
from friday.server import jobs
from friday.server.app import wall_clock
from friday.sim import cornell
from friday.sim.history import open_lived_in
from friday.sim.profiles import PROFILES
from friday.sim.sample import ZONE, term


def run_demo(
    folder: Path,
    port: int,
    serve: Callable[..., None],
    initialize: Callable[..., None],
    case: str | None = None,
    ready: bool = False,
    shift_days: int = 0,
) -> None:
    """`serve` and `initialize` are main's, passed in so this module needn't import it. `case` is one of the
    test profiles (sim/profiles.py) instead of the sample term; `ready` has them three weeks into using
    Friday (sim/history.py): set up as they would themselves, with work done, reviews, a project, rules and
    yesterday's review and some of the inbox still to answer. `shift_days`: lived and served as if it were that many
    days from now, at the same time of day (the screen tests run as a Thursday, so a sample planned from its Monday
    reads the same whatever day they run)."""
    clock = wall_clock if not shift_days else (lambda: wall_clock() + shift_days * 1440)
    folder.mkdir(parents=True, exist_ok=True)
    os.environ["FRIDAY_CONFIG"] = str(folder / "friday.toml")  # none there: no config, no secrets
    db_path = folder / "friday.db"
    student = PROFILES[case] if case else None
    if student and ready and not db_path.exists():
        print(f"Living {student.name}'s last three weeks (about a minute)…", flush=True)
        open_lived_in(db_path, student, clock()).close()
    if not db_path.exists():
        initialize(db_path, ZONE.key, "23:30", "07:30", 60)
        conn = connect(db_path)
        for key, value in (("gcal", {"read": ["primary"]}), ("gmail", {"enabled": True})):
            run(conn, "settings_set", {"key": key, "value": value}, now_utc=clock(), actor="cli", provisional=False)
        conn.close()
    conn = connect(db_path)
    kv_set(conn, "demo", True)  # said on every page, so the sample isn't taken for your own data
    conn.close()
    today = date.today() + timedelta(days=shift_days)
    sample = cornell.term(student, today) if student else term(today)
    address = cornell.address(student) if student else "student@cornell.edu"  # the stand-in account
    jobs.SAMPLE_APIS.update(google={address: sample.google}, mail={address: sample.gmail}, client=sample.ai)
    llm.client = lambda *_: sample.ai  # "Ask AI" too, whichever AI is chosen
    who = f"{student.name}: {student.about}" if student else "a sample term"
    print(f"Made-up sample data ({who}; not your calendars or mail) in {folder}, at http://localhost:{port}.")
    serve(db_path, "127.0.0.1", port, clock)
