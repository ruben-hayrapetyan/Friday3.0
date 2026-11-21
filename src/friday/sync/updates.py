"""Friday's own updater, the network half: the update feed the admin hub writes
(`updates.json`: the current version and every offered version's notes), the newer versions in it, and a new version
fetched, checked against its checksum and unpacked from its disk image beside the app, ready for the Mac app to swap
in. Every Mac build but Friday Test reads the site's feed (Mac/build.sh). Friday names itself in each request
(`Friday/0.3.0 (Mac)`): Cloudflare, in front of the site, refuses Python's own name (error 1010). A test user's Friday
(H224) sends its device's key, in `X-Friday-Test-Key` (H233: from an invite, or from swapping the code typed before
invites; a Friday that still has only a code sends it in `X-Friday-Test-User`): the site then answers with the test
users' feed and lets their version be downloaded."""

import hashlib
import json
import logging
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger("friday.updates")
TIMEOUT_S = 15
CHUNK = 1 << 20
TEST_USER_HEADER = "X-Friday-Test-User"
TEST_KEY_HEADER = "X-Friday-Test-Key"


class UpdateError(Exception):
    """Something that stopped an update, said in a sentence."""


def version_key(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError as wrong:
        raise UpdateError(f"{version!r} isn't a version number") from wrong


def asking(
    url: str, version: str | None, test_code: str | None = None, test_key: str | None = None, body: dict | None = None
) -> urllib.request.Request:
    """A request that says it's Friday, and which version; this device's test-user key with it, else a code from before
    invites, if there is one; a JSON body makes it a POST."""
    headers = {"User-Agent": f"Friday/{version or 'dev'} (Mac)"}
    if test_key:
        headers[TEST_KEY_HEADER] = test_key
    elif test_code:
        headers[TEST_USER_HEADER] = test_code
    if body is None:
        return urllib.request.Request(url, headers=headers)
    headers["Content-Type"] = "application/json"
    return urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")


def fetch_feed(
    url: str,
    opener: Callable[..., Any] | None = None,
    *,
    version: str | None = None,
    test_code: str | None = None,
    test_key: str | None = None,
) -> dict:
    opener = opener or urllib.request.urlopen
    try:
        with opener(asking(url, version, test_code, test_key), timeout=TIMEOUT_S) as answer:
            feed = json.loads(answer.read())
    except (OSError, ValueError) as wrong:
        log.info("update feed %s: %s", url, wrong)
        raise UpdateError("couldn't reach Friday's site; it tries again next time") from wrong
    if not isinstance(feed, dict) or not isinstance(feed.get("versions"), list) or "current" not in feed:
        raise UpdateError("the update feed isn't in the expected shape")
    return feed


class InviteError(UpdateError):
    """An invite the site wouldn't take: `state` says why (used, gone, none, limited)."""

    def __init__(self, state: str) -> None:
        super().__init__(state)
        self.state = state


def post(url: str, body: dict, opener: Callable[..., Any] | None, version: str | None,
         test_code: str | None = None) -> tuple[int, dict]:  # fmt: skip
    """POST `body` to the site; its status and JSON answer (an error's too)."""
    opener = opener or urllib.request.urlopen
    try:
        with opener(asking(url, version, test_code, body=body), timeout=TIMEOUT_S) as answer:
            return getattr(answer, "status", 200), json.loads(answer.read())
    except urllib.error.HTTPError as refused:
        try:
            return refused.code, json.loads(refused.read())
        except ValueError:
            return refused.code, {}
    except (OSError, ValueError) as wrong:
        log.info("test users %s: %s", url, wrong)
        raise UpdateError("couldn't reach Friday's site; try again in a moment") from wrong


def join(site: str, invite: str, device: dict, opener: Callable[..., Any] | None = None, *,
         version: str | None = None) -> dict:  # fmt: skip
    """Use an invite (H233): this device's key and whose it is ({"key", "name"}); InviteError if the site refused it."""
    status, answer = post(f"{site}/test/join", {"invite": invite, "device": device}, opener, version)
    if status == 200 and isinstance(answer.get("key"), str):
        return answer
    raise InviteError(str(answer.get("state") or "none"))


def swap(site: str, code: str, device: dict, opener: Callable[..., Any] | None = None, *,
         version: str | None = None) -> dict | None:  # fmt: skip
    """A code from before invites, swapped for this device's key ({"key", "name"}); None when the site doesn't (a
    code it doesn't know, or a site from before invites)."""
    status, answer = post(f"{site}/test/swap", {"device": device}, opener, version, test_code=code)
    return answer if status == 200 and isinstance(answer.get("key"), str) else None


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
    test_code: str | None = None,
    test_key: str | None = None,
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
        with (
            opener(asking(entry["url"], version, test_code, test_key), timeout=TIMEOUT_S) as answer,
            partial.open("wb") as out,
        ):
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
