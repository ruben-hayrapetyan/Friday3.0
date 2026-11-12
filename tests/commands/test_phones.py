"""Phones (commands/phones.py) at the edges: a code needs this Mac on Tailscale, two
phones of one name are told apart, a phone that isn't paired can't be removed, and a pairing that fails partway
leaves nothing changed. Tailscale is a stand-in."""

import sqlite3
from pathlib import Path

import pytest

from friday.commands import phones
from friday.core.items import FieldError
from friday.sync import tailnet
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> App:
    monkeypatch.setattr(tailnet, "address", lambda *_: "100.64.0.1")
    monkeypatch.setattr(tailnet, "name", lambda *_: "mac.example.ts.net")
    app = new_app(tmp_path)
    app.do("phone_set", on=True)
    return app


def code(app: App) -> str:
    return app.do("phone_pair")["url"].split("#", 1)[1]


def test_a_code_needs_this_mac_on_tailscale(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tailnet, "address", lambda *_: None)
    monkeypatch.setattr(tailnet, "name", lambda *_: None)
    with pytest.raises(FieldError, match="isn't on Tailscale right now"):
        app.do("phone_pair")


def test_two_phones_of_one_name_are_told_apart(app: App) -> None:
    assert phones.pair(app.conn, 1, code(app), "iPhone", app.now_utc)
    assert phones.pair(app.conn, 1, code(app), "iPhone", app.now_utc)
    assert sorted(p["name"] for p in app.do("phone_status")["phones"]) == ["iPhone", "iPhone 2"]


def test_a_phone_that_isnt_paired_cant_be_removed(app: App) -> None:
    with pytest.raises(FieldError, match="That phone isn't paired any more"):
        app.do("phone_forget", id="nope")


def test_a_pairing_that_fails_partway_changes_nothing(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    given = code(app)
    before = app.table("kv")

    def broken(conn: sqlite3.Connection, user_id: int, key: str, value: dict) -> None:
        conn.execute("DELETE FROM kv WHERE key = 'phone_codes'")
        raise RuntimeError("disk full")

    monkeypatch.setattr(phones, "store", broken)
    with pytest.raises(RuntimeError, match="disk full"):
        phones.pair(app.conn, 1, given, "iPhone", app.now_utc)
    assert app.table("kv") == before  # the code is still there to use


def test_pairing_inside_a_transaction_already_open_uses_that_one(app: App) -> None:
    given = code(app)
    app.conn.execute("BEGIN")
    assert phones.pair(app.conn, 1, given, "iPad", app.now_utc)
    app.conn.execute("ROLLBACK")  # the transaction it was part of decides: taken back, it never paired
    assert app.do("phone_status")["phones"] == []
