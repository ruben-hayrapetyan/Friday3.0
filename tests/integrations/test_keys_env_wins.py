"""An app key set in the environment wins, even set empty: empty means "not registered in this copy" (24 Nov: tests
that unregister an app with FRIDAY_<NAME>="" passed in a fresh checkout and failed beside a real Mac/app_keys.json,
whose value an empty variable fell through to)."""

import pytest

from friday.integrations import keys


def test_a_key_set_empty_in_the_environment_is_not_taken_from_the_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(keys, "kept", lambda: {"trello_client_id": "from-the-file"})
    monkeypatch.setenv("FRIDAY_TRELLO_CLIENT_ID", "")
    assert keys.get("trello_client_id") == ""


def test_unset_it_comes_from_the_file_and_set_it_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(keys, "kept", lambda: {"trello_client_id": "from-the-file"})
    monkeypatch.delenv("FRIDAY_TRELLO_CLIENT_ID", raising=False)
    assert keys.get("trello_client_id") == "from-the-file"
    monkeypatch.setenv("FRIDAY_TRELLO_CLIENT_ID", " from-the-env ")
    assert keys.get("trello_client_id") == "from-the-env"
