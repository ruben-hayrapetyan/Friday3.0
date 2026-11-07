"""Glass box: the updater's network half (sync/updates.py). The feed read and checked, the newer versions in it, a
disk image downloaded with its progress and kept only when its checksum matches, and Friday.app unpacked from a real
disk image (on a Mac). The network is a stand-in throughout."""

import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from friday.sync import updates
from friday.sync.updates import UpdateError

IMAGE = b"a disk image" * 1000


def answer(body: bytes):  # noqa: ANN201
    return lambda url, timeout: io.BytesIO(body)


def entry(version: str = "0.2.0", body: bytes = IMAGE) -> dict:
    return {"version": version, "url": f"https://site/downloads/Friday-{version}.dmg",
            "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}  # fmt: skip


def test_the_feed_is_read_and_its_shape_checked() -> None:
    feed = {"current": "0.2.0", "versions": [entry()]}
    assert updates.fetch_feed("u", answer(json.dumps(feed).encode())) == feed
    with pytest.raises(UpdateError, match="expected shape"):
        updates.fetch_feed("u", answer(b'{"versions": "no"}'))

    def unreachable(url: str, timeout: int) -> io.BytesIO:
        raise OSError("no route to host")

    with pytest.raises(UpdateError, match="couldn't reach Friday's site"):
        updates.fetch_feed("u", unreachable)


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
