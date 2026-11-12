"""One version number everywhere (HOSTED.md H174; 8 Nov: Friday was 0.3.0 while the repo said 0.1.0). Black box: the
repo's files agree. Glass box: set_version writes each of them, and leaves other packages in a lock file alone."""

import json
import re
import shutil
from pathlib import Path

import pytest

from scripts.set_version import locked_version, project_version, set_version

REPO = Path(__file__).resolve().parents[1]
FILES = ["VERSION", "pyproject.toml", "web/package.json", "uv.lock"]  # the hub has its own, in Friday-admin (C80)


def versions(root: Path) -> dict[str, str]:
    def project(name: str) -> str:
        return re.search(r'(?m)^\[project\][^\[]*?^version = "([^"]*)"', (root / name).read_text())[1]  # type: ignore[index]

    def locked(name: str, package: str) -> str:
        found = re.search(
            rf'(?m)^name = "{package}"\nversion = "([^"]*)"\nsource = {{ editable', (root / name).read_text()
        )
        return found[1]  # type: ignore[index]

    return {
        "VERSION": (root / "VERSION").read_text().strip(),
        "pyproject.toml": project("pyproject.toml"),
        "web/package.json": json.loads((root / "web/package.json").read_text())["version"],
        "uv.lock": locked("uv.lock", "friday"),
    }


def test_every_file_names_the_same_version() -> None:
    found = versions(REPO)
    assert len(set(found.values())) == 1, found


def test_setting_a_version_writes_every_file_and_nothing_else(tmp_path: Path) -> None:
    for name in FILES:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / name, tmp_path / name)
    before = (tmp_path / "uv.lock").read_text()
    assert set_version(tmp_path, "9.8.7") == FILES
    assert set(versions(tmp_path).values()) == {"9.8.7"}
    after = (tmp_path / "uv.lock").read_text()
    assert len(before.splitlines()) == len(after.splitlines())  # one line changed, the rest as it was
    assert sum(a != b for a, b in zip(before.splitlines(), after.splitlines(), strict=True)) == 1


def test_only_the_projects_own_entries_change() -> None:
    lock = (
        'name = "friday"\nversion = "0.1.0"\nsource = { registry = "x" }\n\n'
        'name = "friday"\nversion = "0.1.0"\nsource = { editable = "." }\n'
    )
    assert locked_version(lock, "friday", "1.2.3").count('"1.2.3"') == 1
    assert 'version = "1.2.3"\nsource = { editable' in locked_version(lock, "friday", "1.2.3")
    toml = '[tool.x]\nversion = "7"\n\n[project]\nname = "f"\nversion = "0.1.0"\n'
    assert project_version(toml, "2.0.0") == '[tool.x]\nversion = "7"\n\n[project]\nname = "f"\nversion = "2.0.0"\n'


def test_a_version_must_be_a_number() -> None:
    with pytest.raises(ValueError, match="like 0.4.0"):
        set_version(REPO, "next")


def test_a_file_whose_version_isnt_found_stops_it_before_anything_is_written(tmp_path: Path) -> None:
    # audit, 12 Nov: a [project] with a list before its version was written back unchanged, and said to be done
    for name in FILES:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / name, tmp_path / name)
    toml = (tmp_path / "pyproject.toml").read_text()
    (tmp_path / "pyproject.toml").write_text(toml.replace("[project]\n", '[project]\nkeywords = ["plan"]\n', 1))
    before = {name: (tmp_path / name).read_text() for name in FILES}
    with pytest.raises(ValueError, match="pyproject.toml"):
        set_version(tmp_path, "9.8.7")
    assert {name: (tmp_path / name).read_text() for name in FILES} == before


def test_a_missing_file_is_said_not_made(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="VERSION"):
        set_version(tmp_path, "9.8.7")
    assert not (tmp_path / "VERSION").exists()
