"""Friday on your phone over Tailscale, the whole system (C61): a real `fridayd serve` on this Mac. Settings → Phone
switched on over HTTP; within seconds Friday answers at this Mac's Tailscale address too, where a device that isn't
paired is told how to pair; the pairing code from the Mac pairs it, and it then opens Friday. Switched off, the
tailnet address stops answering. Skipped where Tailscale isn't up (GitHub's machines)."""

import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from friday.sync.tailnet import address
from tests.system.test_beat_plan_system import SLEEP, Friday

HERE = address()
pytestmark = pytest.mark.skipif(HERE is None, reason="Tailscale isn't up on this machine")


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("phone"))
    try:
        server.c("settings_set", key="sleep", value=SLEEP)
        yield server
    finally:
        server.stop()


def reach(url: str, **kwargs: object) -> httpx.Response | None:
    try:
        return httpx.get(url, timeout=3, **kwargs)  # type: ignore[arg-type]
    except httpx.HTTPError:
        return None


def waited(check: object, seconds: float = 20) -> object:
    end = time.time() + seconds
    while time.time() < end:
        found = check()  # type: ignore[operator]
        if found:
            return found
        time.sleep(0.5)
    raise TimeoutError("waited too long")


def test_on_the_tailnet_a_device_pairs_by_its_code(friday: Friday, tmp_path: Path) -> None:
    there = f"http://{HERE}:{friday.port}"
    assert reach(f"{there}/api/q/status") is None  # off: nothing answers there
    friday.c("phone_set", on=True)
    refused = waited(lambda: reach(f"{there}/api/q/status"))
    assert refused.status_code == 401 and "Settings → Phone" in refused.json()["message"]  # type: ignore[union-attr]
    code = friday.c("phone_pair")["url"].split("#", 1)[1]
    phone = httpx.Client(base_url=there, timeout=5)
    assert phone.post("/api/pair", json={"code": code, "device": "iPhone"}).status_code == 200
    assert phone.get("/api/q/status").status_code == 200  # paired: the cookie it was given opens Friday
    assert [p["name"] for p in friday.q("phone_status")["phones"]] == ["iPhone"]
    friday.c("phone_set", on=False)
    waited(lambda: reach(f"{there}/api/q/status") is None)


def test_a_borrowed_name_is_refused(friday: Friday) -> None:
    answer = httpx.get(f"http://127.0.0.1:{friday.port}/api/q/status", headers={"host": "evil.example"}, timeout=5)
    assert answer.status_code == 421
