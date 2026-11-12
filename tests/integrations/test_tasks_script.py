"""Google Tasks through your own script (C130): each way setting it up can go wrong is said with what to do, in words
that name the step; nothing is connected until the script answers with its key; once connected it reads and ticks."""

from pathlib import Path

import httpx
import pytest

from friday.core.items import FieldError
from friday.integrations import sync
from friday.integrations.base import ConnectorError
from friday.integrations.google_tasks import GoogleTasks
from friday.planner.store import load_settings
from tests.commands.helpers import App, new_app
from tests.integrations.fake_tasks_script import ACCOUNT, HARNESS, KEY, LINK, FakeTasksScript


@pytest.fixture
def fake() -> FakeTasksScript:
    fake = FakeTasksScript(HARNESS.token)
    fake.add("Buy milk", "2026-10-22", in_list="MDI")
    return fake


@pytest.fixture
def app(tmp_path: Path, fake: FakeTasksScript, monkeypatch: pytest.MonkeyPatch) -> App:
    monkeypatch.setitem(sync.TRANSPORTS, "google_tasks", fake.transport)
    return new_app(tmp_path)


def refused(fake: FakeTasksScript, token: str) -> ConnectorError:
    with pytest.raises(ConnectorError) as error:
        GoogleTasks(token, {}, fake.transport).check()
    return error.value


def test_connected_with_the_link_and_key_it_reads_every_list_and_ticks_back(app: App, fake: FakeTasksScript) -> None:
    out = app.do("integration_connect", kind="google_tasks", token=HARNESS.token, fields={})
    assert f"Google Tasks connected ({ACCOUNT})" in out["message"]
    sync.sync_all(app.conn, load_settings(app.conn), app.now_utc, asked=True)
    (source,) = app.table("sources")
    assert '"via": "script"' in source["config"] and KEY not in source["config"] and LINK not in source["config"]
    (raw,) = app.table("raw_inputs")
    assert raw["title"] == "Buy milk"
    assert {r.url.host for r in fake.requests} == {"script.google.com", "script.googleusercontent.com"}
    assert all(r.url.path.endswith("/exec") for r in fake.requests if r.method == "POST"), "posted to /exec/"


def test_a_link_that_isnt_the_scripts_is_refused_before_anything_is_sent(fake: FakeTasksScript) -> None:
    for wrong in ("https://docs.google.com/document/d/abc/edit#k", "script.google.com/macros/s/x/exec#k", f"{LINK}x#k"):
        assert "isn't a Google Apps Script Web app link" in str(refused(fake, wrong))
    assert "test link" in str(refused(fake, LINK.replace("/exec", "/dev") + "#k"))
    assert "key is missing" in str(refused(fake, LINK))
    assert fake.requests == []


def test_a_workspace_accounts_link_and_a_pasted_query_are_taken(fake: FakeTasksScript) -> None:
    workspace = "https://script.google.com/a/macros/cornell.edu/s/AKfycbz-stand-in-deployment-id_0123456789/exec"
    assert GoogleTasks(f"{workspace}#{KEY}", {}).script is not None
    assert GoogleTasks(f" {LINK}?usp=sharing#{KEY} ", {}, fake.transport).check() == ACCOUNT


def test_a_script_made_for_another_friday_says_copy_it_again(fake: FakeTasksScript) -> None:
    said = str(refused(fake, f"{LINK}#another-key"))
    assert "copy the script from Friday's Google Tasks box again" in said and "New version" in said
    assert "another-key" not in said and KEY not in said


def test_the_tasks_service_not_added_says_where_to_add_it(fake: FakeTasksScript) -> None:
    fake.tasks_service = False
    error = refused(fake, HARNESS.token)
    assert error.problem == "access" and "Services press +, add Google Tasks API" in str(error)


def test_a_deployment_not_open_to_anyone_says_who_has_access(fake: FakeTasksScript) -> None:
    fake.access = "google"
    assert "Who has access to Anyone" in str(refused(fake, HARNESS.token))
    fake.access = "anyone"
    fake.fail_next(403)
    assert "Who has access: Anyone" in str(refused(fake, HARNESS.token))


def test_a_link_google_has_no_script_at_says_copy_it_again(fake: FakeTasksScript) -> None:
    gone = LINK.replace("0123456789", "9999999999")
    assert "no script at that link" in str(refused(fake, f"{gone}#{KEY}"))


def test_a_web_page_instead_of_the_scripts_answer_is_said_not_misread() -> None:
    page = httpx.MockTransport(lambda r: httpx.Response(200, text="<html>Authorization is required</html>"))
    with pytest.raises(ConnectorError, match="answered with a web page") as error:
        GoogleTasks(HARNESS.token, {}, page).check()
    assert error.value.problem == "token"


def test_a_refused_link_is_never_kept(app: App, fake: FakeTasksScript) -> None:
    with pytest.raises(FieldError, match="isn't this Friday's"):
        app.do("integration_connect", kind="google_tasks", token=f"{LINK}#wrong", fields={})
    assert app.table("sources") == []
    dump = "\n".join(app.conn.iterdump())
    assert LINK not in dump and "#wrong" not in dump


def test_the_sign_in_way_still_reads_with_a_google_account() -> None:
    assert GoogleTasks("", {"account": ACCOUNT}).script is None


@pytest.mark.parametrize(("answer", "words"), [
    (["ok"], "The script answered in a shape Friday doesn't know"),
    ({"error": "op"}, "The script is older than this Friday: copy it again"),
    ({"error": "Exception: Service invoked too many times for one day: tasks."}, "The script said: Exception: Ser"),
])  # fmt: skip
def test_what_the_script_says_that_isnt_its_answer_is_said_in_words(
    fake: FakeTasksScript, answer: object, words: str
) -> None:
    fake.answer = lambda ask: answer  # type: ignore[method-assign]
    error = refused(fake, HARNESS.token)
    assert error.problem == "answer" and words in str(error)


def test_a_read_without_its_lists_is_said_not_taken_as_nothing_open(fake: FakeTasksScript) -> None:
    fake.answer = lambda ask: {"ok": True, "v": 1, "lists": None}  # type: ignore[method-assign]
    with pytest.raises(ConnectorError, match="answered in a shape Friday doesn't know") as said:
        GoogleTasks(HARNESS.token, {}, fake.transport).read()
    assert said.value.problem == "answer"
