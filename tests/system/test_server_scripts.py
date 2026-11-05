"""The server's scripts (HOSTED.md S1), run as they are on the server against a throwaway home: `profile.sh` says
which test profile a Friday serves, switches it (H76: one at a time) and restarts that Friday's service, and refuses
a profile that doesn't exist. `systemctl` is a stand-in that writes down how it was called."""

import os
import stat
import subprocess
from pathlib import Path

import pytest

from tests.system.test_beat_plan_system import REPO

SCRIPTS = REPO / "scripts" / "server"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    staging = tmp_path / "friday-hosted" / "staging"
    for key in ("maya", "kira"):  # built already, so switching needn't build
        (staging / "profiles" / key).mkdir(parents=True)
        (staging / "profiles" / key / "friday.db").write_text("")
    (staging / "friday.env").write_text("APP=/srv/app\nPROFILE=maya\nPORT=8766\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "systemctl"
    fake.write_text(f'#!/bin/sh\necho "$@" >> {tmp_path}/systemctl.calls\n')
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    return tmp_path


def profile(home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ | {"HOME": str(home), "PATH": f"{home / 'bin'}:{os.environ['PATH']}"}
    return subprocess.run([str(SCRIPTS / "profile.sh"), *args], env=env, capture_output=True, text=True, timeout=120)


def test_with_no_profile_named_it_says_which_one_is_served(home: Path) -> None:
    done = profile(home, "staging")
    assert done.returncode == 0 and done.stdout.strip() == "maya"


def test_switching_rewrites_only_the_profile_and_restarts_that_copy(home: Path) -> None:
    done = profile(home, "staging", "kira")
    assert done.returncode == 0, done.stderr
    assert (home / "friday-hosted/staging/friday.env").read_text() == "APP=/srv/app\nPROFILE=kira\nPORT=8766\n"
    assert (home / "systemctl.calls").read_text().split("\n")[0] == "--user restart friday@staging"
    assert "Software engineer" in done.stdout  # it names who is served now


def test_a_profile_that_doesnt_exist_is_refused_and_nothing_changes(home: Path) -> None:
    done = profile(home, "staging", "nobody")
    assert done.returncode == 1 and "no profile called nobody" in done.stdout
    assert "PROFILE=maya" in (home / "friday-hosted/staging/friday.env").read_text()
    assert not (home / "systemctl.calls").exists()


def test_a_copy_that_isnt_set_up_is_named(home: Path) -> None:
    done = profile(home, "real", "kira")
    assert done.returncode == 1 and "no real Friday here" in done.stdout


def test_the_service_runs_each_copys_profile_on_its_port_from_its_checkout() -> None:
    unit = (SCRIPTS / "friday@.service").read_text()
    assert "EnvironmentFile=%h/friday-hosted/%i/friday.env" in unit
    for part in (
        '"$APP/.venv/bin/python"',
        'demo --case "$PROFILE"',
        '--port "$PORT"',
        'FRIDAY_WEB_DIST="$APP/web/dist"',
    ):
        assert part in unit
