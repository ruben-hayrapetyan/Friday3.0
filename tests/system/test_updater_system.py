"""The updater end to end on a Mac (HOSTED.md H118–H124, H144–H146): a real Friday server, started the way a
downloaded copy is (its version, its place and the feed's address), finds a newer version in an update feed served
over HTTP, shows it with its notes, downloads it, checks it, unpacks it from a real disk image, and the Mac app's own
swap script (Mac/Sources/Updater.swift) puts it in place of the old app once that has quit. The new version is a
small stand-in app, so the test needn't build Friday."""

import hashlib
import json
import os
import plistlib
import re
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from tests.system.test_beat_plan_system import REPO, free_port

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="disk images and the swap are the Mac's")


def stand_in_app(folder: Path, version: str) -> Path:
    app = folder / "Friday.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "MacOS" / "Friday").write_text("#!/bin/sh\n")
    (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleShortVersionString": version}))
    return app


def version_of(app: Path) -> str:
    return plistlib.loads((app / "Contents" / "Info.plist").read_bytes())["CFBundleShortVersionString"]


@pytest.fixture
def site(tmp_path: Path) -> Iterator[str]:
    """The site with Friday 0.2.1's disk image and the feed offering it, as the admin hub writes them."""
    root = tmp_path / "site"
    (root / "downloads").mkdir(parents=True)
    stand_in_app(tmp_path / "stage", "0.2.1")
    image = root / "downloads" / "Friday-0.2.1.dmg"
    subprocess.run(["hdiutil", "create", "-quiet", "-volname", "Friday 0.2.1", "-srcfolder", str(tmp_path / "stage"),
                    "-format", "ULFO", str(image)], check=True)  # fmt: skip
    port = free_port()
    address = f"http://127.0.0.1:{port}"
    notes = {"summary": "Friday updates itself.", "new": ["The update popup."], "changed": [], "fixed": ["A fix."]}
    feed = {"current": "0.2.1", "versions": [
        {"version": "0.2.1", "released": "2026-11-07", "url": f"{address}/downloads/Friday-0.2.1.dmg",
         "sha256": hashlib.sha256(image.read_bytes()).hexdigest(), "bytes": image.stat().st_size,
         "minimum_macos": "14.0", "notes": notes}]}  # fmt: skip
    (root / "updates.json").write_text(json.dumps(feed))
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"], cwd=root,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # fmt: skip
    time.sleep(0.5)
    yield address
    server.terminate()
    server.wait(10)


@pytest.fixture
def friday(tmp_path: Path, site: str) -> Iterator[tuple[httpx.Client, Path]]:
    """Friday 0.2.0 as a downloaded copy runs it, from tmp/Applications."""
    app = stand_in_app(tmp_path / "Applications", "0.2.0")
    port = free_port()
    env = os.environ | {"FRIDAY_APP_VERSION": "0.2.0", "FRIDAY_APP_PATH": str(app),
                        "FRIDAY_UPDATE_FEED": f"{site}/updates.json", "FRIDAY_UPDATE_DIR": str(tmp_path / "updates"),
                        "FRIDAY_CONFIG": str(tmp_path / "config" / "friday.toml"),
                        "PYTHONPATH": f"{REPO / 'src'}:{REPO}"}  # fmt: skip
    process = subprocess.Popen(
        [sys.executable, "-m", "friday.server.main", "--data-dir", str(tmp_path / "demo"), "demo", "--port", str(port),
         "--case", "maya"],
        env=env, cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )  # fmt: skip
    client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30)
    yield client, app
    process.terminate()
    process.wait(15)


def wait_for(client: httpx.Client, done, seconds: float = 180) -> dict:  # noqa: ANN001
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            status = client.get("/api/q/update_status").json()
            if done(status):
                return status
        except (httpx.HTTPError, ValueError):
            pass
        time.sleep(0.5)
    raise AssertionError("the updater didn't get there in time")


def swap_script() -> str:
    source = (REPO / "Mac" / "Sources" / "Updater.swift").read_text()
    return re.search(r'static let swapScript = """\n(.*?)\n\s*"""', source, re.S)[1]


def test_a_downloaded_friday_finds_downloads_unpacks_and_swaps_in_the_new_version(
    friday: tuple[httpx.Client, Path],
) -> None:
    client, app = friday
    found = wait_for(client, lambda s: s.get("versions"))
    assert found["checks"] and found["have"] == "0.2.0" and found["popup"]
    assert found["versions"][0]["version"] == "0.2.1" and found["versions"][0]["fixed"] == ["A fix."]
    client.post("/api/c/update_start", json={})
    ready = wait_for(client, lambda s: s["state"] in ("ready", "failed"))
    assert ready["state"] == "ready", ready["message"]
    staged = Path(ready["staged"])
    assert version_of(staged) == "0.2.1" and ready["restart"] == "now"
    gone = subprocess.Popen(["/usr/bin/true"])  # a Friday that has quit
    gone.wait()
    subprocess.run(["/bin/sh", "-c", swap_script(), "friday-swap", str(gone.pid), str(app), str(staged), "0"],
                   check=True, timeout=60)  # fmt: skip
    assert version_of(app) == "0.2.1" and not staged.exists()
    assert sorted(p.name for p in app.parent.iterdir()) == ["Friday.app"]


@pytest.mark.skipif(not os.environ.get("FRIDAY_SITE"), reason="FRIDAY_SITE=URL: the live site, through Cloudflare")
def test_the_live_site_lets_friday_read_its_feed() -> None:
    """Cloudflare refuses Python's own name (error 1010); Friday's name gets the feed, whose links are the counted ones
    (not followed here: each would count as a download)."""
    from friday.sync import updates as net

    site = os.environ["FRIDAY_SITE"].rstrip("/")
    feed = net.fetch_feed(f"{site}/updates.json", version="0.2.0")
    assert feed["versions"] and all(v["url"].startswith(f"{site}/get/") for v in feed["versions"])
