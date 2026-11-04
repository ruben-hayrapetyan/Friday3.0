"""A Google sign-in Google no longer takes, said as what to do (2 Nov: the banner read "Gmail (…) can't be read:
RefreshError: ('invalid_grant: Token has been expired or revoked.', …)"). The source keeps Google's own words, which
the Integrations page reads to offer "Connect again"; the banner says it in plain words."""

import re
from pathlib import Path

import pytest
from google.auth.exceptions import RefreshError

from friday.commands import fetching
from friday.commands.fetching import FAILURES_FOR_BANNER, SIGN_IN_GONE, failing_sources, why
from friday.commands.mail import read_mail
from friday.planner.store import load_settings
from friday.server.worker import set_problem
from tests.commands.helpers import App, new_app

REPO = Path(__file__).resolve().parents[2]
GOOGLE_SAYS = "RefreshError: ('invalid_grant: Token has been expired or revoked.', {'error': 'invalid_grant'})"
PLAIN = "Google's sign-in for it expired or was taken back. Connect it again in Settings → Integrations."


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def failed(app: App, name: str, error: str, times: int) -> None:
    app.conn.execute(
        "INSERT INTO sources (user_id, kind, name, config, last_error, failures) VALUES (1, 'gmail', ?, '{}', ?, ?)",
        [name, error, times],
    )


class TestGlassBox:
    @pytest.mark.parametrize(
        "error",
        [
            GOOGLE_SAYS,
            "RefreshError: something else",
            "invalid_grant",
            "Request had INSUFFICIENT AUTHENTICATION scopes",
        ],
    )
    def test_each_of_google_s_ways_of_saying_it_is_read_as_a_sign_in_gone(self, error: str) -> None:
        assert why(error) == PLAIN

    @pytest.mark.parametrize("error", ["HttpError 503: backend error", "TimeoutError: timed out", "grant denied"])
    def test_other_errors_keep_their_words(self, error: str) -> None:
        assert why(error) == error

    def test_no_reason_is_still_a_sentence(self) -> None:
        assert why(None) == why("") == "it failed, with no reason given"

    def test_the_pattern_is_the_web_app_s_so_the_banner_and_connect_again_agree(self) -> None:
        web = (REPO / "web/src/settings/GoogleConnect.tsx").read_text()
        found = re.search(r"return /(.+)/i\.test\(error", web)
        assert found is not None and found.group(1) == SIGN_IN_GONE.pattern


class TestBlackBox:
    def test_an_expired_sign_in_is_said_plainly_with_where_to_fix_it(self, app: App) -> None:
        failed(app, "Gmail (me@example.com)", GOOGLE_SAYS, 5)
        (said,) = failing_sources(app.conn, 1)
        assert said == f"Gmail (me@example.com) can't be read: {PLAIN}"
        assert "RefreshError" not in said and "invalid_grant" not in said

    def test_other_failures_still_say_google_s_reason(self, app: App) -> None:
        failed(app, "Gmail", "HttpError 503: backend error", FAILURES_FOR_BANNER)
        assert failing_sources(app.conn, 1) == ["Gmail can't be read: HttpError 503: backend error"]

    def test_a_failure_or_two_is_no_banner_yet(self, app: App) -> None:
        failed(app, "Gmail", GOOGLE_SAYS, FAILURES_FOR_BANNER - 1)
        assert failing_sources(app.conn, 1) == []


class TestTheSystem:
    def test_gmail_refusing_the_sign_in_reaches_the_banner_in_words_and_settings_keep_google_s(self, app: App) -> None:
        """Google's own exception from reading mail, as the job reads it, through to `status` and Integrations."""

        def refused() -> None:
            raise RefreshError("invalid_grant: Token has been expired or revoked.", {"error": "invalid_grant"})

        for _ in range(FAILURES_FOR_BANNER):
            assert read_mail(app.conn, load_settings(app.conn, 1), app.now_utc, 1, refused, "me@example.com") == 0
        set_problem(app.conn, 1, "sources", "; ".join(fetching.failing_sources(app.conn, 1)) or None)
        problems = app.do("status")["problems"]
        assert any(p == f"Gmail can't be read: {PLAIN}" for p in problems), problems
        stored = app.conn.execute("SELECT last_error FROM sources WHERE kind = 'gmail'").fetchone()["last_error"]
        assert stored.startswith("RefreshError:") and SIGN_IN_GONE.search(stored)  # what "Connect again" looks for
