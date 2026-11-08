"""Birthdays typed as a list into Ask (8 Nov: "all of my friends' birthdays were on the wrong day... i put it in a
string command", and "make sure all of the refinements that we are doing for claude apply to the other model
providers as well"). Asked "Club Bdays: Mira: Feb 1st, Rosa: jan 27, …", the AI made 9:00–9:30am events or
midnight to 11:59pm ones that took their days, and asked again it added them all again (five of Mira's).

Black box through `ask_claude` and `add` as the Ask window runs them, with each provider's own client (Claude's,
OpenAI's and Google's commands, and the chat API the others speak) answering from a stand-in, so the same prompt,
context and checks reach every AI; then the inside. Monday 2026-10-19 in New York."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from friday.commands.claude import SYSTEM, Held, event_key_of, proposals, same_name
from friday.commands.fields import all_day_is_free
from friday.commands.registry import Ctx
from friday.commands.writer import Writer
from friday.ingest import llm
from friday.planner.store import load_settings
from tests.commands.helpers import App, new_app

LIST = "Club Bdays: Mira: Feb 1st, Rosa: jan 27, Remy: November 10"


def birthday(name: str, day: str, end: str | None = None) -> dict[str, Any]:
    after = end or f"{day[:8]}{int(day[8:10]) + 1:02d}T00:00"
    return {"sentence": f"Add {name}'s birthday", "command": "add", "input": {
        "title": f"{name}'s Birthday", "when": "fixed", "start": f"{day}T00:00", "end": after,
        "every": "rrule:FREQ=YEARLY"}}  # fmt: skip


ANSWER = {"reply": "Three birthdays.", "actions": [
    birthday("Mira", "2027-02-01"),
    birthday("Rosa", "2027-01-27"),
    birthday("Remy", "2026-10-22", end="2026-10-22T23:59"),  # as some answers gave it
    birthday("Remy", "2026-10-22"),  # and the same one twice
]}  # fmt: skip


def command_answering(envelope: dict[str, Any], seen: list[str]) -> Any:
    """A provider's command that answers `envelope`, keeping everything it was told."""

    def run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        seen.append(" ".join(args) + "\n" + (kwargs.get("input") or ""))
        if "-o" in args:  # codex writes its last message to a file
            Path(args[args.index("-o") + 1]).write_text(json.dumps(ANSWER))
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(envelope), stderr="")

    return run


def chat_api(seen: list[str], flavor: str) -> llm.OpenAIClient:
    def service(request: httpx.Request) -> httpx.Response:
        seen.append(request.content.decode())
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(ANSWER)}}], "usage": {}})

    return llm.OpenAIClient("https://ai.test/v1", "k", flavor, transport=httpx.MockTransport(service))


PROVIDERS = {
    "claude": lambda seen: llm.CliClient(Path("/bin/claude"), command_answering({"structured_output": ANSWER}, seen)),
    "codex": lambda seen: llm.CodexClient(Path("/bin/codex"), command_answering({}, seen)),
    "agy": lambda seen: llm.GeminiCliClient(Path("/bin/agy"), command_answering({"structured_output": ANSWER}, seen)),
    "gemini": lambda seen: llm.GeminiCliClient(
        Path("/bin/gemini"), command_answering({"response": json.dumps(ANSWER)}, seen)
    ),
    "openai": lambda seen: chat_api(seen, "openai"),
    "others": lambda seen: chat_api(seen, "compatible"),
}


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=4)


def ask(app: App, monkeypatch: pytest.MonkeyPatch, provider: str) -> tuple[dict[str, Any], str]:
    seen: list[str] = []
    monkeypatch.setattr(llm, "client", lambda *_: PROVIDERS[provider](seen))
    return app.do("ask_claude", text=LIST), "\n".join(seen)


def mulan(app: App) -> None:
    app.do("add", **birthday("Mira", "2027-02-01")["input"], after=[], before=[], exceptions=[])


@pytest.mark.parametrize("provider", list(PROVIDERS))
class TestEveryProvider:
    def test_it_is_told_how_a_birthday_is_made_and_what_you_already_have(
        self, app: App, monkeypatch: pytest.MonkeyPatch, provider: str
    ) -> None:
        mulan(app)
        _, told = ask(app, monkeypatch, provider)
        told = told.replace("\\n", "\n").replace('\\"', '"')
        assert 'next day\'s "T00:00"' in told and "rrule:FREQ=YEARLY" in told and "Club Bdays" in told
        assert '"repeating"' in told and "Mira's Birthday" in told and "2027-02-01T00:00" in told
        assert '"weekday": "Monday"' in told

    def test_one_you_have_and_one_proposed_twice_are_refused_the_others_offered(
        self, app: App, monkeypatch: pytest.MonkeyPatch, provider: str
    ) -> None:
        mulan(app)
        out, _ = ask(app, monkeypatch, provider)
        errors = [a["error"] for a in out["actions"]]
        assert errors[0] == "You already have Mira's Birthday then, repeating"
        assert errors[1] is None and errors[2] is None
        assert errors[3] == "Remy's Birthday is proposed twice"


class TestApplied:
    def test_midnight_to_1159pm_is_the_whole_day_and_leaves_it_free(self, app: App) -> None:
        app.do("add", **birthday("Remy", "2026-10-20", end="2026-10-20T23:59")["input"])
        (row,) = [i for i in app.table("items") if i["title"] == "Remy's Birthday"]
        assert app.do("item", id=row["id"])["item"]["end"] == "2026-10-21T00:00" and row["blocks_time"] == 0

    def test_the_same_name_asked_again_another_way_is_still_known(
        self, app: App, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        app.do("add", title="Rosas birthday", when="fixed", start="2026-10-21T00:00", end="2026-10-22T00:00")
        seen: list[str] = []
        monkeypatch.setattr(llm, "client", lambda *_: PROVIDERS["claude"](seen))
        out = app.do("ask_claude", text=LIST)
        assert [a["error"] for a in out["actions"]][:2] == [None, None]  # Rosa's next one is January's
        rachel = birthday("Rosa", "2026-10-21")
        answer = {"reply": "", "actions": [rachel]}
        monkeypatch.setattr(llm, "client", lambda *_: SimpleNamespace(messages=SimpleNamespace(
            create=lambda **_: SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(answer))],
                                               usage=SimpleNamespace(input_tokens=1, output_tokens=1)))))  # fmt: skip
        assert app.do("ask_claude", text="rachel oct 21")["actions"][0]["error"] == (
            "You already have Rosa's Birthday then"
        )

    def test_a_birthday_moved_away_is_not_in_the_way(self, app: App, monkeypatch: pytest.MonkeyPatch) -> None:
        mulan(app)
        series = next(s for s in app.table("series") if "Mira" in s["template"])
        app.do("series_delete", id=series["id"])
        out, _ = ask(app, monkeypatch, "claude")
        assert out["actions"][0]["error"] is None


class TestInside:
    def test_names_match_whatever_their_case_accents_and_punctuation(self) -> None:
        assert same_name("Rosas birthday") == same_name("Rosa's Birthday") == same_name("RACHEL’S  Birthday")
        assert same_name("Rosa's Birthday") != same_name("Remy's Birthday")
        assert same_name("Zoë's party") == same_name("Zoe's Party")

    def test_only_a_new_event_with_a_name_and_start_is_compared(self) -> None:
        assert event_key_of({"title": "Remy", "when": "fixed", "start": "2026-11-10T00:00"})[0] == "ray"
        assert event_key_of({"title": "Essay", "due": "2026-11-10T00:00"}) == (None, None)
        assert event_key_of({"title": "Remy", "when": "fixed", "start": "soon"}) == (None, None)
        assert event_key_of({"when": "fixed", "start": "2026-11-10T00:00"}) == (None, None)

    def test_twice_in_one_answer_is_only_for_new_events(self) -> None:
        task = {"sentence": "", "command": "add", "input": {"title": "Essay", "duration_min": 60}}
        out = proposals({"actions": [task, task]}, ("add",))
        assert [a.error for a in out.actions] == [None, None]

    def test_held_knows_one_offs_and_each_time_of_a_repeat(self, app: App) -> None:
        mulan(app)
        app.do("add", title="Dentist", when="fixed", start="2026-10-23T10:00", end="2026-10-23T11:00")
        held = Held(Ctx(app.conn, Writer(app.conn, 1), app.now_utc, "you", 1, load_settings(app.conn, 1)))
        fixed = {"when": "fixed"}
        assert held(fixed | {"title": "dentist", "start": "2026-10-23T10:00"}) is not None
        assert held(fixed | {"title": "Dentist", "start": "2026-10-23T11:00"}) is None
        assert held(fixed | {"title": "Mira's Birthday", "start": "2028-02-01T00:00"}) is not None
        assert held(fixed | {"title": "Mira's Birthday", "start": "2028-02-02T00:00"}) is None

    def test_the_prompt_says_how_an_all_day_event_is_made(self) -> None:
        assert 'next day\'s "T00:00"' in SYSTEM and "Leave out what the context already has" in SYSTEM

    def test_1159pm_only_when_it_is_the_same_day_from_midnight(self) -> None:
        assert all_day_is_free({"start": "2026-10-20T00:00", "end": "2026-10-20T23:59"}) == {
            "start": "2026-10-20T00:00", "end": "2026-10-21T00:00", "blocks_time": False}  # fmt: skip
        assert all_day_is_free({"start": "2026-10-20T09:00", "end": "2026-10-20T23:59"})["end"] == "2026-10-20T23:59"
        assert all_day_is_free({"start": "2026-10-20T00:00", "end": "2026-10-21T23:59"})["end"] == "2026-10-21T23:59"
        assert all_day_is_free({"start": "2026-12-31T00:00", "end": "2026-12-31T23:59"})["end"] == "2027-01-01T00:00"
