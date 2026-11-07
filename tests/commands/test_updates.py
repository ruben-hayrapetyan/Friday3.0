"""Friday's own updater as the page uses it (commands/updates.py; HOSTED.md H118–H124, H144–H147), black box through
its commands and the `updates` job. The update feed and the disk image are stand-ins; unpacking is faked here (it's
tested on a real disk image in tests/sync/test_updates.py). Each test is one Friday: a new launch is a new run."""

import hashlib
import io
import json
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from friday.commands import updates
from friday.core.items import FieldError
from friday.server.jobs import look_for_updates
from friday.sync import updates as net
from tests.commands.helpers import App, new_app

FEED = "https://site.example/updates.json"
IMAGE = b"Friday 0.3.0's disk image"


def version(number: str, summary: str, image: bytes = IMAGE) -> dict:
    return {"version": number, "released": "2026-11-07", "url": f"https://site.example/downloads/Friday-{number}.dmg",
            "sha256": hashlib.sha256(image).hexdigest(), "bytes": len(image), "minimum_macos": "14.0",
            "notes": {"summary": summary, "new": [f"New in {number}"], "changed": [],
                      "fixed": [f"Fixed in {number}"]}}  # fmt: skip


class Site:
    """The update feed and disk images as the site serves them."""

    def __init__(self) -> None:
        self.versions = [version("0.3.0", "Three."), version("0.2.0", "Two."), version("0.1.0", "One.")]
        self.image = IMAGE
        self.down = False

    def __call__(self, url: str, timeout: int) -> io.BytesIO:
        if self.down:
            raise OSError("no route to host")
        if url == FEED:
            return io.BytesIO(json.dumps({"current": self.versions[0]["version"], "versions": self.versions}).encode())
        return io.BytesIO(self.image)


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Site]:
    serving = Site()
    monkeypatch.setattr("urllib.request.urlopen", serving)
    monkeypatch.setenv("FRIDAY_UPDATE_FEED", FEED)
    monkeypatch.setenv("FRIDAY_APP_VERSION", "0.1.0")
    monkeypatch.setenv("FRIDAY_UPDATE_DIR", str(tmp_path / "updates"))

    def unpack(image: Path, folder: Path) -> Path:
        (folder / "Friday.app" / "Contents" / "MacOS").mkdir(parents=True)
        return folder / "Friday.app"

    monkeypatch.setattr(net, "unpack", unpack)
    updates.RUNS.clear()
    yield serving
    updates.RUNS.clear()


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def launch(app: App) -> dict:
    """Friday opens: a new run, and the job loop's first look."""
    updates.RUNS.clear()
    look_for_updates(app.conn, app.now_utc, {}, Hub(), None, Path("."), 1)
    return app.do("update_status")


class Hub:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def publish(self, event: str) -> None:
        self.sent.append(event)


def finish(app: App) -> dict:
    run = updates.run_for(app.conn)
    assert run.thread is not None
    run.thread.join(10)
    return app.do("update_status")


def test_a_build_without_the_feed_never_looks_and_says_so(
    app: App, site: Site, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("FRIDAY_UPDATE_FEED")
    status = launch(app)
    assert status["checks"] is False and status["versions"] == [] and status["popup"] is False
    with pytest.raises(FieldError, match="doesn't look for updates"):
        app.do("update_check")
    assert app.do("update_status")["last_checked"] is None


def test_at_launch_it_finds_every_newer_version_with_its_notes_and_asks(app: App, site: Site) -> None:
    status = launch(app)
    assert status["checks"] and status["have"] == "0.1.0" and status["last_checked"] == "2026-10-19T09:00"
    assert [v["version"] for v in status["versions"]] == ["0.3.0", "0.2.0"]
    assert status["versions"][0]["summary"] == "Three." and status["versions"][1]["fixed"] == ["Fixed in 0.2.0"]
    assert status["popup"] is True and status["whats_new"] == []


def test_later_puts_it_off_until_the_next_launch(app: App, site: Site) -> None:
    launch(app)
    assert app.do("update_later")["popup"] is False
    assert app.do("update_status")["popup"] is False
    assert launch(app)["popup"] is True


def test_up_to_date_shows_no_popup(app: App, site: Site, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRIDAY_APP_VERSION", "0.3.0")
    status = launch(app)
    assert status["versions"] == [] and status["popup"] is False and status["last_checked"] is not None


def test_check_now_looks_in_the_background(app: App, site: Site) -> None:
    updates.RUNS.clear()
    assert app.do("update_check")["state"] in ("checking", "idle")
    done = finish(app)
    assert done["state"] == "idle" and [v["version"] for v in done["versions"]] == ["0.3.0", "0.2.0"]


def test_update_downloads_checks_and_unpacks_the_newest_for_the_mac_app(app: App, site: Site, tmp_path: Path) -> None:
    launch(app)
    started = app.do("update_start")
    assert started["state"] in ("downloading", "ready") and started["popup"] is False
    ready = finish(app)
    assert ready["state"] == "ready" and ready["progress"] == 1.0
    assert ready["staged"] == str(tmp_path / "updates" / "0.3.0" / "Friday.app") and ready["restart"] == "now"
    assert not (tmp_path / "updates" / "0.3.0" / "Friday-0.3.0.dmg").exists()  # the image let go once unpacked
    app.do("settings_set", key="updates", value={"restart": "quit"})
    assert app.do("update_status")["restart"] == "quit"


def test_a_download_that_isnt_the_published_file_fails_plainly(app: App, site: Site) -> None:
    launch(app)
    site.image = b"tampered"
    app.do("update_start")
    failed = finish(app)
    assert failed["state"] == "failed" and failed["staged"] is None
    assert failed["message"] == "The download isn't the file the site published (its checksum differs)."
    assert failed["popup"] is True  # the popup says what went wrong and offers Update again


def test_stop_ends_a_download_and_changes_nothing(app: App, site: Site, monkeypatch: pytest.MonkeyPatch) -> None:
    launch(app)
    gate = threading.Event()
    real = net.download

    def slow(entry: dict, folder: Path, progress, cancelled):  # noqa: ANN001, ANN202
        gate.wait(5)
        return real(entry, folder, progress=progress, cancelled=cancelled)

    monkeypatch.setattr(net, "download", slow)
    app.do("update_start")
    gate.set()
    stopped = app.do("update_stop")
    assert stopped["state"] in ("idle", "ready")
    if stopped["state"] == "idle":
        assert stopped["message"] == "Stopped. Nothing was changed." and stopped["staged"] is None


def test_after_updating_what_changed_shows_once(app: App, site: Site, monkeypatch: pytest.MonkeyPatch) -> None:
    launch(app)  # 0.1.0 runs and reads the feed (its notes are kept)
    monkeypatch.setenv("FRIDAY_APP_VERSION", "0.3.0")
    after = launch(app)  # the new version's first launch
    assert [v["version"] for v in after["whats_new"]] == ["0.3.0", "0.2.0"]
    assert after["whats_new"][1]["new"] == ["New in 0.2.0"] and after["popup"] is False
    assert app.do("whats_new_seen")["whats_new"] == []
    assert launch(app)["whats_new"] == []


def test_a_new_users_first_launch_has_nothing_to_tell(app: App, site: Site, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRIDAY_APP_VERSION", "0.3.0")
    assert launch(app)["whats_new"] == []


def test_it_looks_at_launch_then_again_after_a_month(app: App, site: Site) -> None:
    launch(app)
    assert not updates.due(app.conn, app.now_utc + 60, 1)
    assert updates.due(app.conn, app.now_utc + updates.MONTH_MIN, 1)


def test_an_unreachable_site_is_said_in_settings_not_raised(app: App, site: Site) -> None:
    site.down = True
    status = launch(app)
    assert status["message"].startswith("Couldn't look for an update: couldn't reach Friday's site")
    assert status["popup"] is False and status["last_checked"] is None


def test_a_copy_that_cant_replace_itself_says_so_before_downloading(
    app: App, site: Site, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    shut = tmp_path / "Applications"
    (shut / "Friday.app").mkdir(parents=True)
    shut.chmod(0o555)
    monkeypatch.setenv("FRIDAY_APP_PATH", str(shut / "Friday.app"))
    launch(app)
    try:
        with pytest.raises(FieldError, match="can't replace Friday in .*download the new version from the site"):
            app.do("update_start")
        assert app.do("update_status")["state"] == "idle"
    finally:
        shut.chmod(0o755)
