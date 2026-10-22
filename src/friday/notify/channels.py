"""Sending notifications (DESIGN §20.1): Web Push to the installed app, and ntfy as a fallback. What to send, and
when, is decided in `commands/notify.py`; this module only delivers.
"""

import base64
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01
from pywebpush import WebPushException, webpush

log = logging.getLogger("friday.notify")


@dataclass
class Action:
    label: str
    token: str | None = None  # a signed `act` token the app or ntfy posts back; None just opens `url`
    url: str | None = None


@dataclass
class Message:
    title: str
    body: str
    url: str = "/"  # what a tap opens, inside the app
    actions: list[Action] = field(default_factory=list)
    open_token: str | None = None  # posted when the notification is opened, to record it
    dismiss_token: str | None = None  # posted when it is swiped away


def vapid_keys(folder: Path) -> tuple[Vapid01, str]:
    """The server's VAPID key pair, made once and kept in the data folder, and its public key for the browser."""
    path = folder / "vapid_private.pem"
    vapid = Vapid01()
    if path.exists():
        vapid = Vapid01.from_file(str(path))
    else:
        vapid.generate_keys()
        vapid.save_key(str(path))
        path.chmod(0o600)
    raw = vapid.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return vapid, base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def send_webpush(subscription: dict, message: Message, vapid: Vapid01, contact: str) -> bool:
    """Deliver to one browser; False when the subscription is gone and should be forgotten."""
    payload = {
        "title": message.title,
        "body": message.body,
        "url": message.url,
        "actions": [a.__dict__ for a in message.actions],
        "open_token": message.open_token,
        "dismiss_token": message.dismiss_token,
    }
    try:
        webpush(subscription, json.dumps(payload), vapid_private_key=vapid, vapid_claims={"sub": contact}, ttl=3600)
    except WebPushException as error:
        status = error.response.status_code if error.response is not None else None
        if status in (404, 410):
            return False
        log.warning("web push failed: %s", error)
    return True


def send_ntfy(topic_url: str, message: Message, app_url: str | None) -> None:
    """Post to an ntfy topic. Buttons need `app_url`, where the phone can reach Friday."""
    headers = {"Title": message.title.encode().decode("latin-1", "replace")}
    if app_url:
        base = app_url.rstrip("/")
        headers["Click"] = f"{base}/#{message.url}"
        buttons = [
            f"http, {a.label}, {base}/api/c/act, method=POST, body={json.dumps({'token': a.token})}"
            if a.token
            else f"view, {a.label}, {base}/#{a.url or message.url}"
            for a in message.actions[:3]  # ntfy shows at most three
        ]
        if buttons:
            headers["Actions"] = "; ".join(buttons)
    try:
        httpx.post(topic_url, content=message.body.encode(), headers=headers, timeout=10)
    except httpx.HTTPError as error:
        log.warning("ntfy failed: %s", error)
