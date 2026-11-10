"""scripts/live-check.py itself (C96), run as you would run it, against the fake Todoist on a real port instead of
your account: every step passes, it cleans up after itself, never prints the token, and says when the fake and the
service's answers differ in shape."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from tests.integrations.fake_todoist import HARNESS, FakeTodoist
from tests.integrations.kit import serve

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("live_check", REPO / "scripts" / "live-check.py")
live_check = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(live_check)  # type: ignore[union-attr]
differences, shape = live_check.differences, live_check.shape


def run(fake: FakeTodoist) -> subprocess.CompletedProcess:
    address, stop = serve(fake)
    try:
        env = os.environ | {"FRIDAY_LIVE_TOKEN": HARNESS.token, "FRIDAY_API_TODOIST": f"{address}/api/v1"}
        return subprocess.run([sys.executable, str(REPO / "scripts" / "live-check.py"), "todoist"], env=env,
                              capture_output=True, text=True, timeout=120, cwd=REPO)  # fmt: skip
    finally:
        stop()


def test_every_step_passes_against_a_service_that_works_and_its_task_is_deleted() -> None:
    fake = FakeTodoist(HARNESS.token)
    done = run(fake)
    assert done.returncode == 0, done.stdout + done.stderr
    for said in ("token works", "reads with its due and length", "closes it there", "reopens it there",
                 "deleted", "the fake matches"):  # fmt: skip
        assert said in done.stdout, done.stdout
    assert all(t["is_deleted"] for t in fake.tasks.values() if t["content"].startswith("Live check"))
    assert HARNESS.token not in done.stdout + done.stderr


def test_a_service_that_breaks_a_step_is_said_and_fails() -> None:
    class NeverCloses(FakeTodoist):
        def respond(self, request):  # noqa: ANN001, ANN202
            if request.url.path.endswith("/close"):
                import httpx

                return httpx.Response(204)  # says yes, does nothing
            return super().respond(request)

    done = run(NeverCloses(HARNESS.token))
    assert done.returncode == 1 and "done here, still open there" in done.stdout


def test_drift_in_the_answers_shape_is_named() -> None:
    real = {"id": "1", "content": "x", "due": {"date": "d"}, "new_field": 3}
    fake = {"id": "1", "content": "x", "due": None}
    said = differences(shape(real), shape(fake))
    assert any("new_field" in d and "the fake doesn't" in d for d in said)
    assert not any(".due" in d for d in said)  # null in the fake stands for any value
