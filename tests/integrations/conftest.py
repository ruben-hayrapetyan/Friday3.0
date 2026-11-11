import pytest

from tests.integrations.fake_trello import KEY


@pytest.fixture(autouse=True)
def friday_trello_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Friday's Trello app key, as a release carries it (integrations/trello.py APP_KEY)."""
    monkeypatch.setenv("FRIDAY_TRELLO_KEY", KEY)
