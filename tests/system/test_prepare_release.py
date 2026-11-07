"""scripts/prepare-release.sh (HOSTED.md H123, H134, H136), run as it is on a Mac: on a throwaway repo, with a small
stand-in app and stand-ins for ssh and scp that write into a pretend laptop. It refuses what can't be released,
commits the version number, makes a real disk image and leaves it waiting with its notes, candidate.json last."""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="hdiutil makes the disk image")
NOTES = {"summary": "Friday updates itself.", "new": ["An update popup."], "changed": [], "fixed": []}


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def setup(tmp_path: Path) -> dict[str, Path]:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy2(REPO / "scripts" / "prepare-release.sh", repo / "scripts")
    (repo / "VERSION").write_text("0.1.0\n")
    (repo / "Mac").mkdir()
    (repo / "Mac" / "google_client.json").write_text("{}")  # a stand-in: the real one is never read
    git(repo, "init", "-q")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "start")
    git(repo, "config", "user.name", "t")
    git(repo, "config", "user.email", "t@t")
    app = tmp_path / "Friday.app" / "Contents"
    app.mkdir(parents=True)
    (app / "Info.plist").write_text("<plist/>")
    laptop = tmp_path / "laptop"
    laptop.mkdir()
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "ssh").write_text(f'#!/bin/sh\ncd "{laptop}" && sh -c "$2"\n')
    (bin_ / "scp").write_text(f'#!/bin/sh\nshift\ncp "$1" "{laptop}/${{2#*:}}"\n')
    for tool in ("ssh", "scp"):
        (bin_ / tool).chmod(0o755)
    notes = tmp_path / "notes.json"
    notes.write_text(json.dumps(NOTES))
    return {"repo": repo, "app": tmp_path / "Friday.app", "laptop": laptop, "bin": bin_, "notes": notes}


def prepare(setup: dict[str, Path], version: str, notes: Path | None = None) -> subprocess.CompletedProcess:
    env = {"PATH": f"{setup['bin']}:/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(setup["laptop"]),
           "FRIDAY_PREPARE_APP": str(setup["app"]), "FRIDAY_RELEASE_HOST": "laptop"}  # fmt: skip
    script = str(setup["repo"] / "scripts" / "prepare-release.sh")
    return subprocess.run([script, version, str(notes or setup["notes"])], env=env, capture_output=True, text=True,
                          timeout=300)  # fmt: skip


def test_a_prepared_version_waits_on_the_laptop_with_its_notes_and_checksum(setup: dict[str, Path]) -> None:
    done = prepare(setup, "0.2.0")
    assert done.returncode == 0, done.stderr
    folder = setup["laptop"] / "friday-releases" / "candidates" / "0.2.0"
    image = (folder / "Friday-0.2.0.dmg").read_bytes()
    waiting = json.loads((folder / "candidate.json").read_text())
    assert waiting["sha256"] == hashlib.sha256(image).hexdigest() and waiting["bytes"] == len(image)
    assert waiting["notes"] == NOTES and waiting["approved"] is False and waiting["version"] == "0.2.0"
    repo = setup["repo"]
    assert (repo / "VERSION").read_text().strip() == "0.2.0" and waiting["commit"] == git(repo, "rev-parse", "HEAD")
    assert git(repo, "log", "-1", "--format=%s") == "Friday 0.2.0, prepared for release"
    assert image[-512:-508] == b"koly"  # a real disk image (UDIF), not a copy of the folder


@pytest.mark.parametrize(("version", "notes", "said"), [
    ("2", NOTES, "a number like 0.2.0"),
    ("0.2.0", {"summary": "", "new": ["x"]}, "summary sentence"),
    ("0.2.0", {"summary": "s", "new": [], "changed": [], "fixed": []}, "at least one line"),
])  # fmt: skip
def test_it_refuses_what_cant_be_released(setup: dict[str, Path], version: str, notes: dict, said: str) -> None:
    setup["notes"].write_text(json.dumps(notes))
    done = prepare(setup, version)
    assert done.returncode != 0 and said in done.stderr
    assert not (setup["laptop"] / "friday-releases").exists()


def test_it_refuses_uncommitted_changes_and_a_missing_google_client(setup: dict[str, Path]) -> None:
    (setup["repo"] / "VERSION").write_text("9.9.9\n")
    assert "commit or set aside" in prepare(setup, "0.2.0").stderr
    git(setup["repo"], "checkout", "--", "VERSION")
    git(setup["repo"], "rm", "-q", "Mac/google_client.json")
    git(setup["repo"], "commit", "-qm", "no client")
    assert "Friday's Google client" in prepare(setup, "0.2.0").stderr
