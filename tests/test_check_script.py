"""What scripts/check.sh and the screen tests rely on, held so it doesn't slip back (13 Nov: "for any bugs that you
fixed, there should be tests that should have caught those bugs").

- check.sh shows pytest's pass and fail counts: pytest is already quiet (pyproject's addopts -q), and check.sh's own -q
  hid them, so a passing run couldn't be read off its summary.
- The screen tests' Friday has a made-up key for every app key Friday reads (integrations/keys.py): without one, a
  service's box read "not ready" on any checkout without the gitignored Mac/app_keys.json (a contributor's fork,
  GitHub's checks), and its tests failed there only."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_check_sh_runs_pytest_without_quieting_it_twice() -> None:
    addopts = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["pytest"]["ini_options"]["addopts"]
    runs = [line.split("#")[0] for line in (ROOT / "scripts" / "check.sh").read_text().splitlines()]
    pytest_runs = [line for line in runs if re.match(r"\s*uv run pytest\b", line)]
    assert pytest_runs, "check.sh runs the Python tests"
    if "-q" in addopts.split():
        for line in pytest_runs:
            assert "-q" not in line.split(), f"{line.strip()!r}: pytest is already -q; another hides its counts"


def test_the_screen_tests_stand_in_every_app_key() -> None:
    read = set()
    for source in (ROOT / "src" / "friday" / "integrations").glob("*.py"):
        read |= set(re.findall(r'keys\.get\("([a-z_]+)"\)', source.read_text()))
    assert read, "Friday reads its app keys by name"
    server = (ROOT / "web" / "src" / "test" / "server.ts").read_text()
    missing = sorted(name for name in read if f"{name.upper()}:" not in server)
    assert not missing, f"web/src/test/server.ts has no made-up FRIDAY_ key for {missing}"
