"""Webhooks (DESIGN §22.8): only the URLs that asked for an event get it, signed with the secret from `secrets.toml`
when there is one, and a receiver that never answers is given up on after 3 tries."""

import hashlib
import hmac
import json
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from friday.core.integrations import Webhook
from friday.core.paths import secrets_path
from friday.notify import webhooks


def test_without_a_secrets_file_or_its_webhooks_section_nothing_signs(no_personal_config: Path) -> None:
    assert not secrets_path().exists() and webhooks.secret() is None
    secrets_path().write_text('[google]\nclient = "x"\n')
    assert webhooks.secret() is None
    secrets_path().write_text('[webhooks]\nsecret = "s3cret"\n')
    assert webhooks.secret() == "s3cret"


def test_an_event_goes_only_to_the_urls_that_asked_for_it_signed(
    no_personal_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secrets_path().write_text('[webhooks]\nsecret = "s3cret"\n')
    sent: list[tuple[str, bytes, dict[str, str]]] = []
    landed = threading.Event()

    def post(url: str, content: bytes, headers: dict[str, str], timeout: float) -> Any:
        sent.append((url, content, headers))
        landed.set()
        return SimpleNamespace(is_success=True)

    monkeypatch.setattr(httpx, "post", post)
    hooks = [Webhook(url="https://a.test/done", events=("item.done",)), Webhook(url="https://b.test/plan",
             events=("plan.changed",))]  # fmt: skip
    webhooks.fire(hooks, "slack.low", {"x": 1})  # nobody asked: no thread, nothing sent
    webhooks.fire(hooks, "item.done", {"id": 3})
    assert landed.wait(5)
    [(url, body, headers)] = sent
    assert url == "https://a.test/done" and json.loads(body) == {"event": "item.done", "data": {"id": 3}}
    assert headers["x-friday-signature"] == "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()


def test_unsigned_without_a_secret_and_given_up_after_three_tries(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    calls: list[dict[str, str]] = []
    pauses: list[float] = []

    def post(url: str, content: bytes, headers: dict[str, str], timeout: float) -> Any:
        calls.append(headers)
        return SimpleNamespace(is_success=False)

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(webhooks.time, "sleep", pauses.append)
    webhooks.send_all(["https://example.test/hook"], b"{}", None)
    assert len(calls) == 3 and "x-friday-signature" not in calls[0]
    assert pauses == [2.0, 4.0]  # a longer wait before each retry, none after the last
    assert "failed 3 times" in caplog.text
