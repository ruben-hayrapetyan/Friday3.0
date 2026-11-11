import pytest

from friday.integrations import keys


@pytest.fixture(autouse=True)
def friday_app_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    """Friday's own app ids at the services, stand-ins as a build carries them (integrations/keys.py); your real keys
    file (Mac/app_keys.json) is never read in tests."""
    monkeypatch.setattr(keys, "PLACES", [])
    keys.kept.cache_clear()
    monkeypatch.setenv("FRIDAY_MICROSOFT_CLIENT_ID", "00000000-f00d-4000-8000-000000000001")
    monkeypatch.setenv("FRIDAY_TRELLO_CLIENT_ID", "trello-stand-in-client")
