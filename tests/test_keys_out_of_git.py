"""Friday's own app ids and secrets stay out of git (11 Nov: "they should be kept out of the github repos"): the keys
file is ignored, none of its values is in any tracked file, and Friday reads them from the environment first, then the
file (integrations/keys.py)."""

import json
import subprocess
from pathlib import Path

import pytest

from friday.integrations import keys

REPO = Path(__file__).resolve().parents[1]
FILE = REPO / "Mac" / "app_keys.json"


def test_the_keys_file_is_ignored_by_git() -> None:
    said = subprocess.run(["git", "check-ignore", "-q", str(FILE)], cwd=REPO, capture_output=True)
    assert said.returncode == 0, "Mac/app_keys.json isn't in .gitignore"


@pytest.mark.skipif(not FILE.exists(), reason="no keys file in this checkout (CI)")
def test_no_key_is_in_a_tracked_file() -> None:
    for name, value in json.loads(FILE.read_text()).items():
        found = subprocess.run(["git", "grep", "-l", "-F", str(value)], cwd=REPO, capture_output=True, text=True)
        assert found.stdout == "", f"{name} is in {found.stdout.split()}"


def test_a_key_comes_from_the_environment_then_the_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    kept = tmp_path / "app_keys.json"
    kept.write_text(json.dumps({"slack_client_id": "from-file", "trello_client_id": "file-trello"}))
    monkeypatch.setattr(keys, "PLACES", [tmp_path / "missing.json", kept])
    keys.kept.cache_clear()
    monkeypatch.setenv("FRIDAY_SLACK_CLIENT_ID", "from-env")
    try:
        assert keys.get("slack_client_id") == "from-env"
        assert keys.get("trello_client_id") == "file-trello"
        assert keys.get("ticktick_client_id") == ""
    finally:
        keys.kept.cache_clear()
