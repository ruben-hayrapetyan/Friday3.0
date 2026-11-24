"""Tokens for assistants and scripts (tests/features.toml: tokens), the whole pipeline: a real `fridayd serve`, each
token made, listed and revoked over HTTP as Settings → Tokens does, and the token itself then used as a bearer token
on the same HTTP API: what it may read, what it may change (its scope), what it is never let do (YOURS_ONLY), and that
a revoked one is refused."""

from collections.abc import Iterator

import pytest

from tests.system.test_beat_plan_system import Friday


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("tokens"))
    yield server
    server.stop()


def bearer(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}"}


def names(friday: Friday) -> dict[str, dict]:
    return {t["name"]: t for t in friday.q("tokens")}


def test_a_new_friday_has_no_tokens(friday: Friday) -> None:
    assert friday.q("tokens") == []


def test_token_add_shows_the_token_once_and_lists_it_without_it(friday: Friday) -> None:
    made = friday.c("token_add", name="reader")
    assert made["name"] == "reader" and made["scope"] == "read"  # read is the default scope
    assert made["token"].startswith("fr_") and len(made["token"]) > 20
    listed = names(friday)["reader"]
    assert listed["scope"] == "read" and listed["last_used"] is None and listed["created"]
    assert made["token"] not in friday.http.get("/api/q/tokens").text  # never shown again
    # and never kept in the command log either (unlogged: the log keeps every result)
    assert all(e["command"] != "token_add" for e in friday.q("log_list", limit=50))


def test_two_tokens_are_different_secrets(friday: Friday) -> None:
    one = friday.c("token_add", name="script-a", scope="read-write")["token"]
    two = friday.c("token_add", name="script-b", scope="read-write")["token"]
    assert one != two
    assert {n: t["scope"] for n, t in names(friday).items() if n.startswith("script-")} == {
        "script-a": "read-write",
        "script-b": "read-write",
    }


def test_a_name_already_taken_is_refused_and_the_first_token_still_works(friday: Friday) -> None:
    first = friday.c("token_add", name="twice")["token"]
    answer = friday.http.post("/api/c/token_add", json={"name": "twice", "scope": "read-write"})
    assert answer.status_code == 422
    assert answer.json() == {"field": "name", "message": "name: there is already a token named twice"}
    assert names(friday)["twice"]["scope"] == "read"  # not overwritten
    assert friday.http.get("/api/q/status", headers=bearer(first)).status_code == 200


@pytest.mark.parametrize(
    ("body", "field"),
    [({"name": ""}, "name"), ({"name": "x" * 41}, "name"), ({"name": "admin", "scope": "everything"}, "scope")],
)
def test_token_add_refuses_a_bad_name_or_scope(friday: Friday, body: dict, field: str) -> None:
    answer = friday.http.post("/api/c/token_add", json=body)
    assert answer.status_code == 422  # the request's own check: FastAPI's list of what's wrong, by where
    assert [e["loc"][-1] for e in answer.json()["detail"]] == [field]
    assert body["name"] not in names(friday)


def test_a_read_token_reads_and_is_noted_as_used_but_cant_change_anything(friday: Friday) -> None:
    token = friday.c("token_add", name="viewer")["token"]
    friday.c("add", title="Seen by the viewer", duration_min=30)
    items = friday.http.get("/api/q/items", headers=bearer(token))
    assert items.status_code == 200 and "Seen by the viewer" in {i["title"] for i in items.json()}
    assert names(friday)["viewer"]["last_used"] is not None
    answer = friday.http.post("/api/c/add", json={"title": "Added by the viewer"}, headers=bearer(token))
    assert answer.status_code == 403 and "can only read" in answer.text
    assert "Added by the viewer" not in {i["title"] for i in friday.q("items")}


def test_a_read_write_token_changes_the_plan_as_the_assistant(friday: Friday) -> None:
    token = friday.c("token_add", name="helper", scope="read-write")["token"]
    answer = friday.http.post("/api/c/add", json={"title": "Added by the helper", "duration_min": 20},
                              headers=bearer(token))  # fmt: skip
    assert answer.status_code == 200, answer.text
    item = answer.json()["result"]["item"]
    assert friday.q("item", id=item["id"])["item"]["title"] == "Added by the helper"
    logged = next(e for e in friday.q("log_list", item_id=item["id"]) if e["command"] == "add")
    assert logged["actor"] == "mcp:helper"  # acted as the assistant, not as you


@pytest.mark.parametrize(
    ("command", "body", "why"),
    [
        ("token_add", {"name": "sneaky", "scope": "read-write"}, "token_add"),
        ("token_remove", {"name": "reader"}, "token_remove"),
        ("ai_key_set", {"provider": "claude", "key": "sk-nope"}, "ai_key_set"),
        ("settings_set", {"key": "llm", "value": {}}, "the llm setting"),
    ],
)
def test_an_assistant_is_never_let_do_what_is_yours_alone(friday: Friday, command: str, body: dict, why: str) -> None:
    token = friday.c("token_add", name=f"rw-{command}", scope="read-write")["token"]
    before = names(friday)
    answer = friday.http.post(f"/api/c/{command}", json=body, headers=bearer(token))
    assert answer.status_code == 422, answer.text
    assert answer.json() == {
        "field": "command",
        "message": f"command: Only you can do that ({why}), not an assistant: do it in Friday's Settings on your Mac",
    }
    assert set(names(friday)) == set(before)  # no token made or revoked


def test_an_unknown_token_is_refused(friday: Friday) -> None:
    answer = friday.http.get("/api/q/items", headers=bearer("fr_not-a-token-anyone-made"))
    assert answer.status_code == 401 and "unknown token" in answer.text


def test_token_remove_revokes_it_at_once(friday: Friday) -> None:
    token = friday.c("token_add", name="short-lived", scope="read-write")["token"]
    assert friday.http.get("/api/q/status", headers=bearer(token)).status_code == 200
    said = friday.c("token_remove", name="short-lived")
    assert said["message"] == "Revoked short-lived"
    assert "short-lived" not in names(friday)
    assert friday.http.get("/api/q/status", headers=bearer(token)).status_code == 401
    answer = friday.http.post("/api/c/add", json={"title": "After revoking"}, headers=bearer(token))
    assert answer.status_code == 401
    assert "After revoking" not in {i["title"] for i in friday.q("items")}


def test_token_remove_leaves_the_other_tokens(friday: Friday) -> None:
    keep = friday.c("token_add", name="keeper")["token"]
    friday.c("token_add", name="goner")
    friday.c("token_remove", name="goner")
    assert "keeper" in names(friday) and "goner" not in names(friday)
    assert friday.http.get("/api/q/status", headers=bearer(keep)).status_code == 200


def test_token_remove_of_a_name_that_isnt_there_is_refused(friday: Friday) -> None:
    before = names(friday)
    answer = friday.http.post("/api/c/token_remove", json={"name": "nobody"})
    assert answer.status_code == 422
    assert answer.json() == {"field": "name", "message": "name: no token named nobody"}
    assert names(friday) == before


def test_a_revoked_name_can_be_made_again_with_a_new_secret(friday: Friday) -> None:
    old = friday.c("token_add", name="again")["token"]
    friday.c("token_remove", name="again")
    new = friday.c("token_add", name="again")["token"]
    assert new != old
    assert friday.http.get("/api/q/status", headers=bearer(old)).status_code == 401
    assert friday.http.get("/api/q/status", headers=bearer(new)).status_code == 200


def test_undo_of_token_remove_brings_it_back(friday: Friday) -> None:
    token = friday.c("token_add", name="undone")["token"]
    friday.c("token_remove", name="undone")
    removed = next(e for e in friday.q("log_list", limit=20) if e["command"] == "token_remove")
    friday.c("undo", command_id=removed["id"])
    assert "undone" in names(friday)
    assert friday.http.get("/api/q/status", headers=bearer(token)).status_code == 200
