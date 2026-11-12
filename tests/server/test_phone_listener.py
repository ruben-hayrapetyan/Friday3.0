"""The tailnet listener's own thread (server/phone.py): a check that fails is logged and the next one still runs,
and stopping ends the thread."""

import threading

import pytest

from friday.server.phone import Tailnet, TailnetListener

NAME = "mac.example.ts.net"
ADDRESS = "100.101.1.2"


def test_a_failed_check_is_logged_and_the_next_one_runs(caplog: pytest.LogCaptureFixture) -> None:
    checks: list[int] = []
    known = threading.Event()

    def read() -> tuple[str | None, str | None]:
        checks.append(1)
        if len(checks) == 1:
            raise OSError("tailscale isn't answering")
        known.set()
        return ADDRESS, NAME

    tailnet = Tailnet()
    listener = TailnetListener(object(), 8765, lambda: True, tailnet, read, every_s=0.01, bind=False)
    listener.start()
    try:
        assert known.wait(5)
    finally:
        listener.stop()
        listener.join(5)
    assert not listener.is_alive()
    assert (tailnet.address, tailnet.name) == (ADDRESS, NAME)
    assert "checking the tailnet failed" in caplog.text
