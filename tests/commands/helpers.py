"""A fresh database with a timezone, sleep times and daily caps set, and a clock the tests move by hand."""

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from friday.api.types import CommandResult
from friday.commands.all import REGISTRY
from friday.commands.registry import run
from friday.core.db import connect
from friday.core.time import format_local, parse_local, to_local, to_utc

TZ = "America/New_York"
WEEKDAY_SLEEP = {"bedtime": "23:30", "wake": "07:30", "margin_min": 60}
WEEKEND_SLEEP = {"bedtime": "00:30", "wake": "09:00", "margin_min": 60}
SLEEP = {d: WEEKDAY_SLEEP for d in ("mon", "tue", "wed", "thu", "fri")} | {"sat": WEEKEND_SLEEP, "sun": WEEKEND_SLEEP}
MONDAY_9 = "2026-10-19T09:00"


@dataclass
class App:
    conn: sqlite3.Connection
    now_utc: int
    actor: str = "you"
    results: list[CommandResult] = field(default_factory=list)

    def do(self, command: str, /, **payload: Any) -> Any:
        """Run a command or query and return its result; raise on errors."""
        out = run(self.conn, command, payload, now_utc=self.now_utc, actor=self.actor, provisional=False)
        self.results.append(out)
        return out.result

    def full(self, command: str, /, **options: Any) -> CommandResult:
        payload = options.pop("payload", {})
        return run(self.conn, command, payload, now_utc=self.now_utc, actor=self.actor, **options)

    def at(self, local: str) -> "App":
        self.now_utc = to_utc(parse_local(local), TZ)
        return self

    def local_now(self) -> str:
        return format_local(to_local(self.now_utc, TZ))

    def table(self, name: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn.execute(f"SELECT * FROM {name} ORDER BY rowid")]


def new_app(tmp_path: Path, now: str = MONDAY_9, horizon_days: int = 7) -> App:
    conn = connect(tmp_path / "friday.db")
    app = App(conn, to_utc(parse_local(now), TZ))
    app.do("settings_set", key="time", value={"timezone": TZ, "horizon_days": horizon_days})
    app.do("settings_set", key="sleep", value=SLEEP)
    app.do(
        "settings_set",
        key="engine",
        value={
            "chains": 2,
            "step_budgets": [{"max_items": 1000, "cold": 40_000, "warm": 20_000}],
            "repair_steps": 50_000,
            "fallback_s": 2,
        },
    )
    return app


__all__ = ["REGISTRY", "App", "new_app"]
