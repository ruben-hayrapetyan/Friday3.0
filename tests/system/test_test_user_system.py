"""Test users end to end on a Mac (H224–H227): a real Friday server, started as a downloaded copy is, joins
as a test user with a code over its HTTP API; the site (a stand-in served over HTTP that answers as the admin hub's
site does: the test users' feed and disk image only for a code it knows) says whose code it is and offers their
version; Friday downloads it with the code, checks it and unpacks it from a real disk image. Leaving, it's offered
only everyone's version again."""

import hashlib
import json
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

from tests.system.test_beat_plan_system import REPO, free_port
from tests.system.test_updater_system import stand_in_app, version_of, wait_for

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="disk images are the Mac's")
CODE = "K7QF-29XM"


def disk_image(folder: Path, version: str) -> Path:
    stand_in_app(folder / f"stage-{version}", version)
    image = folder / f"Friday-{version}.dmg"
    subprocess.run(["hdiutil", "create", "-quiet", "-volname", f"Friday {version}", "-srcfolder",
                    str(folder / f"stage-{version}"), "-format", "ULFO", str(image)], check=True)  # fmt: skip
    return image


@pytest.fixture
def site(tmp_path: Path) -> Iterator[tuple[str, list]]:
    """Everyone has 0.2.1; test users (Ana's code) have 0.3.0, at /test/, for their code alone."""
    images = {v: disk_image(tmp_path, v) for v in ("0.2.1", "0.3.0")}
    asked: list[tuple[str, str | None]] = []
    port = free_port()
    address = f"http://127.0.0.1:{port}"

    def entry(version: str, path: str, test: bool = False) -> dict:
        image = images[version]
        notes = {"summary": f"Friday {version}.", "new": [], "changed": [], "fixed": [f"Fixed in {version}."]}
        return {"version": version, "released": "2026-11-18", "url": f"{address}{path}",
                "sha256": hashlib.sha256(image.read_bytes()).hexdigest(), "bytes": image.stat().st_size,
                "minimum_macos": "14.0", "notes": notes, **({"test": True} if test else {})}  # fmt: skip

    everyone = {"current": "0.2.1", "versions": [entry("0.2.1", "/downloads/Friday-0.2.1.dmg")]}

    class Site(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            pass

        def send(self, body: bytes, kind: str = "application/json", status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            code = self.headers.get("X-Friday-Test-User")
            asked.append((self.path, code))
            known = code is not None and code.replace("-", "").upper() == CODE.replace("-", "")
            if self.path == "/updates.json":
                feed = dict(everyone)
                if code is not None:
                    feed["test_user"] = "Ana" if known else None
                if known:
                    feed |= {"current": "0.3.0", "versions": [entry("0.3.0", "/test/Friday-0.3.0.dmg", True),
                                                              *everyone["versions"]]}  # fmt: skip
                return self.send(json.dumps(feed).encode())
            if self.path == "/downloads/Friday-0.2.1.dmg":
                return self.send(images["0.2.1"].read_bytes(), "application/x-apple-diskimage")
            if self.path == "/test/Friday-0.3.0.dmg" and known:
                return self.send(images["0.3.0"].read_bytes(), "application/x-apple-diskimage")
            return self.send(b"No such download.", "text/plain", 404)

    server = ThreadingHTTPServer(("127.0.0.1", port), Site)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield address, asked
    server.shutdown()


@pytest.fixture
def friday(tmp_path: Path, site: tuple[str, list]) -> Iterator[httpx.Client]:
    """Friday 0.2.0 as a downloaded copy runs it, from tmp/Applications."""
    app = stand_in_app(tmp_path / "Applications", "0.2.0")
    port = free_port()
    env = os.environ | {"FRIDAY_APP_VERSION": "0.2.0", "FRIDAY_APP_PATH": str(app),
                        "FRIDAY_UPDATE_FEED": f"{site[0]}/updates.json", "FRIDAY_UPDATE_DIR": str(tmp_path / "updates"),
                        "FRIDAY_CONFIG": str(tmp_path / "config" / "friday.toml"),
                        "PYTHONPATH": f"{REPO / 'src'}:{REPO}"}  # fmt: skip
    process = subprocess.Popen(
        [sys.executable, "-m", "friday.server.main", "--data-dir", str(tmp_path / "demo"), "demo", "--port", str(port),
         "--case", "maya"],
        env=env, cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )  # fmt: skip
    yield httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30)
    process.terminate()
    process.wait(15)


def test_a_test_user_gets_their_version_with_their_code_and_leaving_offers_everyones(
    friday: httpx.Client, site: tuple[str, list]
) -> None:
    _, asked = site
    first = wait_for(friday, lambda s: s.get("versions"))
    assert [v["version"] for v in first["versions"]] == ["0.2.1"] and first["test_user"] is None
    assert asked[0] == ("/updates.json", None)
    joined = friday.post("/api/c/update_test_join", json={"code": "k7qf 29xm"})
    assert joined.status_code == 200, joined.text
    known = wait_for(friday, lambda s: (s.get("test_user") or {}).get("known") is not None)
    assert known["test_user"] == {"code": CODE, "name": "Ana", "known": True}
    assert [(v["version"], v["test"]) for v in known["versions"]] == [("0.3.0", True), ("0.2.1", False)]
    friday.post("/api/c/update_start", json={})
    ready = wait_for(friday, lambda s: s["state"] in ("ready", "failed"))
    assert ready["state"] == "ready", ready["message"]
    assert version_of(Path(ready["staged"])) == "0.3.0"
    assert ("/test/Friday-0.3.0.dmg", CODE) in asked  # downloaded with the code
    friday.post("/api/c/update_test_leave", json={})
    left = wait_for(friday, lambda s: s["state"] != "checking" and s["test_user"] is None)
    assert [v["version"] for v in left["versions"]] == ["0.2.1"]
    assert asked[-1] == ("/updates.json", None)
