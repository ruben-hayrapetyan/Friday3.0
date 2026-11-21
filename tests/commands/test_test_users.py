"""Test users (H224–H227), black box through the updater's commands: a code typed in Settings → Updates is
checked with the site, sent with every look and download from then on, and brings the version the site offers test
users; a code the site doesn't know is said so; leaving keeps the version you have and is offered only everyone's
from then on. The site is a stand-in that answers as friday_hub/site.py does (the hub's own tests cover that one)."""

import io
import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from email.message import Message
from pathlib import Path

import pytest

from friday.commands import updates
from friday.core.items import FieldError
from friday.sync import updates as net
from tests.commands.helpers import App, new_app
from tests.commands.test_updates import FEED, finish, launch, version

CODE = "K7QF-29XM"


class Site:
    """Everyone's feed, and for Ana's code the test users' feed (their version on top, saying whose code it is)."""

    def __init__(self) -> None:
        self.everyone = [version("0.2.0", "Two."), version("0.1.0", "One.")]
        self.test = version("0.3.0", "Three, for test users.") | {
            "url": "https://site.example/test/Friday-0.3.0.dmg", "test": True}  # fmt: skip
        self.codes = {"K7QF29XM": "Ana"}
        self.asked: list[tuple[str, str | None]] = []
        self.down = False
        self.meanwhile: list = []  # what you do while it's looking, once each
        self.held: threading.Event | None = None  # set: each answer waits until it's let go
        self.invites_on = False  # a site from before invites (H233) answers /test/join and /test/swap with 404
        self.invites: dict[str, str] = {}  # invite → name; used ones leave
        self.keys: dict[str, str] = {}  # key → name
        self.joined: list[dict] = []  # each device that joined, as Friday described it

    def __call__(self, request: urllib.request.Request, timeout: int) -> io.BytesIO:
        sent = request.get_header("X-friday-test-user")
        key = request.get_header("X-friday-test-key")
        self.asked.append((request.full_url, sent or (key and "key")))
        if request.full_url.endswith(("/test/join", "/test/swap")):
            return self.invite_or_swap(request, sent)
        while self.meanwhile:
            self.meanwhile.pop(0)()
        if self.held is not None:
            self.held.wait(10)
        if self.down:
            raise OSError("no route to host")
        if request.full_url != FEED:
            return io.BytesIO(b"Friday 0.3.0's disk image")
        feed: dict = {"current": self.everyone[0]["version"], "versions": self.everyone}
        if key is not None:  # a wrong key gets exactly the public feed
            name = self.keys.get(key)
            if name:
                feed = {"current": "0.3.0", "versions": [self.test, *self.everyone], "test_user": name}
            return io.BytesIO(json.dumps(feed).encode())
        if sent is not None:
            name = self.codes.get(sent.replace("-", "").upper())
            feed["test_user"] = name
            if name:
                feed = feed | {"current": "0.3.0", "versions": [self.test, *self.everyone]}
        return io.BytesIO(json.dumps(feed).encode())

    def invite_or_swap(self, request: urllib.request.Request, code: str | None) -> io.BytesIO:
        refuse = lambda status, state: urllib.error.HTTPError(  # noqa: E731
            request.full_url, status, state, Message(), io.BytesIO(json.dumps({"state": state}).encode())
        )
        if not self.invites_on:
            raise refuse(404, "none")
        body = json.loads(request.data or b"{}")
        if request.full_url.endswith("/test/join"):
            name = self.invites.pop(body.get("invite", ""), None)
            if name is None:
                raise refuse(409, "used" if body.get("invite") == "used-invite-0000000" else "none")
        else:
            name = self.codes.get((code or "").replace("-", "").upper())
            if name is None:
                raise refuse(404, "none")
        key = f"key-{len(self.keys)}-" + "k" * 40
        self.keys[key] = name
        self.joined.append(body.get("device", {}))
        return io.BytesIO(json.dumps({"key": key, "name": name}).encode())


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


def join(app: App, code: str = CODE) -> dict:
    app.do("update_test_join", code=code)
    return finish(app)


def test_not_a_test_user_sends_no_code(app: App, site: Site) -> None:
    status = launch(app)
    assert status["test_user"] is None
    assert [v["version"] for v in status["versions"]] == ["0.2.0"]
    assert site.asked == [(FEED, None)]


def test_a_code_is_checked_with_the_site_and_brings_the_test_users_version(app: App, site: Site) -> None:
    launch(app)
    site.held = threading.Event()  # the site hasn't answered yet (18 Nov: on debian it sometimes had, and this failed)
    checking = app.do("update_test_join", code=" k7qf 29xm ")
    assert checking["state"] == "checking" and checking["test_user"] == {
        "code": CODE,
        "name": None,
        "known": None,
        "device": False,
    }
    site.held.set()
    done = finish(app)
    assert done["test_user"] == {"code": CODE, "name": "Ana", "known": True, "device": False}
    assert [(v["version"], v["test"]) for v in done["versions"]] == [("0.3.0", True), ("0.2.0", False)]
    assert done["popup"] is True
    assert site.asked[-1] == (FEED, CODE)


def test_a_code_the_site_doesnt_know_is_said_and_brings_nothing_new(app: App, site: Site) -> None:
    launch(app)
    done = join(app, "ZZZZ-ZZZZ")
    assert done["test_user"] == {"code": "ZZZZ-ZZZZ", "name": None, "known": False, "device": False}
    assert [v["version"] for v in done["versions"]] == ["0.2.0"]


def test_a_code_that_isnt_eight_letters_and_digits_is_refused_before_asking(app: App, site: Site) -> None:
    launch(app)
    for typed in ("", "K7QF", "K7QF-29XM-1", "K7QF-29X!"):
        with pytest.raises(FieldError, match="eight letters and digits"):
            app.do("update_test_join", code=typed)
    assert app.do("update_status")["test_user"] is None and len(site.asked) == 1


def test_the_code_goes_with_every_look_and_download_after(app: App, site: Site) -> None:
    launch(app)
    join(app)
    launch(app)  # a new launch, a day later: still a test user
    assert site.asked[-1] == (FEED, CODE)
    app.do("update_start")
    ready = finish(app)
    assert ready["state"] == "ready"
    assert site.asked[-1] == ("https://site.example/test/Friday-0.3.0.dmg", CODE)


def test_removed_in_the_hub_the_next_look_says_so_and_offers_only_everyones(app: App, site: Site) -> None:
    launch(app)
    join(app)
    del site.codes["K7QF29XM"]
    status = launch(app)
    assert status["test_user"] == {"code": CODE, "name": None, "known": False, "device": False}
    assert [v["version"] for v in status["versions"]] == ["0.2.0"]


def test_leaving_keeps_the_version_you_have_and_offers_only_everyones(
    app: App, site: Site, monkeypatch: pytest.MonkeyPatch
) -> None:
    launch(app)
    join(app)
    monkeypatch.setenv("FRIDAY_APP_VERSION", "0.3.0")  # updated to the test users' version
    launch(app)
    app.do("update_test_leave")
    left = finish(app)
    assert left["test_user"] is None and left["versions"] == [] and left["have"] == "0.3.0"
    assert site.asked[-1] == (FEED, None)


def test_a_site_out_of_reach_keeps_the_code_to_check_next_time(app: App, site: Site) -> None:
    launch(app)
    site.down = True
    failed = join(app)
    assert failed["test_user"] == {"code": CODE, "name": None, "known": None, "device": False}
    assert "Couldn't reach Friday's site" in failed["message"]
    site.down = False
    assert launch(app)["test_user"] == {"code": CODE, "name": "Ana", "known": True, "device": False}


def test_a_copy_that_doesnt_look_for_updates_cant_join(app: App, site: Site, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FRIDAY_UPDATE_FEED")
    with pytest.raises(FieldError, match="doesn't look for updates"):
        app.do("update_test_join", code=CODE)


def test_the_code_is_kept_with_the_data_not_the_app(app: App, site: Site) -> None:
    launch(app)
    join(app)
    updates.RUNS.clear()  # Friday quits and opens again
    assert app.do("update_status")["test_user"] == {"code": CODE, "name": "Ana", "known": True, "device": False}


# 18 Nov: the system test saw the code known before the versions it brings (each write was its own commit), and a
# look still going when you left would write your code back.


def test_leaving_while_it_looks_with_the_code_isnt_undone_by_that_look(app: App, site: Site, tmp_path: Path) -> None:
    launch(app)
    join(app)
    other = new_app(tmp_path)  # the page, on its own connection, while the job's look is out
    site.meanwhile.append(lambda: other.do("update_test_leave"))
    updates.RUNS.clear()
    launch(app)  # its answer, for the code you had, is dropped
    status = finish(app)  # and the look leaving started, without it
    assert status["test_user"] is None
    assert [v["version"] for v in status["versions"]] == ["0.2.0"]


def test_joining_while_a_look_without_the_code_is_out_looks_again_with_it(app: App, site: Site, tmp_path: Path) -> None:
    launch(app)
    other = new_app(tmp_path)
    site.meanwhile.append(lambda: other.do("update_test_join", code=CODE))
    app.do("update_check")
    done = finish(app)
    assert done["test_user"] == {"code": CODE, "name": "Ana", "known": True, "device": False}
    assert [v["version"] for v in done["versions"]] == ["0.3.0", "0.2.0"]
    # the feed asked without the code, then with it (a site from before invites refused the swap in between)
    assert [a for a in site.asked if a[0] == FEED][-2:] == [(FEED, None), (FEED, CODE)]


def test_leaving_stops_offering_the_test_users_version_at_once(app: App, site: Site) -> None:
    launch(app)
    join(app)
    site.down = True  # the look after leaving can't reach the site
    app.do("update_test_leave")
    left = finish(app)
    assert left["test_user"] is None and [v["version"] for v in left["versions"]] == ["0.2.0"]


def test_a_site_that_says_nothing_of_the_code_doesnt_know_it(app: App, site: Site, monkeypatch) -> None:  # noqa: ANN001
    """18 Nov, seen on a demo: the site before test users answers without `test_user`, and the row said the code would
    be checked the next time Friday looked, just after it had."""
    launch(app)
    answered = Site.__call__

    def silent(self: Site, request, timeout):  # noqa: ANN001, ANN202
        feed = json.loads(answered(self, request, timeout).read())
        feed.pop("test_user", None)
        return io.BytesIO(json.dumps(feed).encode())

    monkeypatch.setattr(Site, "__call__", silent)
    assert join(app)["test_user"] == {"code": CODE, "name": None, "known": False, "device": False}


def test_only_you_can_join_or_leave_never_an_assistants_token(app: App, site: Site) -> None:
    """Which versions this Friday is offered is yours to choose: an assistant (MCP or the HTTP API with its token)
    never signs you up for test versions or takes you off them."""
    from friday.commands.registry import YOURS_ONLY

    assert {"update_test_join", "update_test_leave"} <= YOURS_ONLY
    launch(app)
    app.actor = "mcp:claude"
    for name, payload in (("update_test_join", {"code": CODE}), ("update_test_leave", {})):
        with pytest.raises(FieldError, match="Only you can do that"):
            app.do(name, **payload)


# Invites and device keys (H233)

INVITE = "Inv1te-abcdefghijklmnop"


@pytest.mark.parametrize(
    "pasted",
    [f"https://site.example/join#{INVITE}", f"friday://join?invite={INVITE}", INVITE, f"  {INVITE}\n"],
)
def test_an_invite_joins_this_device_with_its_own_key(app: App, site: Site, pasted: str) -> None:
    """The link as sent, Friday's own friday://join, or the invite alone: the site swaps it once for this device's key,
    kept here and sent with each look; the page learns only that there is one."""
    launch(app)
    site.invites_on, site.invites[INVITE] = True, "Ana"
    app.do("update_test_invite", invite=pasted)
    done = finish(app)
    assert done["test_user"] == {"code": None, "name": "Ana", "known": True, "device": True}
    assert [v["version"] for v in done["versions"]] == ["0.3.0", "0.2.0"]
    assert site.asked[-1] == (FEED, "key")  # the look after joining sent the key
    (device,) = site.joined
    assert device["name"] and device["system"]  # what the hub lists it as
    assert "key-" not in json.dumps(app.do("update_status"))  # the key never goes to the page


@pytest.mark.parametrize(
    ("invite", "said"),
    [("used-invite-0000000", "this invite was used already"), ("no-such-invite-0000", "paste the whole link")],
)
def test_an_invite_the_site_refuses_says_why(app: App, site: Site, invite: str, said: str) -> None:
    launch(app)
    site.invites_on = True
    with pytest.raises(FieldError, match=said):
        app.do("update_test_invite", invite=invite)
    assert app.do("update_status")["test_user"] is None
    with pytest.raises(FieldError, match="paste the whole invite link"):
        app.do("update_test_invite", invite="hi")


def test_a_code_from_before_is_swapped_for_a_key_on_the_next_look(app: App, site: Site) -> None:
    launch(app)
    join(app)  # a code, as test users joined before invites
    site.invites_on = True  # the site now has invites
    app.do("update_check")
    done = finish(app)
    assert done["test_user"] == {"code": None, "name": "Ana", "known": True, "device": True}
    assert site.asked[-2:] == [("https://site.example/test/swap", CODE), (FEED, "key")]


def test_a_removed_devices_key_is_no_longer_a_test_users(app: App, site: Site) -> None:
    """Its key gets the public feed, which names nobody: offered only everyone's versions from then on."""
    launch(app)
    site.invites_on, site.invites[INVITE] = True, "Ana"
    app.do("update_test_invite", invite=INVITE)
    finish(app)
    site.keys.clear()  # removed in the hub
    app.do("update_check")
    done = finish(app)
    assert done["test_user"] == {"code": None, "name": None, "known": False, "device": True}
    assert [v["version"] for v in done["versions"]] == ["0.2.0"]
