"""The command registry (DESIGN §9.1–9.2): every action and query is registered once; interfaces are generated.

A mutating command runs in one transaction and appends a `command_log` row with its actor, input, result and undo
data. `preview` runs it and rolls back; `preview="full"` also solves the changed state warm and returns the change
list. An idempotency key returns the stored result of an earlier run.
"""

import json
import logging
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Literal, get_type_hints

from pydantic import BaseModel, ValidationError

from friday.api.types import ChangeOut, CommandResult
from friday.commands.writer import Writer
from friday.core.dates import read_moment
from friday.core.db import SLOW_MS, begin_write, waited
from friday.core.items import FieldError
from friday.core.settings import minutes_of
from friday.core.time import (
    format_local,
    format_utc,
    local_midnight,
    parse_local,
    parse_utc,
    planning_date,
    span_to_utc,
    to_local,
    to_utc,
)
from friday.planner.service import plan_snapshot
from friday.planner.service import provisional as placement
from friday.planner.snapshot import Snapshot, read_snapshot
from friday.planner.store import current_plan, generation, load_item, load_settings
from friday.planner.views import change_list


@dataclass
class Ctx:
    conn: sqlite3.Connection
    db: Writer
    now_utc: int
    actor: str
    user_id: int
    settings: dict[str, Any]
    command_id: int | None = None
    notices: list[str] = field(default_factory=list)
    memo: dict[str, Any] = field(default_factory=dict)  # what one request reads once and many item views share
    # The server solves in its worker process: replan(reason) -> plan id. Without one, replan solves in-process.
    solver: Callable[[str], int | None] | None = None

    @property
    def tz(self) -> str:
        tz = self.settings["time"].timezone
        if tz is None:
            raise FieldError("timezone", "not set yet; run `fridayd init`")
        return tz

    @property
    def day_start(self) -> int:
        return minutes_of(self.settings["time"].day_start)

    @property
    def today(self) -> date:
        return planning_date(self.now_utc, self.tz, self.day_start)

    @property
    def now_text(self) -> str:
        return format_utc(self.now_utc)

    def utc(self, local: str, field_name: str = "time") -> str:
        """A local `2026-10-20T14:00`, or a spoken `tue 14:00` or `3pm`, as a stored UTC string."""
        return format_utc(to_utc(self.moment(local, field_name), self.tz))

    def moment(self, local: str, field_name: str = "time") -> datetime:
        """A local `2026-10-20T14:00`, or a spoken `tue 14:00` or `3pm`, as a clock time."""
        try:
            return parse_local(local)
        except ValueError:
            return self.spoken(local, field_name)

    def span(self, start: str, end: str, start_name: str = "start", end_name: str = "end") -> tuple[int, int]:
        """A start and end as UTC minutes; a pair beginning in the hour the clocks skip moves past it whole."""
        return span_to_utc(self.moment(start, start_name), self.moment(end, end_name), self.tz)

    def spoken(self, text: str, field_name: str) -> datetime:
        words = text.lower().split()
        found = read_moment(words, 0, to_local(self.now_utc, self.tz).date()) if words else None
        if found is None or found[1] is None or found[2] != len(words):
            raise FieldError(field_name, f"{text!r} is not a time like 2026-10-20T14:00 or tue 14:00")
        return local_midnight(found[0]) + timedelta(minutes=found[1])

    def local(self, stored: str | None) -> str | None:
        return format_local(to_local(parse_utc(stored), self.tz)) if stored else None


@dataclass(frozen=True)
class Spec:
    name: str
    fn: Callable[[Ctx, Any], Any]
    input_type: type[BaseModel]
    output_type: Any
    mutates: bool
    affects_plan: bool
    summary: str
    logged: bool = True  # False: runs outside the registry's transaction and log (replan writes plans itself)


log = logging.getLogger("friday.commands")
REGISTRY: dict[str, Spec] = {}


def command(name: str, *, mutates: bool = True, affects_plan: bool = False, logged: bool = True) -> Callable:
    def register(fn: Callable) -> Callable:
        hints = get_type_hints(fn)
        summary = (fn.__doc__ or name).strip().splitlines()[0]
        REGISTRY[name] = Spec(name, fn, hints["inp"], hints["return"], mutates, affects_plan, summary, logged)
        return fn

    return register


def query(name: str) -> Callable:
    return command(name, mutates=False)


def run(
    conn: sqlite3.Connection,
    name: str,
    payload: dict[str, Any] | BaseModel | None = None,
    *,
    now_utc: int,
    actor: str = "you",
    user_id: int = 1,
    preview: bool | Literal["full"] = False,
    idempotency_key: str | None = None,
    provisional: bool = True,
    solver: Callable[[str], int | None] | None = None,
) -> CommandResult:
    """Run one command or query, and log it: commands at info with their input, time and outcome, queries at debug.
    `provisional` adds the executor's quick placement to plan-changing commands."""
    started = time.perf_counter()
    try:
        out = dispatch(conn, name, payload, now_utc, actor, user_id, preview, idempotency_key, provisional, solver)
    except FieldError as error:
        log.warning("%s by %s refused: %s", name, actor, error)
        raise
    except Exception:
        log.exception("%s by %s failed", name, actor)
        raise
    spec = REGISTRY.get(name)
    ms = (time.perf_counter() - started) * 1000
    wait = waited(conn)  # of that time, how long it stood behind another write
    if spec is not None and spec.mutates and ms - wait > SLOW_MS:
        log.warning("%s by %s held the database for %.0f ms (other writes waited)", name, actor, ms - wait)
    if spec is not None and spec.mutates and spec.logged:
        given = payload.model_dump(exclude_none=True) if isinstance(payload, BaseModel) else payload or {}
        said = f"C{out.command_id}" if out.command_id is not None else "preview" if preview else "repeat"
        behind = f" (waited {wait:.0f} ms)" if wait >= 50 else ""
        log.info("%s by %s: %s, %.0f ms%s, %s", name, actor, said, ms, behind, json.dumps(given)[:120])
    else:
        log.debug("%s by %s: %.0f ms", name, actor, ms)
    return out


# Yours alone (the audit, 8 Nov): who may open Friday, its keys and mailboxes, where the AI and webhooks send what
# they send, and what's installed. An assistant's token (actor "mcp:…") never runs these, over MCP or the HTTP API
# (`fridayd mcp` uses the latter), nor undoes them; MCP also leaves them out of its tools (server/mcp.py HIDDEN).
YOURS_ONLY = frozenset({
    "token_add", "token_remove", "phone_set", "phone_pair", "phone_forget", "ai_key_set", "ai_check", "ai_models",
    "gmail_app_set", "google_connect", "google_connect_cancel", "google_remove", "google_client_save",
    "local_model_use", "local_model_cancel", "update_start", "update_stop", "import_personal", "terms_accept",
    "integration_connect", "integration_disconnect", "mail_app_set", "mail_app_forget",
})  # fmt: skip
YOURS_ONLY_SETTINGS = frozenset({"phone", "llm", "webhooks", "google", "gcal", "gmail", "server", "updates", "notify"})


def assistant_may(conn: sqlite3.Connection, name: str, payload: Any, actor: str, user_id: int) -> None:
    """Refuse an assistant what's yours alone, in words that say where you do it."""
    if not actor.startswith("mcp:"):
        return
    given = payload.model_dump() if isinstance(payload, BaseModel) else dict(payload or {})
    why = ""
    if name in YOURS_ONLY:
        why = name
    elif name == "settings_set" and given.get("key") in YOURS_ONLY_SETTINGS:
        why = f"the {given.get('key')} setting"
    elif name == "undo" and given.get("command_id") is not None:
        undone = conn.execute(
            "SELECT command, input FROM command_log WHERE user_id = ? AND id = ?", [user_id, given["command_id"]]
        ).fetchone()
        key = json.loads(undone["input"]).get("key") if undone and undone["command"] == "settings_set" else None
        if undone and (undone["command"] in YOURS_ONLY or key in YOURS_ONLY_SETTINGS):
            why = f"undoing {undone['command']}"
    if why:
        raise FieldError(
            "command", f"Only you can do that ({why}), not an assistant: do it in Friday's Settings on your Mac"
        )


def dispatch(
    conn: sqlite3.Connection,
    name: str,
    payload: dict[str, Any] | BaseModel | None,
    now_utc: int,
    actor: str,
    user_id: int,
    preview: bool | Literal["full"],
    idempotency_key: str | None,
    provisional: bool,
    solver: Callable[[str], int | None] | None,
) -> CommandResult:
    spec = REGISTRY.get(name)
    if spec is None:
        raise FieldError("command", f"no command named {name!r}")
    inp = payload if isinstance(payload, BaseModel) else spec.input_type.model_validate(payload or {})
    assistant_may(conn, name, inp, actor, user_id)
    if preview and spec.mutates and not spec.logged:  # it can't be rolled back, so a preview would do it (audit)
        raise FieldError("preview", f"{name} can't be previewed: it isn't a change to your plan, so it can't be undone")
    settings = load_settings(conn, user_id)
    if not spec.mutates or not spec.logged:
        ctx = Ctx(conn, Writer(conn, user_id), now_utc, actor, user_id, settings, solver=solver)
        return CommandResult(command_id=None, result=dump(spec.fn(ctx, inp)))
    if idempotency_key is not None:
        earlier = conn.execute(
            "SELECT id, result FROM command_log WHERE user_id = ? AND idempotency_key = ?", [user_id, idempotency_key]
        ).fetchone()
        if earlier:
            return CommandResult(command_id=earlier["id"], result=json.loads(earlier["result"]), repeated=True)
    return run_in_transaction(conn, spec, inp, settings, now_utc, actor, user_id, preview, idempotency_key, provisional)


def run_in_transaction(
    conn: sqlite3.Connection,
    spec: Spec,
    inp: BaseModel,
    settings: dict[str, Any],
    now_utc: int,
    actor: str,
    user_id: int,
    preview: bool | Literal["full"],
    idempotency_key: str | None,
    provisional: bool,
) -> CommandResult:
    begin_write(conn, spec.name)
    try:
        # Looked for again under the lock: a retry sent while the first was still running found nothing before, and
        # the key's second row was a database error (audit, 12 Nov).
        earlier = None if preview or idempotency_key is None else conn.execute(
            "SELECT id, result FROM command_log WHERE user_id = ? AND idempotency_key = ?", [user_id, idempotency_key]
        ).fetchone()  # fmt: skip
        if earlier:
            conn.execute("ROLLBACK")
            return CommandResult(command_id=earlier["id"], result=json.loads(earlier["result"]), repeated=True)
        command_id = log_start(conn, spec, inp, now_utc, actor, user_id, None if preview else idempotency_key)
        ctx = Ctx(conn, Writer(conn, user_id), now_utc, actor, user_id, settings, command_id)
        result = dump(spec.fn(ctx, inp))
        made = None
        placing = None
        if spec.affects_plan:
            bump_generation(conn, user_id)
            made = generation(conn, user_id)
            placing = (made, changed_items(ctx.db.changes), moved_from(ctx, inp))
        ghosts = None
        if placing is not None and provisional:
            ghosts = placement(conn, now_utc, user_id, placing[1], placing[2])
        if preview:
            snapshot = read_snapshot(conn, now_utc, user_id) if preview == "full" else None
            conn.execute("ROLLBACK")
            changes = full_preview(conn, snapshot, ctx.tz) if snapshot else None
            return CommandResult(command_id=None, result=result, provisional=ghosts, preview=True, changes=changes)
        conn.execute(
            "UPDATE command_log SET result = ?, undo = ? WHERE id = ?",
            [json.dumps(result), ctx.db.undo_data(), command_id],
        )
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:  # a full preview's solve fails after its rollback: its own error, not "no transaction"
            conn.execute("ROLLBACK")
        raise
    out = CommandResult(command_id=command_id, result=result, provisional=ghosts, generation=made)
    out._placing = placing
    return out


def tried[T](
    conn: sqlite3.Connection,
    name: str,
    payload: dict[str, Any],
    look: Callable[[sqlite3.Connection], T],
    *,
    now_utc: int,
    user_id: int = 1,
) -> T:
    """What `look` finds with a command applied that is then undone: the command and the look share one transaction,
    always rolled back (Do I have time for this?, `commands/fitting.py`). Nothing is logged or kept."""
    spec = REGISTRY.get(name)
    if spec is None or not spec.mutates or not spec.logged:
        raise FieldError("command", f"{name!r} isn't a change Friday can try")
    inp = spec.input_type.model_validate(payload)
    settings = load_settings(conn, user_id)
    conn.execute("BEGIN IMMEDIATE")
    try:
        command_id = log_start(conn, spec, inp, now_utc, "you", user_id, None)
        spec.fn(Ctx(conn, Writer(conn, user_id), now_utc, "you", user_id, settings, command_id), inp)
        if spec.affects_plan:
            bump_generation(conn, user_id)
        return look(conn)
    finally:
        conn.execute("ROLLBACK")


@dataclass
class Tried:
    """One change of several tried together: why it was refused, else the items it made and those it changed."""

    error: str | None = None
    created: list[int] = field(default_factory=list)
    changed: list[int] = field(default_factory=list)


def tried_many[T, S](
    conn: sqlite3.Connection,
    changes: list[tuple[str, dict[str, Any]]],
    look: Callable[[sqlite3.Connection, list[Tried]], T],
    *,
    now_utc: int,
    user_id: int = 1,
    each: Callable[[sqlite3.Connection], S] | None = None,
    resolve: Callable[[dict[str, Any], list["Tried"]], dict[str, Any]] | None = None,
) -> tuple[T, list[S]]:
    """`tried` for several changes in order, in one transaction always rolled back (What if, `commands/whatif.py`).
    Each is kept apart: one refused (a moved event that no longer exists, say) is taken back alone and the rest
    still apply. A rule or setting tried counts for the changes after it. `each` looks after every change; `resolve`
    puts what earlier changes made into a change's input (What if's placeholders)."""
    settings = load_settings(conn, user_id)
    conn.execute("BEGIN IMMEDIATE")
    try:
        done: list[Tried] = []
        seen: list[S] = []
        for n, (name, payload) in enumerate(changes):
            spec = REGISTRY.get(name)
            if spec is None or not spec.mutates or not spec.logged:
                done.append(Tried(error=f"{name!r} isn't a change Friday can try"))
            else:
                conn.execute(f"SAVEPOINT tried_{n}")
                try:
                    inp = spec.input_type.model_validate(resolve(payload, done) if resolve else payload)
                    writer = Writer(conn, user_id)
                    command_id = log_start(conn, spec, inp, now_utc, "you", user_id, None)
                    spec.fn(Ctx(conn, writer, now_utc, "you", user_id, settings, command_id), inp)
                    if spec.affects_plan:
                        bump_generation(conn, user_id)
                    items = [c for c in writer.changes if c["table"] == "items"]
                    made = [int(c["key"]["id"]) for c in items if c["op"] == "insert"]
                    touched = sorted({int(c["key"]["id"]) for c in items if c["op"] != "insert"} - set(made))
                    done.append(Tried(created=made, changed=touched))
                    conn.execute(f"RELEASE tried_{n}")
                except (FieldError, ValidationError, ValueError) as error:
                    conn.execute(f"ROLLBACK TO tried_{n}")
                    conn.execute(f"RELEASE tried_{n}")
                    done.append(Tried(error=str(error)))
                settings = load_settings(conn, user_id)
            if each is not None:
                seen.append(each(conn))
        return look(conn, done), seen
    finally:
        conn.execute("ROLLBACK")


def full_preview(conn: sqlite3.Connection, snapshot: Snapshot, tz: str) -> ChangeOut:
    """Solve a snapshot taken before the rollback, outside the transaction so the solve holds no write lock."""
    plan = plan_snapshot(snapshot, warm=True)
    saved = current_plan(conn, snapshot.user_id)
    before = json.loads(saved["report"]).get("rule_totals", {}) if saved else {}
    titles = {item.id: item.title for item in snapshot.items}

    def title(item_id: int) -> str:
        # An item the previewed command dropped is in the database again after the rollback, not in the snapshot.
        found = titles.get(item_id) or load_item(conn, item_id, snapshot.user_id)
        return found if isinstance(found, str) else found.title if found else f"T{item_id}"

    return change_list(plan.report, before, tz, title)


def log_start(
    conn: sqlite3.Connection,
    spec: Spec,
    inp: BaseModel,
    now_utc: int,
    actor: str,
    user_id: int,
    idempotency_key: str | None,
) -> int:
    cursor = conn.execute(
        "INSERT INTO command_log (user_id, at_utc, actor, command, input, result, idempotency_key) "
        "VALUES (?, ?, ?, ?, ?, '{}', ?)",
        [user_id, format_utc(now_utc), actor, spec.name, inp.model_dump_json(exclude_none=True), idempotency_key],
    )
    return int(cursor.lastrowid or 0)


def changed_items(changes: list[dict[str, Any]]) -> set[int]:
    """Items a command touched directly or through their pins, progress, dependencies or timer."""
    out = set()
    for change in changes:
        row = change.get("after") or change.get("before") or {}
        if change["table"] == "items":
            out.add(change["key"]["id"])
        elif "item_id" in row:
            out.add(row["item_id"])
    return out


def moved_from(ctx: Ctx, inp: BaseModel) -> dict[int, list[tuple[int, int]]]:
    """The block a change moved an item from (a dragged block's `from_start`–`from_end`), which the quick placement
    leaves empty."""
    item, start, end = (getattr(inp, k, None) for k in ("id", "from_start", "from_end"))
    if not isinstance(item, int) or not isinstance(start, str) or not isinstance(end, str):
        return {}
    return {item: [(parse_utc(ctx.utc(start, "from_start")), parse_utc(ctx.utc(end, "from_end")))]}


def bump_generation(conn: sqlite3.Connection, user_id: int) -> None:
    # Not undo data: the generation only ever counts up, and an undo raises it again.
    conn.execute(
        "INSERT INTO kv (user_id, key, value) VALUES (?, 'generation', '1') "
        "ON CONFLICT (user_id, key) DO UPDATE SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT)",
        [user_id],
    )


def dump(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [dump(v) for v in value]
    return value
