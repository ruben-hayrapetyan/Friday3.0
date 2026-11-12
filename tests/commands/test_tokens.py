"""Tokens for an assistant (MCP) or a script: made once by name, shown once, and revoked by name."""

from pathlib import Path

import pytest

from friday.core.items import FieldError
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def test_a_token_is_made_once_per_name(app: App) -> None:
    made = app.do("token_add", name="claude")
    assert made["name"] == "claude" and made["token"].startswith("fr_")
    with pytest.raises(FieldError, match="there is already a token named claude"):
        app.do("token_add", name="claude")


def test_only_a_token_you_have_can_be_revoked(app: App) -> None:
    app.do("token_add", name="claude")
    app.do("token_remove", name="claude")
    with pytest.raises(FieldError, match="no token named claude"):
        app.do("token_remove", name="claude")
