"""Updates through the whole pipeline (24 Nov, the user: every feature tested in every layer): a real `fridayd serve`
started as a downloaded Friday 0.2.0 is (its version and the feed's address), a stand-in for Friday's site on a real
port (the feed, test users' codes and invites, and downloads that are slow or not the file published), and every
updater command sent over HTTP as Settings → Updates sends it, with what `update_status` then says read back. Nothing
is installed: a download is stopped or fails its checksum (test_updater_system.py unpacks a real one). Then Friday is
started again as a newer version (what's new, once) and as a copy that doesn't look (each command refused)."""

import json
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx
import pytest

from tests.system.test_beat_plan_system import REPO, Friday, free_port

CODE = "K7QF-29XM"
INVITE = "Inv1te-for-Ana_0123456789"
KEY = "device-key-ana"


def entry(address: str, version: str, test: bool = False) -> dict:
    notes = {
        "summary": f"Friday {version}.",
        "new": [f"New in {version}."],
        "changed": [],
        "fixed": [f"Fixed in {version}."],
    }
    return {"version": version, "released": "2026-11-20", "url": f"{address}/dl/{version}.dmg",
            "sha256": "0" * 64, "bytes": 200 << 20, "minimum_macos": "14.0", "notes": notes,
            **({"test": True} if test else {})}  # fmt: skip


class Site:
    """Friday's site as the admin hub writes it: everyone's feed, and the test users' for Ana's code or key."""

    def __init__(self) -> None:
        self.port = free_port()
        self.address = f"http://127.0.0.1:{self.port}"
        self.everyone = ["0.1.9", "0.2.1"]  # what everyone is offered (0.1.9 is older than the 0.2.0 you have)
        self.download = "slow"  # "slow": 200 MB a megabyte at a time; "bad": a file that isn't the one published
        self.asked: list[dict[str, Any]] = []
        site = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:
                pass

            def send(self, body: dict | bytes, status: int = 200) -> None:
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def heard(self, body: dict | None = None) -> tuple[str | None, str | None]:
                code, key = self.headers.get("X-Friday-Test-User"), self.headers.get("X-Friday-Test-Key")
                site.asked.append({"path": self.path, "code": code, "key": key, "agent": self.headers.get("User-Agent"),
                                   "body": body})  # fmt: skip
                return code, key

            def do_GET(self) -> None:  # noqa: N802
                code, key = self.heard()
                ana = key == KEY or (code or "").replace("-", "").upper() == CODE.replace("-", "")
                if self.path == "/updates.json":
                    versions = [entry(site.address, v) for v in site.everyone]
                    feed: dict[str, Any] = {"current": site.everyone[-1], "versions": versions}
                    if code is not None or key is not None:
                        feed["test_user"] = "Ana" if ana else None
                    if ana:
                        feed |= {"current": "0.3.0", "versions": [entry(site.address, "0.3.0", True), *versions]}
                    return self.send(feed)
                if self.path.startswith("/dl/"):
                    if site.download == "bad":
                        return self.send(b"not the published disk image")
                    self.send_response(200)
                    self.send_header("Content-Length", str(200 << 20))
                    self.end_headers()
                    try:
                        for _ in range(200):
                            self.wfile.write(b"\0" * (1 << 20))
                            time.sleep(0.25)
                    except OSError:  # Friday stopped reading: the download was stopped
                        pass
                    return None
                return self.send({"state": "none"}, 404)

            def do_POST(self) -> None:  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                self.heard(body)
                if self.path == "/test/join":
                    invite = body.get("invite")
                    if invite == INVITE:
                        return self.send({"key": KEY, "name": "Ana"})
                    if invite.startswith("used"):
                        return self.send({"state": "used"}, 409)
                    if invite.startswith("gone"):
                        return self.send({"state": "gone"}, 410)
                    return self.send({"state": "none"}, 404)
                return self.send({}, 404)  # /test/swap: a site that keeps codes as codes

        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def feeds(self) -> list[dict]:
        return [a for a in self.asked if a["path"] == "/updates.json"]


@pytest.fixture(scope="module")
def site() -> Iterator[Site]:
    out = Site()
    yield out
    out.server.shutdown()


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory, site: Site) -> Iterator[Friday]:
    folder = tmp_path_factory.mktemp("updates")
    with pytest.MonkeyPatch.context() as env:
        env.setenv("FRIDAY_APP_VERSION", "0.2.0")
        env.setenv("FRIDAY_UPDATE_FEED", f"{site.address}/updates.json")
        env.setenv("FRIDAY_UPDATE_DIR", str(folder / "staging"))
        env.delenv("FRIDAY_APP_PATH", raising=False)
        server = Friday(folder)
    yield server
    server.stop()


def status(friday: Friday) -> dict:
    return friday.q("update_status")


def settled(friday: Friday, check: Any = lambda s: True) -> dict:
    """update_status once it isn't looking (and `check` holds)."""
    return friday.until(lambda: (s := status(friday))["state"] != "checking" and check(s) and s)


def refused(friday: Friday, verb: str, **body: Any) -> dict:
    answer = friday.http.post(f"/api/c/{verb}", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()


def offered(s: dict) -> list[str]:
    return [v["version"] for v in s["versions"]]


def restart(friday: Friday, **env: str | None) -> None:
    """The same Friday (its data) started again, as another version or another kind of copy."""
    friday.stop()
    for name, value in env.items():
        if value is None:
            friday.env.pop(name, None)
        else:
            friday.env[name] = value
    friday.port = free_port()
    friday.log = (friday.folder / "server.out").open("a")
    fridayd = [sys.executable, "-m", "friday.server.main", "--data-dir", str(friday.folder / "data")]
    friday.process = subprocess.Popen([*fridayd, "serve", "--port", str(friday.port)], cwd=REPO, env=friday.env,
                                      stdout=friday.log, stderr=subprocess.STDOUT)  # fmt: skip
    friday.http = httpx.Client(base_url=f"http://127.0.0.1:{friday.port}", timeout=300)

    def up() -> bool:
        try:
            return friday.http.get("/api/q/status").status_code == 200
        except httpx.HTTPError:
            return False

    friday.until(up)


def test_01_at_launch_it_looks_and_offers_only_newer_versions_with_their_notes(friday: Friday, site: Site) -> None:
    s = settled(friday, lambda s: s["versions"])
    assert s["checks"] is True and s["have"] == "0.2.0"
    assert offered(s) == ["0.2.1"]  # 0.1.9 is older than 0.2.0: never offered
    (v,) = s["versions"]
    assert (v["summary"], v["new"], v["fixed"], v["test"]) == (
        "Friday 0.2.1.",
        ["New in 0.2.1."],
        ["Fixed in 0.2.1."],
        False,
    )
    assert s["popup"] is True and s["last_checked"] is not None and s["test_user"] is None
    first = site.feeds()[0]
    assert first["agent"] == "Friday/0.2.0 (Mac)" and first["code"] is None and first["key"] is None


def test_02_check_now_looks_again_and_finds_what_was_published_since(friday: Friday, site: Site) -> None:
    looked = len(site.feeds())
    site.everyone = ["0.1.9", "0.2.1", "0.2.2"]
    answer = friday.c("update_check")
    assert answer["state"] in ("checking", "idle")
    s = settled(friday, lambda s: offered(s) == ["0.2.2", "0.2.1"])  # newest first
    assert len(site.feeds()) == looked + 1 and s["state"] == "idle" and s["message"] is None


def test_03_later_puts_the_newest_off_and_a_newer_one_asks_at_once(friday: Friday, site: Site) -> None:
    put_off = friday.c("update_later")
    assert put_off["popup"] is False and offered(put_off) == ["0.2.2", "0.2.1"]  # still offered in Settings
    assert status(friday)["popup"] is False  # kept, not just in the answer
    site.everyone = [*site.everyone, "0.2.3"]
    friday.c("update_check")
    s = settled(friday, lambda s: offered(s)[0] == "0.2.3")
    assert s["popup"] is True  # Later was for 0.2.2; 0.2.3 asks now
    again = friday.c("update_later")
    assert again["popup"] is False


def test_04_a_test_users_code_is_checked_and_brings_their_version(friday: Friday, site: Site) -> None:
    assert refused(friday, "update_test_join", code="K7QF")["field"] == "code"
    assert "eight letters and digits" in refused(friday, "update_test_join", code="K7QF-29X!")["message"]
    assert status(friday)["test_user"] is None  # a refused code is never kept
    wrong = friday.c("update_test_join", code="zzzz 9999")
    assert wrong["test_user"]["code"] == "ZZZZ-9999" and wrong["test_user"]["known"] is None  # shown at once
    s = settled(friday, lambda s: s["test_user"]["known"] is not None)
    assert s["test_user"] == {"code": "ZZZZ-9999", "name": None, "known": False, "device": False}
    assert "0.3.0" not in offered(s) and site.feeds()[-1]["code"] == "ZZZZ-9999"
    friday.c("update_test_join", code="k7qf29xm")  # as typed: the same code as K7QF-29XM
    s = settled(friday, lambda s: s["test_user"]["known"])
    assert s["test_user"] == {"code": CODE, "name": "Ana", "known": True, "device": False}
    assert [(v["version"], v["test"]) for v in s["versions"]][:2] == [("0.3.0", True), ("0.2.3", False)]
    assert site.feeds()[-1]["code"] == CODE


def test_05_leaving_forgets_the_code_and_the_test_users_version_at_once(friday: Friday, site: Site) -> None:
    left = friday.c("update_test_leave")
    assert left["test_user"] is None and "0.3.0" not in offered(left)  # before the look it starts answers
    s = settled(friday)
    assert s["test_user"] is None and offered(s) == ["0.2.3", "0.2.2", "0.2.1"]
    assert site.feeds()[-1]["code"] is None and site.feeds()[-1]["key"] is None


def test_06_an_invite_the_site_refuses_says_why_and_keeps_nothing(friday: Friday, site: Site) -> None:
    said = {
        "just words": "paste the whole invite link you were sent",
        "https://friday-scheduler.com/join#used-invite-0123456789": "used already",
        "friday://join?invite=gone-invite-0123456789": "run out",
        "unknown-invite-0123456789": "isn't an invite Friday's site knows",
    }
    for pasted, words in said.items():
        answer = refused(friday, "update_test_invite", invite=pasted)
        assert answer["field"] == "invite" and words in answer["message"], (pasted, answer)
    assert status(friday)["test_user"] is None
    joins = [a["body"]["invite"] for a in site.asked if a["path"] == "/test/join"]
    assert joins == [
        "used-invite-0123456789",
        "gone-invite-0123456789",
        "unknown-invite-0123456789",
    ]  # the invite alone


def test_07_an_invite_joins_this_device_with_its_own_key_sent_from_then_on(friday: Friday, site: Site) -> None:
    joined = friday.c("update_test_invite", invite=f"https://friday-scheduler.com/join#{INVITE}")
    assert joined["test_user"] == {"code": None, "name": "Ana", "known": True, "device": True}
    join = [a for a in site.asked if a["path"] == "/test/join"][-1]
    assert join["body"]["invite"] == INVITE and {"name", "system"} <= set(join["body"]["device"])
    s = settled(friday, lambda s: "0.3.0" in offered(s))
    assert s["versions"][0]["test"] is True and site.feeds()[-1]["key"] == KEY and site.feeds()[-1]["code"] is None
    left = friday.c("update_test_leave")
    assert left["test_user"] is None
    assert settled(friday)["test_user"] is None and site.feeds()[-1]["key"] is None


def test_08_a_download_that_isnt_the_file_published_fails_and_says_so(friday: Friday, site: Site) -> None:
    site.download = "bad"
    started = friday.c("update_start")
    assert started["state"] in ("downloading", "failed")  # a small wrong file can fail before the answer is made
    s = friday.until(lambda: (s := status(friday))["state"] == "failed" and s)
    assert s["message"] == "The download isn't the file the site published (its checksum differs)."
    assert s["staged"] is None and s["popup"] is False  # failed, but 0.2.3 is still put off with Later
    assert any(a["path"] == "/dl/0.2.3.dmg" for a in site.asked)  # the newest, as offered
    assert not list((friday.folder / "staging").rglob("*.dmg")) and not list(
        (friday.folder / "staging").rglob("*.part")
    )


def test_09_stop_ends_a_download_and_changes_nothing(friday: Friday, site: Site) -> None:
    site.download = "slow"
    assert friday.c("update_start")["state"] == "downloading"
    going = friday.until(lambda: (s := status(friday))["progress"] > 0 and s)
    assert going["state"] == "downloading" and 0 < going["progress"] < 1
    assert friday.c("update_start")["state"] == "downloading"  # pressed again: the same download, not a second
    stopped = friday.c("update_stop")
    assert (stopped["state"], stopped["message"]) == ("idle", "Stopped. Nothing was changed.")
    assert stopped["staged"] is None and offered(stopped)[0] == "0.2.3"
    time.sleep(1)
    assert status(friday)["state"] == "idle"
    assert not list((friday.folder / "staging").rglob("*.dmg")) and not list(
        (friday.folder / "staging").rglob("*.part")
    )
    assert friday.c("update_stop")["state"] == "idle"  # nothing going on: nothing to stop


def test_10_with_nothing_newer_there_is_nothing_to_download(friday: Friday, site: Site) -> None:
    site.everyone = ["0.1.9"]
    friday.c("update_check")
    s = settled(friday, lambda s: not s["versions"])
    assert s["popup"] is False
    assert refused(friday, "update_start")["message"] == "updates: there's no newer version to download"
    assert status(friday)["state"] == "idle"
    site.everyone = ["0.1.9", "0.2.1", "0.2.2", "0.2.3"]
    friday.c("update_check")
    assert offered(settled(friday, lambda s: s["versions"])) == ["0.2.3", "0.2.2", "0.2.1"]


def test_11_a_new_version_shows_what_changed_since_yours_once(friday: Friday) -> None:
    assert friday.c("whats_new_seen")["whats_new"] == []  # nothing new in the version you've had
    restart(friday, FRIDAY_APP_VERSION="0.2.2")
    s = status(friday)
    assert s["have"] == "0.2.2"
    assert [v["version"] for v in s["whats_new"]] == ["0.2.2", "0.2.1"]  # newest first, not 0.2.3 nor yours before
    assert s["whats_new"][0]["new"] == ["New in 0.2.2."]
    assert offered(s) == ["0.2.3"]  # what you have now isn't offered
    seen = friday.c("whats_new_seen")
    assert seen["whats_new"] == [] and status(friday)["whats_new"] == []


def test_12_a_copy_that_doesnt_look_refuses_each_look_and_says_why(friday: Friday) -> None:
    restart(friday, FRIDAY_UPDATE_FEED=None)
    s = status(friday)
    assert s["checks"] is False
    assert refused(friday, "update_check")["message"] == (
        "updates: this Friday is built from its code here, so it doesn't look for updates"
    )
    assert "can't be a test user" in refused(friday, "update_test_join", code=CODE)["message"]
    assert "can't be a test user" in refused(friday, "update_test_invite", invite=INVITE)["message"]
    assert status(friday)["test_user"] is None
    left = friday.c("update_test_leave")  # nothing to leave, and no look made
    assert left["state"] == "idle" and left["test_user"] is None
