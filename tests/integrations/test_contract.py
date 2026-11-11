"""Every integration against the contract (tests/integrations/contract.py), each through its fake: one row per
integration and check. A new integration joins by adding its harness to HARNESSES."""

import inspect
from collections.abc import Iterator
from pathlib import Path

import pytest

from friday.integrations import sync
from tests.commands.helpers import new_app
from tests.integrations import contract
from tests.integrations.contract import World
from tests.integrations.fake_asana import HARNESS as ASANA
from tests.integrations.fake_canvas import HARNESS as CANVAS
from tests.integrations.fake_github import HARNESS as GITHUB
from tests.integrations.fake_jira import HARNESS as JIRA
from tests.integrations.fake_linear import HARNESS as LINEAR
from tests.integrations.fake_mac_reminders import HARNESS as REMINDERS
from tests.integrations.fake_mac_things import HARNESS as THINGS
from tests.integrations.fake_notion import HARNESS as NOTION
from tests.integrations.fake_todoist import HARNESS as TODOIST
from tests.integrations.fake_trello import HARNESS as TRELLO
from tests.integrations.kit import Harness

HARNESSES = [TODOIST, REMINDERS, NOTION, TRELLO, ASANA, LINEAR, JIRA, GITHUB, CANVAS, THINGS]


def cases() -> Iterator:
    for h in HARNESSES:
        for name, check in contract.CHECKS.items():
            marks = getattr(check, "pytestmark", [])
            params = next((m.args for m in marks if m.name == "parametrize"), None)
            if params:
                for value in params[1]:
                    yield pytest.param(h, name, {params[0]: value}, id=f"{h.kind}-{name[6:]}-{value}")
            else:
                yield pytest.param(h, name, {}, id=f"{h.kind}-{name[6:]}")


def world(h: Harness, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    fake = h.fake(h.token)
    monkeypatch.setitem(sync.TRANSPORTS, h.kind, fake.transport)
    return World(h, new_app(tmp_path), fake)


@pytest.mark.parametrize(("h", "name", "params"), list(cases()))
def test_the_contract(h: Harness, name: str, params: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contract.run_check(name, world(h, tmp_path, monkeypatch), **params)


def test_every_check_is_run() -> None:
    assert len(contract.CHECKS) >= 13
    assert all(inspect.signature(c).parameters.get("w") for c in contract.CHECKS.values())
