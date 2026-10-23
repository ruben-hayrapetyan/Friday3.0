"""Webhooks (DESIGN §22.8): the body signed with the secret, and a failing receiver tried 3 times."""

import hashlib
import hmac
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from friday.notify import webhooks


def test_a_webhook_is_signed_and_retried_until_it_lands(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def post(url: str, content: bytes, headers: dict[str, str], timeout: float) -> Any:
        calls.append(headers)
        if len(calls) == 1:
            raise httpx.ConnectError("down")
        return SimpleNamespace(is_success=len(calls) == 3)

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(webhooks.time, "sleep", lambda s: None)
    webhooks.send_all(["https://example.test/hook"], b'{"event": "item.done"}', "s3cret")
    expected = hmac.new(b"s3cret", b'{"event": "item.done"}', hashlib.sha256).hexdigest()
    assert len(calls) == 3 and calls[0]["x-friday-signature"] == f"sha256={expected}"
