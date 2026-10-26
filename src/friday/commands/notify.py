"""Notifications (DESIGN §20): what is due this minute, and signed action tokens; the commands `act`,
`push_subscribe`, `push_unsubscribe` and `notify_test`; the queries `notifications` and `push_key`.

The server's notify job asks `due_notifications` every minute, records each one, and delivers it
(`notify/channels.py`). A notification's buttons carry tokens that `act` checks and runs as you.
"""

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from friday.api.commands import ActInput, Changed, DoneInput, EndpointInput, PushSubscription, SettleInput, StartInput
from friday.api.types import Empty
from friday.commands.items import done
from friday.commands.progress import settle, start
from friday.commands.registry import Ctx, command, query, run
from friday.core.db import one, rows
from friday.core.items import FieldError
from friday.core.settings import bedtime_minutes, minutes_of
from friday.core.time import (
    ampm,
    format_local,
    format_utc,
    local_midnight,
    parse_local,
    planning_date,
    to_local,
    to_utc,
)
from friday.planner.build import sleep_on
from friday.planner.prepare import block_key
from friday.planner.snapshot import day_overrides
from friday.planner.store import kv_get, load_settings

WINDOW_MIN = 120  # a timed notification still goes out this long after its time, if the server was asleep then
UNCAPPED = {"slack_low", "overload", "check", "test"}  # these go out even past the daily cap
DEADLINE_WARNINGS = {"slack_low", "overload", "test"}  # these get through while a timer runs, when you hold the rest
TOKEN_MIN = 60
SNOOZE_MIN = 15


@dataclass
class Outgoing:
    kind: str
    dedup_key: str
    title: str
    body: str
    url: str = "/"  # inside the app
    item_id: int | None = None
    actions: list[tuple[str, str]] = field(default_factory=list)  # (label, action): see `act`, or "open:<url>"
    urgent: bool = False  # sent in quiet hours too


@dataclass
class Day:
    """Where now falls in the planning day, in minutes after its local midnight (past 1440 after midnight)."""

    today: date
    minute: int
    wake: int
    bedtime: int


def day_now(conn: sqlite3.Connection, settings: dict[str, Any], now_utc: int, user_id: int) -> Day:
    tz, day_start = settings["time"].timezone, minutes_of(settings["time"].day_start)
    today = planning_date(now_utc, tz, day_start)
    minute = int((to_local(now_utc, tz) - local_midnight(today)).total_seconds() // 60)
    night = sleep_on(settings, day_overrides(conn, user_id), today)
    return Day(today, minute, minutes_of(night.wake), bedtime_minutes(night.bedtime, night.wake, day_start))


def due_notifications(conn: sqlite3.Connection, now_utc: int, user_id: int = 1) -> list[Outgoing]:
    """What should go out now: due, switched on, not sent before, outside quiet hours and under the daily cap."""
    settings = load_settings(conn, user_id)
    if settings["time"].timezone is None or settings["sleep"] is None:
        return []

    def ask(name: str, **params: Any) -> Any:
        return run(conn, name, params, now_utc=now_utc, user_id=user_id).result

    day = day_now(conn, settings, now_utc, user_id)
    found = timed(ask, settings, day) + watched(conn, ask, settings, now_utc, user_id)
    if (test := kv_get(conn, "notify_test", None, user_id)) is not None:
        found.append(Outgoing("test", f"test:{test}", "Friday", "Notifications work.", urgent=True))
    types = settings["notify"].types
    sent = already_sent(conn, [o.dedup_key for o in found])
    quiet = is_quiet(settings["notify"].quiet, day)
    held = settings["notify"].hold_while_timing and one(conn, "SELECT 1 FROM timer WHERE user_id = ?", [user_id])
    fresh = [
        o
        for o in found
        if types.get(o.kind, True)
        and o.dedup_key not in sent
        and (o.urgent or not quiet)
        and (not held or o.kind in DEADLINE_WARNINGS)
    ]
    room = settings["notify"].max_per_day - sent_today(conn, settings, day, user_id)
    capped = [o for o in fresh if o.kind not in UNCAPPED][: max(0, room)]
    return [o for o in fresh if o.kind in UNCAPPED or o in capped]


def is_quiet(window: tuple[str, str] | None, day: Day) -> bool:
    """Inside your quiet hours, or, without them, between bedtime and wake."""
    if window is None:
        return day.minute >= day.bedtime or day.minute < day.wake
    start, end, minute = minutes_of(window[0]), minutes_of(window[1]), day.minute % 1440
    return start <= minute < end if start <= end else minute >= start or minute < end


def already_sent(conn: sqlite3.Connection, keys: list[str]) -> set[str]:
    if not keys:
        return set()
    marks = ", ".join("?" * len(keys))
    return {
        r["dedup_key"] for r in rows(conn, f"SELECT dedup_key FROM notifications WHERE dedup_key IN ({marks})", keys)
    }


def sent_today(conn: sqlite3.Connection, settings: dict[str, Any], day: Day, user_id: int) -> int:
    start = to_utc(
        local_midnight(day.today) + timedelta(minutes=minutes_of(settings["time"].day_start)), settings["time"].timezone
    )
    found = one(
        conn,
        "SELECT count(*) AS n FROM notifications WHERE user_id = ? AND sent_utc >= ? AND kind != 'test'",
        [user_id, format_utc(start)],
    )
    return found["n"] if found else 0


def timed(ask: Any, settings: dict[str, Any], day: Day) -> list[Outgoing]:
    """The morning brief, the evening review and the weekly review, at their times (§20.2)."""
    notify, out = settings["notify"], []
    brief_at = minutes_of(notify.brief_at) if notify.brief_at else day.wake + 30
    review_at = minutes_of(notify.review_at) if notify.review_at else day.bedtime - 60
    if brief_at <= day.minute < brief_at + WINDOW_MIN:
        brief = ask("brief")
        out.append(Outgoing("morning_brief", f"brief:{day.today}", "Today", brief["text"], "/"))
    if review_at <= day.minute < review_at + WINDOW_MIN and not ask("review")["reviewed"]:
        out.append(
            Outgoing(
                "evening_review",
                f"review:{day.today}",
                "Review today (30 s)",
                "How did today go? Mark what got done.",
                "/review",
            )
        )
    last_day = (settings["time"].grid_spec().week_start + 6) % 7
    if day.today.weekday() == last_day and review_at <= day.minute < review_at + WINDOW_MIN:
        out.append(Outgoing("weekly_review", f"week:{day.today}", "Your week", "See how the week went.", "/week"))
    return out


def watched(conn: sqlite3.Connection, ask: Any, settings: dict[str, Any], now_utc: int, user_id: int) -> list[Outgoing]:
    """Block starts, low slack, overload, a waiting plan, and blocks that may not have happened (§20.2)."""
    now, status, out = ask("now"), ask("status"), []
    here = format_local(to_local(now_utc, settings["time"].timezone))
    current = now["current"]
    if current and minutes_between(current["start"], here) < 5:
        out.append(block_start(current, f"start:{current['key']}"))
    for key in snoozed(conn, now_utc, user_id):
        if current and key == f"start:{current['key']}":
            out.append(block_start(current, f"{key}:again"))
    for alert in now["alerts"]:
        item, title = alert["item_id"], alert["title"]
        if alert["kind"] == "triage":
            out.append(
                Outgoing(
                    "overload",
                    f"overload:{item}:{here[:10]}",
                    f"{title} won't fit before its due",
                    "See ways to make room.",
                    "/?triage",
                    item,
                    [("Options", "open:/?triage")],
                )
            )
            continue
        slack = minutes_between(here, alert["latest_start"])
        if slack <= settings["executor"].notify_minutes:
            out.append(
                Outgoing(
                    "slack_low",
                    f"slack:{item}:{here[:10]}",
                    f"Start {title} by {ampm(alert['latest_start'])}",
                    f"{max(0, slack)} min of slack left.",
                    "/",
                    item,
                    [("Start", f"start:{item}"), ("Options", "open:/?triage")],
                    urgent=slack < 30,
                )
            )
    if status["conflicts"]:
        pins = ",".join(str(c["pin_id"]) for c in status["conflicts"])
        out.append(
            Outgoing(
                "conflict",
                f"conflict:{pins}",
                "Locks are making work late",
                "The new plan waits for you.",
                "/",
                None,
                [("Review", "open:/")],
            )
        )
    return out + checks(conn, ask, settings["time"].timezone, here, user_id)


def block_start(block: dict[str, Any], key: str) -> Outgoing:
    return Outgoing(
        "block_start",
        key,
        f"Now: {block['title']}",
        f"Until {ampm(block['end'])}",
        "/",
        block["item_id"],
        [("Start", f"start:{block['item_id']}"), ("Snooze 15", f"snooze:{key}"), ("Swap", "open:/")],
    )


def checks(conn: sqlite3.Connection, ask: Any, tz: str, here: str, user_id: int) -> list[Outgoing]:
    """A hard item's last block before its due ended in the past hour with nothing recorded: until the review it
    counts as done, so ask now, while there's still time (decision 105)."""
    day = here[:10]
    blocks = ask("plan", start=f"{day}T00:00", end=here)["blocks"]
    out = []
    for block in blocks:
        ended = minutes_between(block["end"], here)
        if not 0 <= ended < 60:
            continue
        item = ask("item", id=block["item_id"])
        it, later = item["item"], [b for b in item["blocks"] if b["start"] > block["start"]]
        if it["firmness"] != "hard" or not it["due"] or it["status"] != "todo":
            continue
        if any(b["start"] < it["due"] for b in later) or recorded(conn, block, tz, user_id):
            continue
        out.append(
            Outgoing(
                "check",
                f"check:{block['key']}",
                f"Did you finish {it['title']}?",
                f"It's due {it['due'][5:].replace('T', ' ')}.",
                "/",
                it["id"],
                [("Yes, done", f"done:{it['id']}"), ("Not yet", f"settle:{block['key']}:not_done")],
                urgent=True,
            )
        )
    return out


def recorded(conn: sqlite3.Connection, block: dict[str, Any], tz: str, user_id: int) -> bool:
    """A running timer on the item, a timer session over the block, or an answer for it."""
    start, end = (to_utc(parse_local(block[side]), tz) for side in ("start", "end"))
    found = one(
        conn,
        "SELECT 1 FROM progress p JOIN items i ON i.id = p.item_id WHERE i.user_id = ? AND p.item_id = ? "
        "AND (p.block_key = ? OR (p.source = 'timer' AND p.start_utc < ? AND p.end_utc > ?))",
        [user_id, block["item_id"], block_key(block["item_id"], start), format_utc(end), format_utc(start)],
    )
    timing = one(conn, "SELECT 1 FROM timer WHERE user_id = ? AND item_id = ?", [user_id, block["item_id"]])
    return found is not None or timing is not None


def minutes_between(start: str, end: str) -> int:
    return int((parse_local(end) - parse_local(start)).total_seconds() // 60)


def snoozed(conn: sqlite3.Connection, now_utc: int, user_id: int) -> list[str]:
    found = rows(conn, "SELECT key, value FROM kv WHERE user_id = ? AND key LIKE 'snooze:%'", [user_id])
    return [r["key"].removeprefix("snooze:") for r in found if int(json.loads(r["value"])) <= now_utc]


def secret(conn: sqlite3.Connection, user_id: int) -> bytes:
    """The key tokens are signed with, made on first use."""
    value = kv_get(conn, "action_secret", None, user_id)
    if value is None:
        value = secrets.token_hex(32)
        conn.execute(
            "INSERT OR IGNORE INTO kv (user_id, key, value) VALUES (?, 'action_secret', ?)",
            [user_id, json.dumps(value)],
        )
        value = kv_get(conn, "action_secret", None, user_id)
    return bytes.fromhex(value)


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make_token(conn: sqlite3.Connection, notification_id: int, action: str, now_utc: int, user_id: int = 1) -> str:
    """A token for one button: which notification, what it does, until when, and a nonce so it works once."""
    body = json.dumps({"n": notification_id, "a": action, "x": now_utc + TOKEN_MIN, "o": secrets.token_hex(8)})
    signature = hmac.new(secret(conn, user_id), body.encode(), hashlib.sha256).digest()
    return f"{b64(body.encode())}.{b64(signature)}"


def read_token(ctx: Ctx, token: str) -> dict[str, Any]:
    try:
        body_part, signature_part = token.split(".")
        body = base64.urlsafe_b64decode(body_part + "=" * (-len(body_part) % 4))
        signature = base64.urlsafe_b64decode(signature_part + "=" * (-len(signature_part) % 4))
    except ValueError as error:
        raise FieldError("token", "not a Friday token") from error
    expected = hmac.new(secret(ctx.conn, ctx.user_id), body, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise FieldError("token", "not a Friday token")
    payload = json.loads(body)
    if payload["x"] < ctx.now_utc:
        raise FieldError("token", "this button has expired; open the app instead")
    if kv_get(ctx.conn, f"used:{payload['o']}", None, ctx.user_id) is not None:
        raise FieldError("token", "this button was already used")
    return payload


@command("act", affects_plan=True)
def act(ctx: Ctx, inp: ActInput) -> Changed:
    """Run a notification's button: start, done, settle a block, snooze, or record that it was opened or dismissed."""
    payload = read_token(ctx, inp.token)
    action = payload["a"]
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": f"used:{payload['o']}"}, {"value": json.dumps(ctx.now_text)})
    ctx.db.update("notifications", {"id": payload["n"]}, {"acted": 0 if action == "dismiss" else 1})
    verb, _, rest = action.partition(":")
    if verb == "start":
        start(ctx, StartInput(id=int(rest)))
        return Changed(message="Timer started")
    if verb == "done":
        done(ctx, DoneInput(id=int(rest)))
        return Changed(message="Marked done")
    if verb == "settle":
        key, _, status = rest.rpartition(":")
        return settle(ctx, SettleInput(block_key=key, status=status))  # type: ignore[arg-type]
    if verb == "snooze":
        ctx.db.upsert(
            "kv", {"user_id": ctx.user_id, "key": f"snooze:{rest}"}, {"value": json.dumps(ctx.now_utc + SNOOZE_MIN)}
        )
        return Changed(message=f"Snoozed {SNOOZE_MIN} min")
    return Changed(message="Noted")


@command("push_subscribe")
def push_subscribe(ctx: Ctx, inp: PushSubscription) -> Changed:
    """Send Web Push to this browser."""
    ctx.db.upsert(
        "push_subscriptions",
        {"user_id": ctx.user_id, "endpoint": inp.endpoint},
        {"keys": json.dumps(inp.keys), "created_utc": ctx.now_text},
    )
    return Changed(message="Notifications on for this device")


@command("push_unsubscribe")
def push_unsubscribe(ctx: Ctx, inp: EndpointInput) -> Changed:
    """Stop Web Push to this browser."""
    found = one(ctx.conn, "SELECT id FROM push_subscriptions WHERE endpoint = ?", [inp.endpoint])
    if found:
        ctx.db.delete("push_subscriptions", {"id": found["id"]})
    return Changed(message="Notifications off for this device")


@command("notify_test", logged=False)  # a nudge to the notify job, not a change to undo
def notify_test(ctx: Ctx, inp: Empty) -> Changed:
    """Send a test notification on every channel within the minute."""
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "notify_test"}, {"value": json.dumps(ctx.now_text)})
    return Changed(message="A test notification goes out within a minute")


@query("notifications")
def notifications(ctx: Ctx, inp: Empty) -> list[dict[str, Any]]:
    """The 30 most recent notifications, newest first, and whether each was acted on."""
    found = rows(ctx.conn, "SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT 30", [ctx.user_id])
    return [
        {
            "id": r["id"],
            "kind": r["kind"],
            "item_id": r["item_id"],
            "key": r["dedup_key"],
            "title": r["title"],
            "body": r["body"],
            "sent": ctx.local(r["sent_utc"]),
            "acted": None if r["acted"] is None else bool(r["acted"]),
        }
        for r in found
    ]


@query("push_key")
def push_key(ctx: Ctx, inp: Empty) -> dict[str, Any]:
    """The server's public key for Web Push, and the channels switched on."""
    return {
        "key": kv_get(ctx.conn, "vapid_public", None, ctx.user_id),
        "channels": list(ctx.settings["notify"].channels),
    }
