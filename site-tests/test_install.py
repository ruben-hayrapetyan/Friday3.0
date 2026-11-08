"""Installing from Terminal (HOSTED.md H131). Glass box: release/make-install.sh fills in the version, the disk image's
checksum and the site's address, and the script runs nothing until all of it has arrived. Black box over HTTP: the
site serves install.sh for the disk image it offers, and the pages show the one line that fetches it, with a Copy
button that works. System (on a Mac, FRIDAY_SITE set): the served line really installs Friday, checked, signed and
without the quarantine mark that makes macOS ask."""

import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from test_site import ROOT, SITE, fetch, parsed, site  # noqa: F401  (site is the served-site fixture)

TEMPLATE = ROOT / "release" / "install-template.sh"
ADDRESS = "https://friday-scheduler.com"
LINE = f"curl -fsSL {ADDRESS}/install.sh | sh"


def made(tmp_path: Path, *args: str) -> str:
    """make-install.sh run on a copy of the release folder, with a stand-in disk image."""
    (tmp_path / "release").mkdir()
    for name in ("install-template.sh", "make-install.sh"):
        shutil.copy2(ROOT / "release" / name, tmp_path / "release" / name)
    (tmp_path / "site" / "downloads").mkdir(parents=True)
    (tmp_path / "site" / "downloads" / "Friday-9.9.9.dmg").write_bytes(b"a disk image")
    subprocess.run([str(tmp_path / "release" / "make-install.sh"), "9.9.9", *args], check=True, capture_output=True)
    return (tmp_path / "site" / "install.sh").read_text()


def test_make_install_fills_in_the_version_checksum_and_address(tmp_path: Path) -> None:
    script = made(tmp_path)
    assert "@" not in re.sub(r"\S+@\S+", "", script.replace('"$@"', ""))  # every placeholder filled
    assert 'VERSION="9.9.9"' in script and f'SHA256="{hashlib.sha256(b"a disk image").hexdigest()}"' in script
    assert f'URL="{ADDRESS}/get/Friday-$VERSION.dmg"' in script
    assert subprocess.run(["sh", "-n"], input=script, text=True).returncode == 0


def test_make_install_takes_the_sites_address_once_there_is_a_domain(tmp_path: Path) -> None:
    assert 'URL="https://friday.example/get/' in made(tmp_path, "https://friday.example/")


def test_the_script_runs_nothing_until_it_has_all_arrived() -> None:
    lines = [ln for ln in TEMPLATE.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    assert lines[-1] == "install_friday"
    top_level = [ln for ln in lines if not ln.startswith((" ", "}")) and "()" not in ln]
    assert all(re.match(r"(set -eu|[A-Z0-9_]+=\".*\"|install_friday)$", ln) for ln in top_level), top_level


def test_the_script_checks_the_download_before_installing_and_keeps_the_old_copy_until_then() -> None:
    script = TEMPLATE.read_text()
    assert script.index("shasum -a 256") < script.index("hdiutil attach") < script.index('ditto "$mount')
    assert script.index('"$app.new"') < script.index('rm -r "$app"')  # a failed copy leaves the Friday you have
    assert "pgrep" in script and "Quit it" in script  # never replaces a Friday that's open


def test_the_site_serves_the_script_for_the_disk_image_it_offers(site: str) -> None:  # noqa: F811
    status, body = fetch(site, "/install.sh")
    script = body.decode()
    version = re.search(r'VERSION="([^"]+)"', script)
    assert status == 200 and version
    assert f"/get/Friday-{version[1]}.dmg" in parsed(site, "index.html").links  # the same as the button
    dmg = SITE / "downloads" / f"Friday-{version[1]}.dmg"
    if not dmg.exists():
        pytest.skip("the disk image is kept on the laptop, not in git")
    digest = hashlib.sha256()
    with dmg.open("rb") as image:
        for chunk in iter(lambda: image.read(1 << 20), b""):
            digest.update(chunk)
    assert f'SHA256="{digest.hexdigest()}"' in script


@pytest.mark.parametrize("page", ["index.html", "help.html"])
def test_the_pages_show_the_line_with_a_copy_button_that_works(site: str, page: str) -> None:  # noqa: F811
    text = fetch(site, "/" + page)[1].decode()
    assert LINE in text and "data-copy" in text
    assert "/site.js" in parsed(site, page).scripts and "data-copy" in fetch(site, "/site.js")[1].decode()
    assert f'URL="{ADDRESS}/' in fetch(site, "/install.sh")[1].decode()  # the line and the script name one site


def test_off_a_mac_the_terminal_line_is_hidden_with_the_download(site: str) -> None:  # noqa: F811
    assert "[data-mac-only]" in fetch(site, "/download.js")[1].decode()
    assert fetch(site, "/")[1].decode().count("data-mac-only") == 2


@pytest.mark.skipif(sys.platform != "darwin" or not os.environ.get("FRIDAY_SITE"), reason="a Mac, FRIDAY_SITE=URL")
def test_the_served_line_installs_friday_without_the_mark_that_makes_macos_ask(tmp_path: Path) -> None:
    # the real line, from the real site, into a folder of its own; `open` stood in for, so nothing starts
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "open").write_text(f'#!/bin/sh\necho "$@" > "{tmp_path}/opened"\n')
    (tmp_path / "bin" / "open").chmod(0o755)
    env = os.environ | {"PATH": f"{tmp_path / 'bin'}:/usr/bin:/bin:/usr/sbin:/sbin",
                        "FRIDAY_INSTALL_DIR": str(tmp_path / "Applications")}  # fmt: skip
    line = f"curl -fsSL {os.environ['FRIDAY_SITE'].rstrip('/')}/install.sh | sh"
    subprocess.run(["sh", "-c", line], env=env, check=True, timeout=900)
    app = tmp_path / "Applications" / "Friday.app"
    assert (tmp_path / "opened").read_text().strip() == str(app)
    assert (app / "Contents/Resources/friday/python/bin/python3.12").exists()
    marks = subprocess.run(["xattr", str(app)], capture_output=True, text=True).stdout
    assert "com.apple.quarantine" not in marks
    assert subprocess.run(["codesign", "--verify", "--strict", str(app)]).returncode == 0
    assert not (tmp_path / "Applications" / "Friday.app.new").exists()
