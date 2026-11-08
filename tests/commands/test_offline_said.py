"""No internet, said as that (8 Nov: with the Wi-Fi off the banner read "student@school.edu can't be read:
TransportError: HTTPSConnectionPool(host='oauth2.googleapis.com', port=443): Max retries exceeded … Failed to resolve …"
for each of four sources). Glass box: which errors mean no internet, and the web app's test matching the server's.
Black box: four sources offline make one line naming them; a source failing for its own reason keeps its words beside
it. The whole system: a calendar link read with no way to its server, through the sync job to `status`."""

import re
from pathlib import Path

import httpx
import pytest

from friday.commands.fetching import FAILURES_FOR_BANNER, OFFLINE, failing_sources, is_offline, why
from tests.commands.helpers import App, new_app
from tests.commands.test_sign_in_gone import GOOGLE_SAYS, PLAIN, failed

REPO = Path(__file__).resolve().parents[2]
GOOGLE_OFFLINE = (
    "TransportError: HTTPSConnectionPool(host='oauth2.googleapis.com', port=443): Max retries exceeded with url: "
    "/token "
    "(Caused by NameResolutionError(\"HTTPSConnection(host='oauth2.googleapis.com', port=443): Failed to resolve "
    "'oauth2.googleapis.com' ([Errno 8] nodename nor servname provided, or not known"
)
CANVAS_OFFLINE = "ConnectError: [Errno 8] nodename nor servname provided, or not known"


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


class TestGlassBox:
    @pytest.mark.parametrize(
        "error",
        [
            GOOGLE_OFFLINE,
            CANVAS_OFFLINE,
            "ConnectionError: [Errno -3] Temporary failure in name resolution",  # Linux
            "URLError: <urlopen error [Errno 11001] getaddrinfo failed>",  # Windows
            "OSError: [Errno 51] Network is unreachable",
            "OSError: [Errno 65] No route to host",
        ],
    )
    def test_ways_of_having_no_internet(self, error: str) -> None:
        assert is_offline(error)
        assert why(error) == "Friday can't reach the internet. It reads again once you're back online."

    @pytest.mark.parametrize(
        "error", ["HttpError 503: backend error", "TimeoutError: timed out", "HTTPStatusError: 404 Not Found", None, ""]
    )
    def test_a_server_that_answers_or_is_slow_is_not_offline(self, error: str | None) -> None:
        assert not is_offline(error)

    def test_an_expired_sign_in_stays_a_sign_in_even_offline_looking(self) -> None:
        assert not is_offline(GOOGLE_SAYS + " Errno 8") and why(GOOGLE_SAYS) == PLAIN

    def test_the_web_app_tests_the_same_words(self) -> None:
        web = (REPO / "web/src/settings/GoogleConnect.tsx").read_text()
        found = re.search(r"return /(.+)/i\.test\(error \?\? \"\"\) && !wantsSignIn", web)
        assert found is not None and found.group(1) == OFFLINE.pattern


class TestBlackBox:
    def test_four_sources_offline_are_one_line_naming_them(self, app: App) -> None:
        for name in ("student@school.edu", "Gmail", "Gmail (ruben@example.com)"):
            failed(app, name, GOOGLE_OFFLINE, FAILURES_FOR_BANNER)
        failed(app, "canvas", CANVAS_OFFLINE, FAILURES_FOR_BANNER + 4)
        assert failing_sources(app.conn, 1) == [
            "Friday can't reach the internet, so student@school.edu, Gmail, Gmail (ruben@example.com) and canvas "
            "weren't read. It keeps planning with what it has and reads again once you're back online."
        ]

    def test_one_offline_and_one_broken_are_said_apart(self, app: App) -> None:
        failed(app, "canvas", CANVAS_OFFLINE, FAILURES_FOR_BANNER)
        failed(app, "Gmail", "HttpError 503: backend error", FAILURES_FOR_BANNER)
        offline, broken = failing_sources(app.conn, 1)
        assert offline.startswith("Friday can't reach the internet, so canvas wasn't read.")
        assert broken == "Gmail can't be read: HttpError 503: backend error"
        assert "Errno" not in offline and "nodename" not in offline

    def test_a_short_spell_offline_is_no_banner(self, app: App) -> None:
        failed(app, "canvas", CANVAS_OFFLINE, FAILURES_FOR_BANNER - 1)
        assert failing_sources(app.conn, 1) == []


class TestTheSystem:
    def test_a_calendar_link_with_no_way_to_its_server_reaches_status_in_words(self, app: App) -> None:
        """The sync job's own fetch, failing as httpx does with no DNS, three times, then the banner it sets."""
        from friday.commands import fetching
        from friday.server.worker import set_problem

        def no_dns(url: str) -> str:
            return httpx.Client(transport=httpx.MockTransport(refused)).get(url).text

        def refused(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("[Errno 8] nodename nor servname provided, or not known", request=request)

        app.do("source_add", kind="ics", name="canvas", url="https://canvas.example.edu/feed.ics")
        for day in range(FAILURES_FOR_BANNER):
            fetching.sync(app.conn, app.now_utc + day * 1440, 1, fetch=no_dns)
        set_problem(app.conn, 1, "sources", "; ".join(failing_sources(app.conn, 1)) or None)
        (said,) = [p for p in app.do("status")["problems"] if "canvas" in p]
        assert said.startswith("Friday can't reach the internet, so canvas wasn't read.")
