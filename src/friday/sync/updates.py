"""Friday's own updater, the network half (HOSTED.md H118–H121, H139, H169): the update feed the admin hub writes
(`updates.json`: the current version and every offered version's notes), the newer versions in it, and a new version
fetched, checked against its checksum and unpacked from its disk image beside the app, ready for the Mac app to swap
in. Every Mac build but Friday Test reads the site's feed (Mac/build.sh). Friday names itself in each request
(`Friday/0.3.0 (Mac)`): Cloudflare, in front of the site, refuses Python's own name (error 1010)."""

import hashlib
import json
import logging
import shutil
import subprocess
import tempfile
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger("friday.updates")
TIMEOUT_S = 15
CHUNK = 1 << 20


class UpdateError(Exception):
    """Something that stopped an update, said in a sentence."""


def version_key(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError as wrong:
        raise UpdateError(f"{version!r} isn't a version number") from wrong


def asking(url: str, version: str | None) -> urllib.request.Request:
    """A request that says it's Friday, and which version."""
    return urllib.request.Request(url, headers={"User-Agent": f"Friday/{version or 'dev'} (Mac)"})


def fetch_feed(url: str, opener: Callable[..., Any] | None = None, *, version: str | None = None) -> dict:
    opener = opener or urllib.request.urlopen
    try:
        with opener(asking(url, version), timeout=TIMEOUT_S) as answer:
            feed = json.loads(answer.read())
    except (OSError, ValueError) as wrong:
        log.info("update feed %s: %s", url, wrong)
        raise UpdateError("couldn't reach Friday's site; it tries again next time") from wrong
    if not isinstance(feed, dict) or not isinstance(feed.get("versions"), list) or "current" not in feed:
        raise UpdateError("the update feed isn't in the expected shape")
    return feed


def newer(feed: dict, have: str) -> list[dict]:
    """The offered versions newer than the one you have, newest first: each one's notes are shown (H139)."""
    mine = version_key(have)
    found = [v for v in feed["versions"] if version_key(v["version"]) > mine]
    return sorted(found, key=lambda v: version_key(v["version"]), reverse=True)


def download(
    entry: dict,
    folder: Path,
    progress: Callable[[float], None] = lambda done: None,
    cancelled: Callable[[], bool] = lambda: False,
    opener: Callable[..., Any] | None = None,
    *,
    version: str | None = None,
) -> Path:
    """The version's disk image, saved in `folder` and checked against the feed's checksum before it's kept."""
    opener = opener or urllib.request.urlopen
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"Friday-{entry['version']}.dmg"
    partial = target.with_suffix(".part")
    digest = hashlib.sha256()
    total = max(int(entry.get("bytes") or 0), 1)
    got = 0
    try:
        with opener(asking(entry["url"], version), timeout=TIMEOUT_S) as answer, partial.open("wb") as out:
            while chunk := answer.read(CHUNK):
                if cancelled():
                    raise UpdateError("the update was stopped")
                out.write(chunk)
                digest.update(chunk)
                got += len(chunk)
                progress(min(got / total, 1.0))
    except OSError as wrong:
        partial.unlink(missing_ok=True)
        log.info("update download %s: %s", entry["url"], wrong)
        raise UpdateError("the download didn't finish; check the connection and press Update again") from wrong
    except UpdateError:
        partial.unlink(missing_ok=True)
        raise
    if digest.hexdigest() != entry["sha256"]:
        partial.unlink(missing_ok=True)
        raise UpdateError("the download isn't the file the site published (its checksum differs)")
    partial.replace(target)
    return target


def unpack(image: Path, folder: Path, run: Callable[..., Any] = subprocess.run) -> Path:
    """Friday.app copied out of the disk image into `folder`, file times kept (the compiled planner is checked
    against them); the image is let go of afterwards."""
    staged = folder / "Friday.app"
    if staged.exists():
        shutil.rmtree(staged)
    mount = Path(tempfile.mkdtemp(prefix="friday-update-"))
    try:
        run(["hdiutil", "attach", "-quiet", "-nobrowse", "-readonly", "-mountpoint", str(mount), str(image)],
            check=True, capture_output=True, timeout=120)  # fmt: skip
        try:
            run(["ditto", str(mount / "Friday.app"), str(staged)], check=True, capture_output=True, timeout=600)
        finally:
            run(["hdiutil", "detach", "-quiet", str(mount)], capture_output=True, timeout=60)
    except (subprocess.SubprocessError, OSError) as wrong:
        log.info("update disk image %s: %s", image, wrong)
        raise UpdateError("couldn't open the new version's disk image; press Update to try again") from wrong
    finally:
        shutil.rmtree(mount, ignore_errors=True)
    if not (staged / "Contents" / "MacOS").is_dir():
        raise UpdateError("the disk image didn't hold Friday")
    return staged
