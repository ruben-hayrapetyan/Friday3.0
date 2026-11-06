"""Black box: the Mac app as someone downloads it (HOSTED.md H108–H111, on rhayrapetyan/download-site). A copy of
Mac/build/Friday.app, moved somewhere else as a download is, runs Friday's server from its own Python as the app does
(Server.swift's bundled launcher), plans a sample week at once with the planner compiled in the build, serves the
website from inside itself, reads nothing of the repo and writes nothing into itself. Skipped until `Mac/build.sh` has
built the app."""

import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from tests.system.test_beat_plan_system import REPO, free_port

BUILT = REPO / "Mac" / "build" / "Friday.app"
pytestmark = pytest.mark.skipif(sys.platform != "darwin" or not BUILT.exists(), reason="Mac/build.sh builds the app")


def snapshot(app: Path) -> dict[str, float]:
    return {str(p.relative_to(app)): p.stat().st_mtime for p in app.rglob("*") if p.is_file()}


class Downloaded:
    """A copy of the built app in a new place, and its server started the way the app starts it."""

    def __init__(self, folder: Path) -> None:
        self.app = folder / "Downloads" / "Friday.app"
        self.app.parent.mkdir()
        subprocess.run(["ditto", str(BUILT), str(self.app)], check=True)
        self.python = self.app / "Contents/Resources/friday/python/bin/python3.12"
        self.before = snapshot(self.app)
        self.port = free_port()
        support = folder / "Library" / "Application Support" / "Friday"
        env = {"PATH": "/usr/bin:/bin", "HOME": str(folder), "NUMBA_CPU_NAME": "generic",
               "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
               "FRIDAY_DATA_DIR": str(support), "FRIDAY_CONFIG": str(support / "friday.toml")}  # fmt: skip
        self.started = time.monotonic()
        self.process = subprocess.Popen(
            [str(self.python), "-m", "friday.server.main", "--data-dir", str(folder / "demo"), "demo", "--port",
             str(self.port), "--case", "maya"],
            cwd=folder, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
        )  # fmt: skip
        self.http = httpx.Client(base_url=f"http://127.0.0.1:{self.port}", timeout=30)
        self.first_plan = self.wait_for_plan()

    def wait_for_plan(self) -> float:
        for _ in range(480):
            try:
                if self.http.get("/api/q/status").json().get("plan_id") is not None:
                    return time.monotonic() - self.started
            except (httpx.HTTPError, ValueError):
                pass
            time.sleep(0.25)
        raise RuntimeError("the app's server made no plan in two minutes")

    def run(self, code: str) -> str:
        done = subprocess.run([str(self.python), "-c", code], env={"PATH": "/usr/bin:/bin", "PYTHONNOUSERSITE": "1"},
                              capture_output=True, text=True, timeout=120, check=True)  # fmt: skip
        return done.stdout.strip()

    def stop(self) -> None:
        self.process.terminate()
        self.process.wait(15)


@pytest.fixture(scope="module")
def downloaded(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Downloaded]:
    app = Downloaded(tmp_path_factory.mktemp("mac"))
    yield app
    app.stop()


def test_a_downloaded_copy_plans_a_week_at_once_with_the_planner_compiled_in_the_build(downloaded: Downloaded) -> None:
    # Compiling the planner takes over a minute (scripts/deploy.sh's note); compiled in the build, seconds.
    assert downloaded.first_plan < 45, f"first plan after {downloaded.first_plan:.0f} s: the planner was compiled again"


def test_it_serves_the_website_from_inside_itself(downloaded: Downloaded) -> None:
    page = downloaded.http.get("/")
    assert page.status_code == 200 and "<!doctype html>" in page.text.lower()
    web = downloaded.run("from friday.server.main import WEB_DIST; print(WEB_DIST)")
    assert web.startswith(str(downloaded.app)), web


def test_its_python_and_friday_are_its_own_not_the_repos(downloaded: Downloaded) -> None:
    where = downloaded.run("import sys, friday; print(sys.prefix); print(friday.__file__)").splitlines()
    assert all(line.startswith(str(downloaded.app)) for line in where), where
    assert str(REPO) not in downloaded.run("import sys; print(sys.path)")


def test_running_it_writes_nothing_into_the_app(downloaded: Downloaded) -> None:
    downloaded.http.post("/api/c/sync_now", json={})
    assert snapshot(downloaded.app) == downloaded.before


def test_its_signature_still_holds_after_running(downloaded: Downloaded) -> None:
    checked = subprocess.run(["codesign", "--verify", "--strict", str(downloaded.app)], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr


def test_the_google_descriptions_it_keeps_are_the_ones_friday_reads(downloaded: Downloaded) -> None:
    kept = downloaded.run(
        "import googleapiclient, os; d = os.path.join(os.path.dirname(googleapiclient.__file__), "
        "'discovery_cache', 'documents'); print(' '.join(sorted(os.listdir(d))))"
    )
    assert kept.split() == ["calendar.v3.json", "gmail.v1.json", "oauth2.v2.json"]
    built = downloaded.run(  # as sync/google_auth.py builds them, from the kept descriptions, offline
        "from googleapiclient.discovery import build; "
        "print(all(build(n, v, developerKey='k', static_discovery=True) "
        "for n, v in (('calendar', 'v3'), ('gmail', 'v1'))))"
    )
    assert built == "True"
