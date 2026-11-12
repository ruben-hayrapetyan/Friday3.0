"""Webhooks (DESIGN §22.8): `block.started`, `slack.low`, `plan.changed` and `item.done` POSTed as JSON to the
URLs in the `webhooks` setting, signed with HMAC-SHA256 of the body (`X-Friday-Signature: sha256=<hex>`) when
`[webhooks] secret` is set in `secrets.toml`, and tried 3 times. Sending happens on its own thread, so a slow
receiver never holds up a request or the job loop."""

import hashlib
import hmac
import json
import logging
import threading
import time
import tomllib
from collections.abc import Sequence
from typing import Any

import httpx

from friday.core.integrations import Webhook
from friday.core.paths import secrets_path

log = logging.getLogger("friday.webhooks")
TRIES = 3


def secret() -> str | None:
    path = secrets_path()
    return tomllib.loads(path.read_text()).get("webhooks", {}).get("secret") if path.exists() else None


def fire(hooks: Sequence[Webhook], event: str, data: dict[str, Any]) -> None:
    wanted = [h.url for h in hooks if event in h.events]
    if wanted:
        body = json.dumps({"event": event, "data": data}, default=str).encode()
        threading.Thread(target=send_signed, args=(wanted, body), daemon=True).start()


def send_signed(urls: list[str], body: bytes) -> None:
    """The secret read on the sending thread: a secrets.toml that doesn't read sends nothing, rather than failing the
    change that fired it (audit, 12 Nov: a typo there made `done` answer 500 once it was saved) or going unsigned."""
    try:
        key = secret()
    except (OSError, tomllib.TOMLDecodeError) as error:
        log.warning("webhooks not sent: secrets.toml can't be read (%s)", type(error).__name__)
        return
    send_all(urls, body, key)


def send_all(urls: list[str], body: bytes, key: str | None) -> None:
    headers = {"content-type": "application/json"}
    if key:
        headers["x-friday-signature"] = "sha256=" + hmac.new(key.encode(), body, hashlib.sha256).hexdigest()
    for url in urls:
        send(url, body, headers)


def send(url: str, body: bytes, headers: dict[str, str], pause_s: float = 2.0) -> bool:
    for attempt in range(TRIES):
        try:
            if httpx.post(url, content=body, headers=headers, timeout=10).is_success:
                return True
        except httpx.HTTPError as error:
            log.info("webhook %s: %s", url, error)
        if attempt < TRIES - 1:
            time.sleep(pause_s * (attempt + 1))
    log.warning("webhook %s failed %d times", url, TRIES)
    return False
