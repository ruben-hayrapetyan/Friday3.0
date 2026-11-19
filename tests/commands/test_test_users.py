"""Test users (H224–H227), black box through the updater's commands: a code typed in Settings → Updates is
checked with the site, sent with every look and download from then on, and brings the version the site offers test
users; a code the site doesn't know is said so; leaving keeps the version you have and is offered only everyone's
from then on. The site is a stand-in that answers as friday_hub/site.py does (the hub's own tests cover that one)."""

import io
import json
import threading
import urllib.request
from collections.abc import Iterator
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

    def __call__(self, request: urllib.request.Request, timeout: int) -> io.BytesIO:
        sent = request.get_header("X-friday-test-user")
        self.asked.append((request.full_url, sent))
        while self.meanwhile:
            self.meanwhile.pop(0)()
        if self.held is not None:
            self.held.wait(10)
        if self.down:
            raise OSError("no route to host")
        if request.full_url != FEED:
            return io.BytesIO(b"Friday 0.3.0's disk image")
        feed: dict = {"current": self.everyone[0]["version"], "versions": self.everyone}
        if sent is not None:
            name = self.codes.get(sent.replace("-", "").upper())
            feed["test_user"] = name
            if name:
                feed = feed | {"current": "0.3.0", "versions": [self.test, *self.everyone]}
        return io.BytesIO(json.dumps(feed).encode())


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
    assert checking["state"] == "checking" and checking["test_user"] == {"code": CODE, "name": None, "known": None}
    site.held.set()
    done = finish(app)
    assert done["test_user"] == {"code": CODE, "name": "Ana", "known": True}
    assert [(v["version"], v["test"]) for v in done["versions"]] == [("0.3.0", True), ("0.2.0", False)]
    assert done["popup"] is True
    assert site.asked[-1] == (FEED, CODE)


def test_a_code_the_site_doesnt_know_is_said_and_brings_nothing_new(app: App, site: Site) -> None:
    launch(app)
    done = join(app, "ZZZZ-ZZZZ")
    assert done["test_user"] == {"code": "ZZZZ-ZZZZ", "name": None, "known": False}
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
    assert status["test_user"] == {"code": CODE, "name": None, "known": False}
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
    assert failed["test_user"] == {"code": CODE, "name": None, "known": None}
    assert "Couldn't reach Friday's site" in failed["message"]
    site.down = False
    assert launch(app)["test_user"] == {"code": CODE, "name": "Ana", "known": True}


def test_a_copy_that_doesnt_look_for_updates_cant_join(app: App, site: Site, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FRIDAY_UPDATE_FEED")
    with pytest.raises(FieldError, match="doesn't look for updates"):
        app.do("update_test_join", code=CODE)


def test_the_code_is_kept_with_the_data_not_the_app(app: App, site: Site) -> None:
    launch(app)
    join(app)
    updates.RUNS.clear()  # Friday quits and opens again
    assert app.do("update_status")["test_user"] == {"code": CODE, "name": "Ana", "known": True}


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
    assert done["test_user"] == {"code": CODE, "name": "Ana", "known": True}
    assert [v["version"] for v in done["versions"]] == ["0.3.0", "0.2.0"]
    assert site.asked[-2:] == [(FEED, None), (FEED, CODE)]


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
    assert join(app)["test_user"] == {"code": CODE, "name": None, "known": False}


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
