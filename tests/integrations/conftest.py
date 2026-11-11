import pytest


@pytest.fixture(autouse=True)
def friday_app_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    """Friday's own app ids at the services, as a release carries them (Microsoft's app id…)."""
    monkeypatch.setenv("FRIDAY_MS_CLIENT_ID", "00000000-f00d-4000-8000-000000000001")  # Friday's Entra app, in tests
