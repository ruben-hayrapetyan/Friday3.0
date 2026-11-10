"""scripts/prepare-release.sh (HOSTED.md H123, H134, H136), run as it is on a Mac: on a throwaway repo, with a small
stand-in app and stand-ins for ssh and scp that write into a pretend laptop, and for Apple's signing and notarizing
tools (C88: codesign, security, notarytool, stapler and spctl write down how they were called). It refuses what can't
be released, commits the version number, signs the app before the disk image is made, has the image notarized and
stapled, and leaves it waiting with its notes, candidate.json last."""

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
    shutil.copy2(REPO / "scripts" / "set_version.py", repo / "scripts")
    shutil.copytree(REPO / "Mac" / "entitlements", repo / "Mac" / "entitlements")
    shutil.copy2(REPO / "Mac" / "sign.sh", repo / "Mac")
    (repo / "VERSION").write_text("0.1.0\n")
    # every file that names the version (H174), as small as set_version needs them
    for name, package in (("", "friday"),):  # the hub numbers its own, in Friday-admin (C80)
        (repo / name).mkdir(exist_ok=True)
        (repo / f"{name}pyproject.toml").write_text(f'[project]\nname = "{package}"\nversion = "0.1.0"\n')
        (repo / f"{name}uv.lock").write_text(
            f'[[package]]\nname = "{package}"\nversion = "0.1.0"\nsource = {{ editable = "." }}\n'
        )
    (repo / "web").mkdir()
    (repo / "web" / "package.json").write_text('{\n  "name": "friday-web",\n  "version": "0.1.0"\n}\n')
    (repo / "Mac" / "google_client.json").write_text("{}")  # a stand-in: the real one is never read
    git(repo, "init", "-q")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "start")
    git(repo, "config", "user.name", "t")
    git(repo, "config", "user.email", "t@t")
    app = tmp_path / "Friday.app" / "Contents"
    app.mkdir(parents=True)
    (app / "Info.plist").write_text("<plist/>")
    (app / "MacOS").mkdir()
    laptop = tmp_path / "laptop"
    laptop.mkdir()
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "ssh").write_text(f'#!/bin/sh\ncd "{laptop}" && sh -c "$2"\n')
    (bin_ / "scp").write_text(f'#!/bin/sh\nshift\ncp "$1" "{laptop}/${{2#*:}}"\n')
    calls = tmp_path / "apple.txt"  # each call to Apple's tools, one line each, in order
    log = f'echo "$(basename "$0") $*" >> "{calls}"'
    (bin_ / "security").write_text(f'#!/bin/sh\n{log}\n[ -f "{tmp_path}/no-certificate" ] || '
                                   'echo \'  1) ABC123 "Developer ID Application: Ruben (TEAM1)"\'\n')  # fmt: skip
    (bin_ / "codesign").write_text(f"#!/bin/sh\n{log}\n")
    (bin_ / "spctl").write_text(f"#!/bin/sh\n{log}\n")
    # notarytool: a stored profile unless no-profile is there; Apple's verdict is the file verdict (Accepted)
    (bin_ / "xcrun").write_text(f"""#!/bin/sh
{log}
case "$1 $2" in
  "notarytool history") [ ! -f "{tmp_path}/no-profile" ] ;;
  "notarytool submit") v="$(cat "{tmp_path}/verdict" 2>/dev/null || echo Accepted)"
    printf '{{"id": "sub-1", "status": "%s"}}\\n' "$v" ;;
  "notarytool log") echo "The binary is not signed with a valid Developer ID certificate." ;;
esac
""")
    for tool in ("ssh", "scp", "security", "codesign", "spctl", "xcrun"):
        (bin_ / tool).chmod(0o755)
    notes = tmp_path / "notes.json"
    notes.write_text(json.dumps(NOTES))
    return {"repo": repo, "app": tmp_path / "Friday.app", "laptop": laptop, "bin": bin_, "notes": notes,
            "calls": calls, "tmp": tmp_path}  # fmt: skip


def apple_calls(setup: dict[str, Path]) -> list[str]:
    return setup["calls"].read_text().splitlines() if setup["calls"].exists() else []


def prepare(
    setup: dict[str, Path], version: str, notes: Path | None = None, extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    env = {"PATH": f"{setup['bin']}:/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(setup["laptop"]),
           "FRIDAY_PREPARE_APP": str(setup["app"]), "FRIDAY_RELEASE_HOST": "laptop"} | (extra or {})  # fmt: skip
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
    numbered = ["VERSION", "pyproject.toml", "web/package.json", "uv.lock"]  # the hub numbers its own (C80)
    assert sorted(git(repo, "show", "--name-only", "--format=", "HEAD").splitlines()) == sorted(numbered)
    assert all("0.2.0" in (repo / name).read_text() for name in numbered) and not git(repo, "status", "--porcelain")
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


def test_it_refuses_uncommitted_changes_and_needs_no_google_client(setup: dict[str, Path]) -> None:
    (setup["repo"] / "VERSION").write_text("9.9.9\n")
    assert "commit or set aside" in prepare(setup, "0.2.0").stderr
    git(setup["repo"], "checkout", "--", "VERSION")
    git(setup["repo"], "rm", "-q", "Mac/google_client.json")
    git(setup["repo"], "commit", "-qm", "no client")
    assert "Google client" not in prepare(setup, "0.2.0").stderr  # downloads leave it out (C77)


def test_where_the_hub_is_comes_from_a_private_file_and_is_said_when_missing(setup: dict[str, Path]) -> None:
    """The laptop's name and the hub's address aren't in the repo (C80): ~/.config/friday/release.env says them."""
    env = {"PATH": f"{setup['bin']}:/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(setup["laptop"]),
           "FRIDAY_PREPARE_APP": str(setup["app"])}  # fmt: skip
    script = str(setup["repo"] / "scripts" / "prepare-release.sh")
    done = subprocess.run([script, "0.2.0", str(setup["notes"])], env=env, capture_output=True, text=True, timeout=60)
    assert done.returncode != 0 and "say where the hub is" in done.stderr
    assert "tailnet" not in (setup["repo"] / "scripts" / "prepare-release.sh").read_text()


# Signed and notarized (C88, your choice: every prepare-release build)


def test_the_app_is_signed_before_the_image_and_the_image_notarized_and_stapled_before_its_checksum(
    setup: dict[str, Path],
) -> None:
    done = prepare(setup, "0.2.0")
    assert done.returncode == 0, done.stderr
    calls = apple_calls(setup)
    me = "Developer ID Application: Ruben (TEAM1)"
    app_signed = next(i for i, c in enumerate(calls) if c.startswith("codesign") and c.endswith("/stage/Friday.app"))
    assert f"--sign {me} --options runtime --timestamp --entitlements" in calls[app_signed]
    assert "Mac/entitlements/app.plist" in calls[app_signed]
    image = [i for i, c in enumerate(calls) if "Friday-0.2.0.dmg" in c]
    assert [calls[i].split()[:2] for i in image] == [
        ["codesign", "--sign"], ["xcrun", "notarytool"], ["xcrun", "stapler"], ["spctl", "--assess"]
    ]  # fmt: skip
    assert app_signed < image[0] and "--keychain-profile friday-notary --wait" in calls[image[1]]
    folder = setup["laptop"] / "friday-releases" / "candidates" / "0.2.0"
    assert json.loads((folder / "candidate.json").read_text())["sha256"]


@pytest.mark.parametrize(("missing", "said"), [
    ("no-certificate", "no Developer ID Application certificate"),
    ("no-profile", "no keychain profile 'friday-notary'"),
])  # fmt: skip
def test_without_a_certificate_or_a_notary_profile_nothing_is_built_numbered_or_sent(
    setup: dict[str, Path], missing: str, said: str
) -> None:
    (setup["tmp"] / missing).touch()
    done = prepare(setup, "0.2.0")
    assert done.returncode != 0 and said in done.stderr and "C88" in done.stderr
    assert git(setup["repo"], "log", "-1", "--format=%s") == "start"  # the version wasn't committed
    assert not (setup["laptop"] / "friday-releases").exists()
    assert not any(c.startswith("codesign") for c in apple_calls(setup))


def test_a_version_apple_wont_notarize_isnt_sent_and_apple_s_reasons_are_shown(setup: dict[str, Path]) -> None:
    (setup["tmp"] / "verdict").write_text("Invalid")
    done = prepare(setup, "0.2.0")
    assert done.returncode != 0 and "didn't notarize it (Invalid, submission sub-1)" in done.stderr
    assert "not signed with a valid Developer ID" in done.stderr  # notarytool's log of why
    assert not any(c.startswith("xcrun stapler") for c in apple_calls(setup))
    assert not (setup["laptop"] / "friday-releases").exists()


def test_a_named_certificate_and_profile_are_used_as_given(setup: dict[str, Path]) -> None:
    env = {"FRIDAY_SIGN_IDENTITY": "Developer ID Application: Other (TEAM2)", "FRIDAY_NOTARY_PROFILE": "mine"}
    done = prepare(setup, "0.2.0", extra=env)
    assert done.returncode == 0, done.stderr
    calls = apple_calls(setup)
    assert not any(c.startswith("security") for c in calls)  # named, so not looked up
    assert any("--sign Developer ID Application: Other (TEAM2)" in c for c in calls)
    assert any(c.startswith("xcrun notarytool submit") and "--keychain-profile mine" in c for c in calls)
