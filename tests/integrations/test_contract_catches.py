"""The contract catches what it's for (C96: "build a way to test whether it is right"): each connector here is
Todoist's with one bug put in on purpose, the kind a new integration could have, and the check meant for that bug
must fail on it. A check that passes a broken connector would pass a broken integration too."""

import itertools
from pathlib import Path

import pytest

from friday.integrations import sync
from friday.integrations.base import ConnectorError, Remote
from friday.integrations.todoist import Todoist
from tests.commands.helpers import new_app
from tests.integrations import contract
from tests.integrations.contract import World
from tests.integrations.fake_todoist import HARNESS

counter = itertools.count()


class NewIdsEachRead(Todoist):
    """Ids that change from read to read (an id built from a page number, say): everything doubles."""

    def read(self) -> list[Remote]:
        n = next(counter)
        return [Remote(**(r.__dict__ | {"external_id": f"{r.external_id}-{n}"})) for r in super().read()]


class SendsTwice(Todoist):
    def write(self, external_id: str, op) -> None:  # noqa: ANN001
        super().write(external_id, op)
        super().write(external_id, op)


class SaysTheToken(Todoist):
    """Puts the token in its errors, as a careless message would."""

    def __init__(self, token: str, config=None, transport=None):  # noqa: ANN001
        super().__init__(token, config, transport)
        self.token = token

    def read(self) -> list[Remote]:
        try:
            return super().read()
        except ConnectorError as error:
            raise ConnectorError(error.problem, f"{error} (with {self.token})") from error


class PlainHttp(Todoist):
    def __init__(self, token: str, config=None, transport=None):  # noqa: ANN001
        super().__init__(token, config, transport)
        self.http.base = "http://api.todoist.com/api/v1"


class DropsLengths(Todoist):
    def read(self) -> list[Remote]:
        return [Remote(**(r.__dict__ | {"minutes": None})) for r in super().read()]


class EmptyOnFailure(Todoist):
    """Swallows a failed read as an empty list: every to-do looks done there."""

    def read(self) -> list[Remote]:
        try:
            return super().read()
        except ConnectorError:
            return []


class NeverSendsDone(Todoist):
    def write(self, external_id: str, op) -> None:  # noqa: ANN001
        return None


CAUGHT = [
    (NewIdsEachRead, "check_reading_again_with_nothing_changed_makes_nothing_and_sends_nothing", {}),
    (SendsTwice, "check_done_here_goes_back_exactly_once_and_reopen_too", {}),
    (SaysTheToken, "check_the_token_is_never_kept_outside_its_secret", {}),
    (PlainHttp, "check_requests_go_only_to_the_service", {}),
    (DropsLengths, "check_each_to_do_comes_in_once_with_its_title_due_and_length", {}),
    (EmptyOnFailure, "check_a_failure_is_said_in_words_and_loses_nothing", {"failure": "down"}),
    (NeverSendsDone, "check_a_failed_send_is_kept_and_sent_later_once", {}),
]


@pytest.mark.parametrize(("broken", "check", "params"), CAUGHT, ids=[b.__name__ for b, _, _ in CAUGHT])
def test_the_check_fails_on_the_bug_it_is_for(
    broken: type, check: str, params: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = HARNESS.fake(HARNESS.token)
    monkeypatch.setitem(sync.TRANSPORTS, "todoist", fake.transport)
    monkeypatch.setitem(sync.CONNECTORS, "todoist", broken)
    with pytest.raises(AssertionError):
        contract.run_check(check, World(HARNESS, new_app(tmp_path), fake), **params)


@pytest.mark.parametrize(("check", "params"), [(c, p) for _, c, p in CAUGHT])
def test_the_same_check_passes_the_real_connector(
    check: str, params: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = HARNESS.fake(HARNESS.token)
    monkeypatch.setitem(sync.TRANSPORTS, "todoist", fake.transport)
    contract.run_check(check, World(HARNESS, new_app(tmp_path), fake), **params)
