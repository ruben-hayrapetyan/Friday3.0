"""The sync every integration shares (C96), on the Inbox's own pieces (commands/suggesting.py: an input stored once,
an edit when it changes, superseded when it goes):

- Arrival, a setting each integration shows once connected (your answer, 10 Nov): "inbox_first" (the default) puts the
  first read in the Inbox, reviewed together as one batch, then new to-dos go straight in; "straight" and "inbox" do
  the one thing always.
- Each side owns its fields (your answer): the service its title, due, notes and whether it's done; Friday the length
  (after the first read), the kind, pins and where it's planned. An edit from the service changes only its own.
- Gone from the service's open to-dos means done there: done in Friday too, by the sync, so nothing is echoed back.
- Done and reopen in Friday go back (two-way connectors) through source_writes, queued in the command's own
  transaction and sent by the integrations job; a failure is retried, said on the source, never lost.
- Tokens live in secrets.toml (0600), one section per connected source; never in the database, a log or an error."""

import dataclasses
import json
import logging
import sqlite3
import threading
import tomllib
from collections.abc import Callable
from datetime import datetime
from typing import Any

from friday.commands.ai import toml_of
from friday.commands.registry import run
from friday.commands.suggesting import accept_trusted, made_items, store, suggest
from friday.core.db import one, rows
from friday.core.guess import guess_preset
from friday.core.paths import secrets_path
from friday.core.presets import in_use
from friday.core.time import format_local, format_utc, parse_utc, zone
from friday.ingest.ics import Found, Proposed
from friday.integrations.asana import Asana
from friday.integrations.base import Connector, ConnectorError, Remote, Transport
from friday.integrations.canvas import Canvas
from friday.integrations.github import GitHub
from friday.integrations.jira import Jira
from friday.integrations.linear import Linear
from friday.integrations.notion import Notion
from friday.integrations.reminders import Reminders, Things, WaitingForMac
from friday.integrations.todoist import Todoist
from friday.integrations.trello import Trello
from friday.sync.google_auth import write_private

CONNECTORS: dict[str, type] = {
    Todoist.kind: Todoist,
    Reminders.kind: Reminders,
    Notion.kind: Notion,
    Trello.kind: Trello,
    Asana.kind: Asana,
    Linear.kind: Linear,
    Jira.kind: Jira,
    GitHub.kind: GitHub,
    Canvas.kind: Canvas,
    Things.kind: Things,
}
ARRIVALS = ("inbox_first", "straight", "inbox")
SERVICE_OWNS = ("title", "due", "notes", "firmness")  # what an edit from the service may change
MAX_TRIES = 5
POLL_MIN = 10  # how often each integration is read, unless you ask for it now


def is_integration(kind: str) -> bool:
    return kind in CONNECTORS


def section(source_id: int) -> str:
    return f"integration_{source_id}"


def secrets() -> dict[str, dict[str, Any]]:
    path = secrets_path()
    return tomllib.loads(path.read_text()) if path.exists() else {}


def token_of(source_id: int) -> str:
    return str(secrets().get(section(source_id), {}).get("token", ""))


def keep_token(source_id: int, kind: str, token: str) -> None:
    kept = secrets()
    kept[section(source_id)] = {"kind": kind, "token": token.strip()}
    write_private(secrets_path(), toml_of(kept))


def forget_token(source_id: int) -> None:
    kept = secrets()
    if kept.pop(section(source_id), None) is not None:
        write_private(secrets_path(), toml_of(kept))


Make = Callable[[dict[str, Any]], Connector]


# A fake service per kind, in tests (tests/integrations/kit.py); empty, connectors reach the real services.
TRANSPORTS: dict[str, Transport] = {}


def connector_for(source: dict[str, Any], transport: Transport = None) -> Connector:
    """The connector a connected source reads with: its kind's, its token, its settings."""
    config = json.loads(source["config"] or "{}")
    kind = source["kind"]
    return CONNECTORS[kind](token_of(int(source["id"])), config, transport or TRANSPORTS.get(kind))


def fields_of(r: Remote, kind: str | None = None) -> dict[str, Any]:
    """An add from a remote to-do: the kind its title says (an exam's prep), else the integration's own (`kind`, C97:
    a Task from a to-do app, a Work task from a tracker); a due that's only the day you meant, soft."""
    notes = "\n\n".join(x for x in (r.notes.strip(), r.url or "") if x)
    out: dict[str, Any] = {"title": r.title, "notes": notes or None, "preset": kind}
    if r.due:
        out["due"] = r.due if "T" in r.due else f"{r.due}T23:59"  # a whole day: due by its end
        out["firmness"] = "hard" if r.firm else "soft"
    if r.minutes:
        out["duration_min"] = r.minutes
    return {k: v for k, v in out.items() if v is not None}


def local_due(due: str | None, timezone: str | None) -> str | None:
    """A due as Friday keeps it, on your clock: a time with an offset or in UTC ("…Z", Todoist's fixed-zone times,
    Notion's every time) at the same moment in your timezone; a day, or a time already local, as it is."""
    if not due or "T" not in due or not timezone:
        return due
    try:
        moment = datetime.fromisoformat(due.replace("Z", "+00:00"))
    except ValueError:
        return due
    if moment.tzinfo is None:
        return due[:16]
    return format_local(moment.astimezone(zone(timezone)).replace(tzinfo=None))


def kind_for(r: Remote, connector: Connector, settings: dict) -> str | None:
    """The kind the title says, if it says one you use; else the integration's, if you have it."""
    kinds = in_use(settings["presets"], settings["school"])
    if guess_preset(r.title, kinds):
        return None  # `add` reads it from the title, as for anything you type
    return connector.caps.kind if connector.caps.kind in kinds else None


def said_of(r: Remote) -> str:
    """The to-do as the Inbox shows it under "From the source": what the service has, in lines, not a record."""
    lines = [r.title]
    if r.due:
        lines.append(f"Due {r.due.replace('T', ' at ')}")
    if r.minutes:
        lines.append(f"Length {r.minutes} min")
    if r.notes.strip():
        lines += ["", r.notes.strip()]
    if r.url:
        lines += ["", r.url]
    return "\n".join(lines)


def found_of(r: Remote, kind: str | None = None) -> Found:
    return Found(r.external_id, r.digest(), r.title, said_of(r), [Proposed("add", fields_of(r, kind))])


def sync_source(
    conn: sqlite3.Connection,
    source: dict[str, Any],
    connector: Connector,
    settings: dict,
    now_utc: int,
    user_id: int = 1,
) -> int:
    """Read one integration and bring in what's new, changed or done there; returns the suggestions made."""
    config = json.loads(source["config"] or "{}")
    if hasattr(connector, "load"):  # one the Mac app feeds (Apple Reminders): what it last sent
        connector.load(conn, user_id)
    try:
        remotes = [r for r in connector.read() if not r.done]
    except WaitingForMac:
        return 0  # connected, the Mac app not heard from yet: nothing read, so nothing taken as done
    except ConnectorError as error:
        conn.execute(
            "UPDATE sources SET last_error = ?, failures = failures + 1, last_sync_utc = ? WHERE id = ?",
            [str(error), format_utc(now_utc), source["id"]],
        )
        return 0
    conn.execute(
        "UPDATE sources SET last_error = NULL, failures = 0, last_sync_utc = ? WHERE id = ?",
        [format_utc(now_utc), source["id"]],
    )
    if hasattr(connector, "adopt"):  # what another source already brought (the Canvas feed's assignments)
        connector.adopt(conn, source)
    first = not config.get("synced")
    arrival = config.get("arrival", "inbox_first")
    straight = arrival == "straight" or (arrival == "inbox_first" and not first)
    batch = f"integration:{source['id']}:first" if first and not straight else None
    made = 0
    for r in remotes:
        r = dataclasses.replace(r, due=local_due(r.due, settings["time"].timezone))
        f = found_of(r, kind_for(r, connector, settings))
        raw_id = store(conn, int(source["id"]), f, now_utc, user_id)
        if raw_id is None:
            continue
        before = made_items(conn, raw_id)
        proposals = f.proposals
        if before:  # an edit: only what the service owns
            proposals = [Proposed("add", {k: v for k, v in p.input.items() if k in SERVICE_OWNS}) for p in proposals]
        made += suggest(conn, settings, now_utc, user_id, raw_id, proposals, False, source["name"], batch)
        conn.execute("UPDATE raw_inputs SET status = 'extracted' WHERE id = ?", [raw_id])
        if straight or (before and arrival != "inbox"):
            for s in rows(conn, "SELECT id FROM suggestions WHERE raw_input_id = ? AND status = 'pending'", [raw_id]):
                accept_trusted(conn, now_utc, user_id, int(s["id"]), source["name"])
    done_there(conn, source, {r.external_id for r in remotes}, now_utc, user_id)
    if first:
        synced = json.dumps(config | {"synced": True})
        conn.execute("UPDATE sources SET config = ? WHERE id = ?", [synced, source["id"]])
    return made


def done_there(
    conn: sqlite3.Connection, source: dict[str, Any], open_now: set[str], now_utc: int, user_id: int
) -> None:
    """To-dos no longer open there were done (or deleted) there: their suggestions withdrawn, their items done here."""
    for r in rows(
        conn, "SELECT id, external_id FROM raw_inputs WHERE source_id = ? AND status != 'ignored'", [source["id"]]
    ):
        if r["external_id"] in open_now:
            continue
        conn.execute(
            "UPDATE suggestions SET status = 'superseded' WHERE raw_input_id = ? AND status = 'pending'", [r["id"]]
        )
        conn.execute("UPDATE raw_inputs SET status = 'ignored' WHERE id = ?", [r["id"]])
        for item in made_items(conn, int(r["id"])):
            run(conn, "done", {"id": item["id"]}, now_utc=now_utc, actor=f"sync:{source['name']}", user_id=user_id,
                provisional=False)  # fmt: skip


def origin(conn: sqlite3.Connection, item_id: int) -> dict[str, Any] | None:
    """The integration and remote id an item came from, if it came from one."""
    found = one(
        conn,
        "SELECT so.id AS source_id, so.kind, so.enabled, r.external_id FROM suggestions s "
        "JOIN raw_inputs r ON r.id = s.raw_input_id JOIN sources so ON so.id = r.source_id "
        "WHERE s.item_id = ? AND s.status = 'accepted' ORDER BY s.id DESC LIMIT 1",
        [item_id],
    )
    return found if found and is_integration(found["kind"]) else None


def queue_write(conn: sqlite3.Connection, item_id: int, op: str, actor: str, now_utc: int, user_id: int) -> None:
    """Done or reopened in Friday: the same there, sent soon. Never what the sync itself did (it came from there)."""
    if actor.startswith("sync:"):
        return
    came = origin(conn, item_id)
    if not came or not came["enabled"] or not CONNECTORS[came["kind"]].caps.two_way:
        return
    conn.execute(
        "INSERT INTO source_writes (user_id, source_id, external_id, item_id, op, created_utc) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [user_id, came["source_id"], came["external_id"], item_id, op, format_utc(now_utc)],
    )
    WAKE.set()


log = logging.getLogger("friday.integrations")
WAKE = threading.Event()  # set when something is queued to go back: the sender sends it at once (your "yes", C97)
SETTLE_S = 0.5  # the command that queued it commits first; one rolled back or undone leaves nothing to send


class Sender:
    """Sends done and reopen back the moment they're queued, not at the integrations job's minute (which still sends
    anything this missed). Its own thread and connection; a failure is kept for the retry, never raised."""

    def __init__(self, db_path: Any, clock: Callable[[], int]):
        self.db_path, self.clock = db_path, clock
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self.loop, name="friday-integrations-sender", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stopping.set()
        WAKE.set()
        self.thread.join(1)

    def loop(self) -> None:
        from friday.core.db import connect

        conn = connect(self.db_path)
        while not self.stopping.is_set():
            if not WAKE.wait(5):
                continue
            WAKE.clear()
            if self.stopping.wait(SETTLE_S):
                break
            try:
                send_writes(conn, self.clock())
            except Exception:  # a bad write mustn't stop the sender; the job's minute tries again
                log.exception("sending to integrations")
        conn.close()


def send_writes(
    conn: sqlite3.Connection, now_utc: int, make: Callable[[dict[str, Any]], Connector] = connector_for
) -> int:
    """What waits to go back, oldest first, each to its integration; a failure is kept and retried, then said."""
    sent = 0
    for w in rows(
        conn,
        "SELECT w.*, s.kind, s.config, s.name FROM source_writes w JOIN sources s ON s.id = w.source_id "
        "WHERE w.done_utc IS NULL AND w.tries < ? AND s.enabled = 1 ORDER BY w.id",
        [MAX_TRIES],
    ):
        if CONNECTORS[w["kind"]].caps.on_mac:
            continue  # the Mac app sends these (reminder_writes)
        source = {"id": w["source_id"], "kind": w["kind"], "config": w["config"], "name": w["name"]}
        try:
            make(source).write(w["external_id"], w["op"])
        except ConnectorError as error:
            conn.execute("UPDATE source_writes SET tries = tries + 1, error = ? WHERE id = ?", [str(error), w["id"]])
            if w["tries"] + 1 >= MAX_TRIES:
                said = f"Couldn't mark it {w['op'] if w['op'] == 'done' else 'open'} in {w['name']}: {error}"
                conn.execute("UPDATE sources SET last_error = ? WHERE id = ?", [said, w["source_id"]])
            continue
        conn.execute("UPDATE source_writes SET done_utc = ?, error = NULL WHERE id = ?", [format_utc(now_utc), w["id"]])
        sent += 1
    return sent


def due_now(source: dict[str, Any], now_utc: int, asked: bool) -> bool:
    """Read now: asked to (Sync now, just connected), or POLL_MIN since the last read."""
    if asked or not source["last_sync_utc"]:
        return True
    return now_utc - parse_utc(source["last_sync_utc"]) >= POLL_MIN


def sync_all(
    conn: sqlite3.Connection,
    settings: dict,
    now_utc: int,
    user_id: int = 1,
    asked: bool = False,
    make: Callable[[dict[str, Any]], Connector] = connector_for,
) -> int:
    """Every connected integration that's due, then what waits to go back."""
    made = 0
    for source in rows(conn, "SELECT * FROM sources WHERE user_id = ? AND enabled = 1", [user_id]):
        if is_integration(source["kind"]) and due_now(source, now_utc, asked):
            made += sync_source(conn, source, make(source), settings, now_utc, user_id)
    send_writes(conn, now_utc, make)
    return made
