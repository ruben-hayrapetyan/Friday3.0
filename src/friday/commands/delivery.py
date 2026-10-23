"""Delivery for the notify job (DESIGN §20.3; the server runs it each minute, as does the simulator): record what
is due and send it on the channels switched on.

Each notification is a row first (its id goes into its buttons' tokens), then a Web Push to every subscribed
browser and an ntfy post. With no channel on, it still shows in the app's list.
"""

import json
import sqlite3
from pathlib import Path

from friday.commands.notify import Outgoing, due_notifications, make_token
from friday.core.db import rows
from friday.core.time import format_utc
from friday.notify.channels import Action, Message, send_ntfy, send_webpush, vapid_keys
from friday.notify.webhooks import fire
from friday.planner.store import load_settings

WEBHOOK_EVENTS = {"block_start": "block.started", "slack_low": "slack.low"}


def deliver(conn: sqlite3.Connection, now_utc: int, folder: Path, user_id: int = 1) -> list[str]:
    """Send what is due; returns the dedup keys sent."""
    outgoing = due_notifications(conn, now_utc, user_id)
    if not outgoing:
        return []
    settings = load_settings(conn, user_id)
    notify = settings["notify"]
    channels = list(notify.channels) or ["app"]
    vapid = vapid_keys(folder)[0] if "webpush" in channels else None
    subscriptions = rows(conn, "SELECT * FROM push_subscriptions WHERE user_id = ?", [user_id])
    for o in outgoing:
        message = record(conn, o, ",".join(channels), now_utc, user_id)
        if vapid is not None:
            for s in subscriptions:
                subscription = {"endpoint": s["endpoint"], "keys": json.loads(s["keys"])}
                if not send_webpush(subscription, message, vapid, notify.contact):
                    conn.execute("DELETE FROM push_subscriptions WHERE id = ?", [s["id"]])
        if "ntfy" in channels and notify.ntfy_url:
            send_ntfy(notify.ntfy_url, message, notify.app_url)
        if o.kind in WEBHOOK_EVENTS:
            fire(settings["webhooks"], WEBHOOK_EVENTS[o.kind], {"item_id": o.item_id, "title": o.title, "body": o.body})
    if any(o.kind == "test" for o in outgoing):
        conn.execute("DELETE FROM kv WHERE user_id = ? AND key = 'notify_test'", [user_id])
    return [o.dedup_key for o in outgoing]


def record(conn: sqlite3.Connection, o: Outgoing, channel: str, now_utc: int, user_id: int) -> Message:
    cursor = conn.execute(
        "INSERT INTO notifications (user_id, kind, item_id, dedup_key, channel, sent_utc, title, body) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [user_id, o.kind, o.item_id, o.dedup_key, channel, format_utc(now_utc), o.title, o.body],
    )
    notification = int(cursor.lastrowid or 0)
    actions = [
        Action(label, url=action.removeprefix("open:"))
        if action.startswith("open:")
        else Action(label, token=make_token(conn, notification, action, now_utc, user_id))
        for label, action in o.actions
    ]
    tokens = [make_token(conn, notification, action, now_utc, user_id) for action in ("open", "dismiss")]
    return Message(o.title, o.body, o.url, actions, *tokens)
