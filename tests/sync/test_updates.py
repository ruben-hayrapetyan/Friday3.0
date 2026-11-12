"""Glass box: the updater's network half (sync/updates.py). The feed read and checked, the newer versions in it, a
disk image downloaded with its progress and kept only when its checksum matches, and Friday.app unpacked from a real
disk image (on a Mac). The network is a stand-in throughout."""

import hashlib
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from friday.sync import updates
from friday.sync.updates import UpdateError

IMAGE = b"a disk image" * 1000


def answer(body: bytes, asked: list | None = None):  # noqa: ANN201
    def opener(request, timeout):  # noqa: ANN001, ANN202
        if asked is not None:
            asked.append(request)
        return io.BytesIO(body)

    return opener


def entry(version: str = "0.2.0", body: bytes = IMAGE) -> dict:
    return {"version": version, "url": f"https://site/downloads/Friday-{version}.dmg",
            "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}  # fmt: skip


def test_the_feed_is_read_and_its_shape_checked() -> None:
    feed = {"current": "0.2.0", "versions": [entry()]}
    assert updates.fetch_feed("https://site/updates.json", answer(json.dumps(feed).encode())) == feed
    with pytest.raises(UpdateError, match="expected shape"):
        updates.fetch_feed("https://site/updates.json", answer(b'{"versions": "no"}'))

    def unreachable(request: object, timeout: int) -> io.BytesIO:
        raise OSError("no route to host")

    with pytest.raises(UpdateError, match="couldn't reach Friday's site"):
        updates.fetch_feed("https://site/updates.json", unreachable)


def test_every_request_says_it_is_friday_and_which_version(tmp_path: Path) -> None:
    asked: list = []
    feed = {"current": "0.2.0", "versions": [entry()]}
    updates.fetch_feed("https://site/updates.json", answer(json.dumps(feed).encode(), asked), version="0.3.0")
    updates.download(entry(), tmp_path, opener=answer(IMAGE, asked), version="0.3.0")
    assert [r.full_url for r in asked] == ["https://site/updates.json", "https://site/downloads/Friday-0.2.0.dmg"]
    assert {r.get_header("User-agent") for r in asked} == {"Friday/0.3.0 (Mac)"}  # never Python's own name
    assert updates.asking("https://site/updates.json", None).get_header("User-agent") == "Friday/dev (Mac)"


def test_only_newer_versions_count_newest_first_by_number_not_by_text() -> None:
    feed = {"current": "0.10.0", "versions": [entry("0.9.0"), entry("0.10.0"), entry("0.1.0")]}
    assert [v["version"] for v in updates.newer(feed, "0.2.0")] == ["0.10.0", "0.9.0"]
    assert updates.newer(feed, "0.10.0") == []


def test_a_download_is_kept_only_when_its_checksum_matches(tmp_path: Path) -> None:
    seen: list[float] = []
    kept = updates.download(entry(), tmp_path, progress=seen.append, opener=answer(IMAGE))
    assert kept.read_bytes() == IMAGE and seen[-1] == 1.0 and seen == sorted(seen)
    with pytest.raises(UpdateError, match="checksum differs"):
        updates.download(entry("0.3.0"), tmp_path, opener=answer(b"something else"))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["Friday-0.2.0.dmg"]  # nothing half-kept


def test_a_stopped_download_leaves_nothing(tmp_path: Path) -> None:
    with pytest.raises(UpdateError, match="stopped"):
        updates.download(entry(), tmp_path, cancelled=lambda: True, opener=answer(IMAGE))
    assert list(tmp_path.iterdir()) == []


def test_a_version_that_isnt_a_number_is_said_so() -> None:
    with pytest.raises(UpdateError, match="'0.3-beta' isn't a version number"):
        updates.newer({"current": "0.3-beta", "versions": [entry("0.3-beta")]}, "0.2.0")


def test_a_download_cut_off_leaves_nothing_and_says_try_again(tmp_path: Path) -> None:
    class CutOff(io.BytesIO):
        def read(self, size: int = -1) -> bytes:
            if self.tell():
                raise ConnectionResetError("connection reset by peer")
            return super().read(10)

    with pytest.raises(UpdateError, match="didn't finish; check the connection"):
        updates.download(entry(), tmp_path, opener=lambda request, timeout: CutOff(IMAGE))
    assert list(tmp_path.iterdir()) == []


class Hdiutil:
    """hdiutil and ditto, stood in for: attaching "mounts" `holds` (a folder standing for the image's contents)."""

    def __init__(self, holds: Path, fails: str | None = None) -> None:
        self.holds, self.fails = holds, fails
        self.ran: list[str] = []

    def __call__(self, command: list[str], **kwargs: object) -> None:
        verb = command[1] if command[0] == "hdiutil" else command[0]
        self.ran.append(verb)
        if verb == self.fails:
            raise subprocess.CalledProcessError(1, command)
        if verb == "attach":
            mount = Path(command[command.index("-mountpoint") + 1])
            for part in self.holds.iterdir():
                (mount / part.name).symlink_to(part)
        if verb == "ditto" and Path(command[1]).exists():
            shutil.copytree(Path(command[1]).resolve(), command[2])


def contents(tmp_path: Path, with_friday: bool) -> Path:
    holds = tmp_path / "image"
    (holds / ("Friday.app" if with_friday else "Other.app") / "Contents" / "MacOS").mkdir(parents=True)
    return holds


def test_a_version_unpacked_before_is_replaced(tmp_path: Path) -> None:
    old = tmp_path / "out" / "Friday.app" / "Contents" / "Resources" / "old-version"
    old.parent.mkdir(parents=True)
    old.write_text("0.1.0")
    run = Hdiutil(contents(tmp_path, with_friday=True))
    staged = updates.unpack(tmp_path / "Friday.dmg", tmp_path / "out", run=run)
    assert (staged / "Contents" / "MacOS").is_dir() and not old.exists()
    assert run.ran == ["attach", "ditto", "detach"]


def test_an_image_without_friday_is_refused_and_let_go(tmp_path: Path) -> None:
    run = Hdiutil(contents(tmp_path, with_friday=False))
    with pytest.raises(UpdateError, match="didn't hold Friday"):
        updates.unpack(tmp_path / "Friday.dmg", tmp_path / "out", run=run)
    assert run.ran == ["attach", "ditto", "detach"]


@pytest.mark.parametrize("fails", ["attach", "ditto"])
def test_an_image_that_cant_be_opened_or_copied_says_press_update_again(tmp_path: Path, fails: str) -> None:
    run = Hdiutil(contents(tmp_path, with_friday=True), fails=fails)
    with pytest.raises(UpdateError, match="press Update to try again"):
        updates.unpack(tmp_path / "Friday.dmg", tmp_path / "out", run=run)
    assert run.ran == (["attach"] if fails == "attach" else ["attach", "ditto", "detach"])  # let go once attached


def disk_image(tmp_path: Path, with_friday: bool) -> Path:
    stage = tmp_path / "stage"
    (stage / ("Friday.app" if with_friday else "Other.app") / "Contents" / "MacOS").mkdir(parents=True)
    image = tmp_path / "Friday.dmg"
    subprocess.run(["hdiutil", "create", "-quiet", "-volname", "Friday", "-srcfolder", str(stage), "-format", "ULFO",
                    str(image)], check=True)  # fmt: skip
    return image


@pytest.mark.skipif(sys.platform != "darwin", reason="hdiutil opens disk images")
def test_friday_is_unpacked_from_a_real_disk_image_and_the_image_let_go(tmp_path: Path) -> None:
    staged = updates.unpack(disk_image(tmp_path, with_friday=True), tmp_path / "out")
    assert (staged / "Contents" / "MacOS").is_dir() and staged.name == "Friday.app"
    mounted = subprocess.run(["hdiutil", "info"], capture_output=True, text=True).stdout
    assert str(tmp_path) not in mounted  # detached again


@pytest.mark.skipif(sys.platform != "darwin", reason="hdiutil opens disk images")
def test_a_disk_image_without_friday_is_refused(tmp_path: Path) -> None:
    with pytest.raises(UpdateError, match="disk image"):
        updates.unpack(disk_image(tmp_path, with_friday=False), tmp_path / "out")
