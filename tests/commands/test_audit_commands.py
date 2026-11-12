"""Bugs the audit of 12 Nov found in the commands, each kept fixed: a pace until a day gone by, a "never" rule's
hours past midnight and a day's pace read from the UTC date, a revoked token or a used pairing code written back by a
request reading them a moment before, forgetting one mailbox switching off another whose address ends the same, a
broken Chroma file or calendar date as a crash, a default pace that isn't saved, a rule about two kinds not keeping
either, and a retried request with the same idempotency key, or a full preview that failed, said as a database
error."""

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from friday.commands import learned, phones, refit, registry, tokens
from friday.commands.registry import Ctx, run
from friday.commands.writer import Writer
from friday.core.db import connect
from friday.core.items import FieldError
from friday.planner.store import load_settings
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def ctx_of(app: App) -> Ctx:
    return Ctx(app.conn, Writer(app.conn, 1), app.now_utc, "you", 1, load_settings(app.conn, 1))


def test_a_pace_until_a_day_gone_by_is_said_not_a_crash(app: App) -> None:
    with pytest.raises(FieldError, match="before today") as error:
        app.do("pace", capacity=0.5, until="2026-10-01")
    assert error.value.field == "until"


def test_work_past_midnight_inside_a_never_rule_is_asked_about(app: App) -> None:
    app.do("rule_add", text="no work after 11pm", strength="Always")
    essay = app.do("add", title="Essay", duration_min=120)["item"]["id"]
    app.at("2026-10-21T09:00")
    app.do("log", id=essay, start="2026-10-19T23:30", end="2026-10-20T00:30")
    assert refit.forbidden_work(ctx_of(app), {"decided": {}}) == "you:no-work-after-11pm"


def test_work_on_a_day_a_never_rule_leaves_out_isnt_asked_about(app: App) -> None:
    rules = app.do("settings")["rules"] + [{"name": "weekends-only", "type": "time_preference", "weight": 1.0,
                                           "params": {"days_except": ["sat", "sun"], "price": "forbid"}}]  # fmt: skip
    app.do("settings_set", key="rules", value=rules)
    essay = app.do("add", title="Essay", duration_min=120)["item"]["id"]
    app.at("2026-10-26T09:00")
    app.do("log", id=essay, start="2026-10-24T10:00", end="2026-10-24T11:00")  # a Saturday: allowed
    assert refit.forbidden_work(ctx_of(app), {"decided": {}}) is None
    app.do("log", id=essay, start="2026-10-21T10:00", end="2026-10-21T11:00")  # a Wednesday: not
    assert refit.forbidden_work(ctx_of(app), {"decided": {}}) == "weekends-only"


def test_why_names_the_pace_of_the_evening_a_block_is_in(app: App) -> None:
    essay = app.do("add", title="Essay", duration_min=60)["item"]["id"]
    app.do("pin", id=essay, start="2026-10-19T21:00", kind="locked")  # 1am the next day in UTC
    app.do("pace", name="easy", for_days=1)
    app.do("replan")
    key = next(b["key"] for b in app.do("plan")["blocks"] if b["item_id"] == essay)
    assert app.do("why", key=key)["sentence"].endswith("Easy pace that day.")


def test_a_token_revoked_while_a_request_reads_the_tokens_stays_revoked(
    app: App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made = app.do("token_add", name="helper", scope="read-write")["token"]
    other = connect(tmp_path / "friday.db")
    other.execute("PRAGMA busy_timeout = 0")
    tried: list[bool] = []
    waiting: list[bool] = []
    read = tokens.saved

    def saved_then_revoked(conn: sqlite3.Connection, user_id: int) -> dict:
        found = read(conn, user_id)
        if conn is app.conn and not tried:
            tried.append(True)
            try:  # the revoke from Settings, a moment after this request read the tokens
                run(other, "token_remove", {"name": "helper"}, now_utc=app.now_utc, provisional=False)
            except sqlite3.OperationalError:  # it waits for the lock instead
                waiting.append(True)
        return found

    monkeypatch.setattr(tokens, "saved", saved_then_revoked)
    tokens.agent(app.conn, 1, made, app.now_utc)
    monkeypatch.setattr(tokens, "saved", read)
    if waiting:
        run(other, "token_remove", {"name": "helper"}, now_utc=app.now_utc, provisional=False)
    assert tokens.agent(app.conn, 1, made, app.now_utc) is None


def test_a_pairing_code_used_while_another_is_made_works_once(
    app: App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.do("phone_set", on=True)
    monkeypatch.setattr("friday.sync.tailnet.name", lambda: "mac.tailnet.ts.net")
    monkeypatch.setattr("friday.sync.tailnet.address", lambda: "100.64.0.1")
    first = app.do("phone_pair")["url"].split("#")[1]
    other = connect(tmp_path / "friday.db")
    other.execute("PRAGMA busy_timeout = 0")
    used: list[str | None] = []
    read = phones.stored

    def stored_then_used(conn: sqlite3.Connection, user_id: int, key: str) -> dict:
        found = read(conn, user_id, key)
        if key == "phone_codes" and conn is app.conn and not used:  # the phone scans it as the Mac makes another
            used.append(None)
            try:
                used[0] = phones.pair(other, 1, first, "iPhone", app.now_utc)
            except sqlite3.OperationalError:
                used[0] = "waiting"
        return found

    monkeypatch.setattr(phones, "stored", stored_then_used)
    app.do("phone_pair")
    monkeypatch.setattr(phones, "stored", read)
    if used == ["waiting"]:
        assert phones.pair(other, 1, first, "iPhone", app.now_utc) is not None
    assert phones.pair(app.conn, 1, first, "iPad", app.now_utc) is None, "the code worked a second time"


def test_forgetting_one_mailbox_leaves_one_whose_address_ends_the_same(app: App, no_personal_config: Path) -> None:
    (no_personal_config / "secrets.toml").write_text(
        '[gmail_app]\naddress = "bob@gmail.com"\npassword = "abcdefghijklmnop"\n'
        '[gmail_app_2]\naddress = "jimbob@gmail.com"\npassword = "abcdefghijklmnop"\n'
        '[mail_app]\nprovider = "icloud"\naddress = "bob@icloud.com"\npassword = "x"\n'
        '[mail_app_2]\nprovider = "icloud"\naddress = "jimbob@icloud.com"\npassword = "x"\n'
    )
    for kind, account in [("gmail", "bob@gmail.com"), ("gmail", "jimbob@gmail.com"), ("mail", "bob@icloud.com"),
                          ("mail", "jimbob@icloud.com")]:  # fmt: skip
        app.conn.execute(
            "INSERT INTO sources (user_id, kind, name, config) VALUES (1, ?, ?, ?)",
            [kind, account, f'{{"account": "{account}"}}'],
        )
    app.do("gmail_app_set", address="bob@gmail.com", password="")
    app.do("mail_app_forget", address="bob@icloud.com")
    assert {r["name"]: r["enabled"] for r in app.table("sources")} == {
        "bob@gmail.com": 0, "jimbob@gmail.com": 1, "bob@icloud.com": 0, "jimbob@icloud.com": 1,
    }  # fmt: skip


def test_a_chroma_colours_file_that_isnt_one_is_said(app: App, tmp_path: Path) -> None:
    broken, listed = tmp_path / "colors.json", tmp_path / "list.json"
    broken.write_text("{not json")
    listed.write_text("[1, 2]")
    for path in (broken, listed):
        with pytest.raises(FieldError, match="isn't the file that app keeps") as error:
            app.do("import_chroma_colors", colors_path=str(path))
        assert error.value.field == "colors_path"
    with pytest.raises(FieldError, match="isn't the file that app keeps") as error:
        app.do("import_personal", todos_path=str(tmp_path / "none.json"), categories_path=str(listed))
    assert error.value.field == "categories_path"


def test_a_calendar_from_a_day_that_isnt_one_is_said(app: App) -> None:
    with pytest.raises(FieldError) as error:
        app.do("calendar", start="2026-13-01")
    assert error.value.field == "start"


def test_a_rule_about_two_kinds_keeps_both(app: App) -> None:
    app.do("rule_add", text="no errands or chores after 8pm")
    with pytest.raises(FieldError, match="rule"):
        app.do("kind_remove", name="Chore", move_to="Errand")


def test_a_request_retried_with_its_key_while_the_first_runs_gets_the_first_answer(
    app: App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = connect(tmp_path / "friday.db")
    first: list[int | None] = []
    take = registry.begin_write

    def first_one_finishes_meanwhile(conn: sqlite3.Connection, who: str) -> None:
        if not first:  # the first request, still running when its retry checked the key, finishes
            monkeypatch.setattr(registry, "begin_write", take)
            done = run(other, "add", {"title": "Essay"}, now_utc=app.now_utc, idempotency_key="k1", provisional=False)
            first.append(done.command_id)
        take(conn, who)

    monkeypatch.setattr(registry, "begin_write", first_one_finishes_meanwhile)
    again = app.full("add", payload={"title": "Essay"}, idempotency_key="k1", provisional=False)
    assert again.repeated and again.command_id == first[0]
    assert [i["title"] for i in app.table("items")] == ["Essay"]


def test_a_full_preview_that_fails_says_why(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    def fails(*args: object) -> None:
        raise FieldError("preview", "that can't be worked out")

    monkeypatch.setattr(registry, "full_preview", fails)
    with pytest.raises(FieldError, match="can't be worked out"):
        app.full("add", payload={"title": "Essay"}, preview="full")
    assert app.table("items") == []


def test_the_default_pace_is_one_you_saved(app: App) -> None:
    with pytest.raises(FieldError, match="isn't one of your saved paces"):
        app.do("settings_set", key="pace", value={"default": "Gone"})
    paces = {k: v for k, v in app.do("settings")["paces"].items() if k != "Normal"}
    with pytest.raises(FieldError, match="isn't one of your saved paces"):
        app.do("settings_set", key="paces", value=paces)


def test_a_default_pace_friday_toml_names_but_doesnt_save_is_the_usual_dials(app: App) -> None:
    gone = {"key": "pace", "value": {"default": "Gone"}}
    run(app.conn, "settings_set", gone, now_utc=app.now_utc, actor="config", provisional=False)
    is_default = learned.default_pace_days(app.conn, load_settings(app.conn, 1), 1)
    assert is_default(date(2026, 10, 19))
