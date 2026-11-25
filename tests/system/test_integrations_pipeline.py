"""Other apps through the whole pipeline (24 Nov, the user: every feature tested in every layer): a real `fridayd serve`
with a stand-in Todoist on a real port (FRIDAY_API_TODOIST) and Friday's app registered at Microsoft only
(FRIDAY_MICROSOFT_CLIENT_ID; TickTick's and Trello's not), and each command sent over HTTP as Settings → Integrations
sends it: where a service gives a token or whether it's ready (`integration_token_page`), the service's sign-in page
and the page you come back to (`integration_sign_in`, /oauth/callback), and Disconnect keeping or removing what it
brought in (`integration_disconnect`), read back through `integrations`, `items`, `plan`, and Undo."""

import time
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import pytest

from tests.integrations.fake_todoist import HARNESS, FakeTodoist
from tests.integrations.kit import serve
from tests.system.test_beat_plan_system import TZ, Friday

MICROSOFT_ID = "test-microsoft-app-id"


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Friday, FakeTodoist]]:
    fake = FakeTodoist(HARNESS.token)
    soon = datetime.now(ZoneInfo(TZ)).date() + timedelta(days=3)
    fake.add("Write the grant report", f"{soon}", 120)
    fake.add("Renew passport", f"{soon}T17:00:00")
    address, stop = serve(fake)
    with pytest.MonkeyPatch.context() as env:
        env.setenv("FRIDAY_API_TODOIST", f"{address}/api/v1")
        env.setenv("FRIDAY_MICROSOFT_CLIENT_ID", MICROSOFT_ID)
        for unregistered in ("TICKTICK_CLIENT_ID", "TICKTICK_CLIENT_SECRET", "TRELLO_CLIENT_ID"):
            env.setenv(f"FRIDAY_{unregistered}", "")
        friday = Friday(tmp_path_factory.mktemp("integrations"))
    yield friday, fake
    friday.stop()
    stop()


@pytest.fixture(scope="module")
def friday(world: tuple[Friday, FakeTodoist]) -> Friday:
    return world[0]


def refused(friday: Friday, verb: str, query: bool = False, **body: Any) -> dict:
    answer = friday.http.get(f"/api/q/{verb}", params=body) if query else friday.http.post(f"/api/c/{verb}", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()


def origin(friday: Friday) -> str:
    return f"http://127.0.0.1:{friday.port}"


def items(friday: Friday, *titles: str) -> dict[str, dict]:
    return {i["title"]: i for i in friday.q("items", status="all") if i["title"] in titles}


# Where a token comes from, and whether this copy of Friday can connect it


def test_token_page_says_a_pasted_tokens_service_is_ready(friday: Friday) -> None:
    assert friday.q("integration_token_page", kind="todoist") == {"url": None, "ready": True}


def test_token_page_says_a_sign_in_is_ready_only_with_fridays_app_registered(friday: Friday) -> None:
    assert friday.q("integration_token_page", kind="microsoft_todo")["ready"] is True
    assert friday.q("integration_token_page", kind="ticktick")["ready"] is False
    assert friday.q("integration_token_page", kind="trello")["ready"] is False
    assert (
        friday.q("integration_token_page", kind="outlook_mail")["ready"] is True
    )  # the mailbox signs in at Microsoft too


def test_token_page_refuses_a_service_friday_doesnt_connect_to(friday: Friday) -> None:
    answer = refused(friday, "integration_token_page", query=True, kind="myspace")
    assert answer["field"] == "kind" and answer["message"] == "kind: Friday doesn't connect to “myspace”"


# Signing in on the service's page


def test_sign_in_opens_the_services_page_with_fridays_app_and_this_macs_way_back(friday: Friday) -> None:
    url = friday.c("integration_sign_in", kind="microsoft_todo", origin=origin(friday))["url"]
    assert url.startswith("https://login.microsoftonline.com/common/oauth2/v2.0/authorize?")
    asked = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
    assert asked["client_id"] == MICROSOFT_ID and asked["response_type"] == "code"
    assert asked["redirect_uri"] == f"{origin(friday)}/oauth/callback"
    assert asked["code_challenge_method"] == "S256" and asked["state"]
    again = friday.c("integration_sign_in", kind="microsoft_todo", origin=origin(friday))["url"]
    assert parse_qs(urlsplit(again).query)["state"][0] != asked["state"]  # a fresh page each time
    assert friday.q("integrations") == []  # nothing connected until you're back


def test_sign_in_refuses_a_pasted_token_service_another_origin_and_an_unregistered_app(friday: Friday) -> None:
    said = refused(friday, "integration_sign_in", kind="todoist", origin=origin(friday))
    assert said == {"field": "kind", "message": "kind: todoist isn't connected by signing in"}
    said = refused(friday, "integration_sign_in", kind="microsoft_todo", origin="https://friday.example.com")
    assert said == {"field": "origin", "message": "origin: Sign in from Friday on this Mac"}
    said = refused(friday, "integration_sign_in", kind="ticktick", origin=origin(friday))
    assert "TickTick isn't ready in this copy of Friday yet" in said["message"]


def test_coming_back_from_a_sign_in_you_said_no_to_connects_nothing(friday: Friday) -> None:
    url = friday.c("integration_sign_in", kind="microsoft_todo", origin=origin(friday))["url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    back = friday.http.get("/oauth/callback", params={"state": state, "error": "access_denied"})
    assert back.status_code == 400 and "Not connected" in back.text
    assert "Microsoft To Do didn&#x27;t connect: you said no" in back.text
    used = friday.http.get("/oauth/callback", params={"state": state, "code": "a-code"})  # that page is done with
    assert used.status_code == 400 and "too old or was used already" in used.text
    assert friday.q("integrations") == []


# Disconnecting


@pytest.fixture(scope="module")
def todoist(world: tuple[Friday, FakeTodoist]) -> dict:
    """Todoist connected and its first read accepted from the Inbox: its two to-dos in Friday."""
    friday, _ = world
    connected = friday.c("integration_connect", kind="todoist", token=HARNESS.token)["source"]
    batch = friday.until(lambda: next((s["batch"] for s in friday.q("inbox")["suggestions"]
                                       if (s.get("batch") or "").startswith("integration:")), None))  # fmt: skip
    friday.c("batch_accept", batch=batch)
    assert set(items(friday, "Write the grant report", "Renew passport")) == {
        "Write the grant report",
        "Renew passport",
    }
    return connected


def test_disconnect_and_remove_drops_what_it_brought_and_undo_brings_it_back(friday: Friday, todoist: dict) -> None:
    (row,) = friday.q("integrations")
    assert row["id"] == todoist["id"] and row["made"] == 2
    answer = friday.http.post("/api/c/integration_disconnect", json={"id": todoist["id"], "keep": False})
    assert answer.status_code == 200, answer.text
    assert friday.q("integrations") == []
    brought = items(friday, "Write the grant report", "Renew passport")
    assert {i["status"] for i in brought.values()} == {"dropped"}
    assert not {b["item_id"] for b in friday.q("plan")["blocks"]} & {i["id"] for i in brought.values()}
    friday.c("undo", command_id=answer.json()["command_id"])  # one undo: the to-dos and the connection
    assert {i["status"] for i in items(friday, "Write the grant report", "Renew passport").values()} == {"todo"}
    assert [c["id"] for c in friday.q("integrations")] == [todoist["id"]]


# 24 Nov: this test found that Undo brought the connection back without its token (forgotten at disconnect, and a
# secret Undo can't bring back); your answer, "Ask to sign in again": the row says so, and signing in again fills in
# that same row, which then reads.
def test_after_undoing_a_disconnect_it_asks_to_sign_in_again_then_reads(
    world: tuple[Friday, FakeTodoist], todoist: dict
) -> None:
    friday, fake = world
    (row,) = friday.q("integrations")
    assert row["needs_sign_in"] is True
    again = friday.c("integration_connect", kind="todoist", token=HARNESS.token)["source"]
    assert again["id"] == todoist["id"] and again["needs_sign_in"] is False  # the same row, not a second
    fake.add("Book the venue", f"{datetime.now(ZoneInfo(TZ)).date() + timedelta(days=4)}", 60)
    friday.c("sync_now")

    def read() -> Any:
        (row,) = friday.q("integrations")
        arrived = "Book the venue" in {s.get("title") for s in friday.q("inbox")["suggestions"]} | {
            i["title"] for i in friday.q("items", status="all")}  # fmt: skip
        return row if row["last_error"] or arrived else None

    row = friday.until(read)
    assert row["last_error"] is None, row["last_error"]


def test_disconnect_and_keep_leaves_its_to_dos_in_friday_and_changes_nothing_there(
    world: tuple[Friday, FakeTodoist], todoist: dict
) -> None:
    friday, fake = world
    gone = friday.c("integration_disconnect", id=todoist["id"], keep=True)
    assert gone["id"] == todoist["id"] and friday.q("integrations") == []
    kept = items(friday, "Write the grant report", "Renew passport")
    assert {i["status"] for i in kept.values()} == {"todo"}
    friday.c("done", id=kept["Renew passport"]["id"])  # done in Friday no longer goes to Todoist
    time.sleep(6)
    task = next(t for t in fake.tasks.values() if t["content"] == "Renew passport")
    assert task["checked"] is False


def test_disconnect_refuses_what_isnt_connected(friday: Friday, todoist: dict) -> None:
    for wrong in (999999, 0, -1):
        said = refused(friday, "integration_disconnect", id=wrong, keep=True)
        assert said == {"field": "id", "message": "id: That integration isn't connected"}
