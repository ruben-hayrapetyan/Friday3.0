"""What every integration is (PROGRESS.md C96, 10 Nov: "since this app is not only for university students, the
personally tailored list of canvas, gmail, calendar, and syllabus is not enough"): a connector that reads a service's
to-dos as `Remote`s and, when it works both ways, writes done and reopen back. The shared sync (integrations/sync.py)
does everything else the same way for all of them: stored once, changed in place, gone means done, your edits kept.

A connector speaks to its service only through `Http`, which says every failure in words to act on and never puts the
token in one; tests hand it a fake service (tests/integrations/kit.py)."""

import hashlib
import json
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar, Literal, Protocol

import httpx

TIMEOUT_S = 30


@dataclass(frozen=True)
class Remote:
    """One to-do as the service has it, in Friday's terms. `due` is local ("2026-11-20" for a whole day,
    "2026-11-20T17:00" for a time) or UTC ("…Z"); `minutes` is the service's own length, when it keeps one."""

    external_id: str
    title: str
    due: str | None = None
    minutes: int | None = None
    notes: str = ""
    url: str | None = None
    done: bool = False
    firm: bool = True  # its due is a deadline; False: the day you meant to do it (Todoist's due beside a deadline)

    def digest(self) -> str:
        """Changes when anything Friday reads from it changes."""
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class Caps:
    two_way: bool = True  # done and reopen in Friday go back to the service
    lengths: bool = False  # the service keeps a length (an estimate, a duration)
    kind: str = "Task"  # what a to-do from it is when its title says nothing more (C97): "Task", or "Work task"
    on_mac: bool = False  # read and written by the Mac app (Apple Reminders), not over the internet
    lists: bool = False  # you choose which of its lists are read (Notion's databases); its ids are "<list>/<to-do>"
    gone_is_done: bool = True  # one no longer there was done there; not for Slack's mentions, which only age out


Problem = Literal["token", "access", "rate", "down", "answer"]


class ConnectorError(RuntimeError):
    """A failure in words to act on; `problem` says which kind, for the contract and the status line."""

    def __init__(self, problem: Problem, message: str, retry_after_s: int | None = None):
        super().__init__(message)
        self.problem, self.retry_after_s = problem, retry_after_s


class Connector(Protocol):
    kind: ClassVar[str]  # the source kind ("todoist")
    name: ClassVar[str]  # what the app calls the service ("Todoist")
    caps: ClassVar[Caps]

    def check(self) -> str:
        """The account the token belongs to, said back to you ("ruben@…"); ConnectorError when it doesn't work."""
        ...

    def read(self) -> list[Remote]:
        """Every to-do of yours the service has open now."""
        ...

    def write(self, external_id: str, op: Literal["done", "reopen"]) -> None:
        """Mark it done, or open again, there. Done twice is no error."""
        ...


Transport = httpx.BaseTransport | None  # a fake service, in tests


@dataclass
class Http:
    """A service's API: its address, your token as it wants it, and failures said plainly."""

    name: str
    base: str
    headers: dict[str, str]
    transport: Transport = None
    sent: list[str] = field(default_factory=list)  # method and path of each request, for the contract
    fresh: Callable[[], dict[str, str]] | None = None  # headers made for each request (a signed-in service's token)

    def client(self) -> httpx.Client:
        headers = self.headers | (self.fresh() if self.fresh else {})
        return httpx.Client(base_url=self.base, headers=headers, timeout=TIMEOUT_S, transport=self.transport)

    def call(self, method: str, path: str, allow: tuple[int, ...] = (), **kw: Any) -> httpx.Response:
        """The answer; a failure said in words, except the statuses in `allow`, which the connector reads itself (a
        GraphQL service's 400 says what went wrong in its body)."""
        self.sent.append(f"{method} {path}")
        try:
            with self.client() as client:
                answer = client.request(method, path, **kw)
        except httpx.TimeoutException as error:
            raise ConnectorError("down", f"{self.name} didn't answer in time: Friday tries again shortly") from error
        except httpx.HTTPError as error:
            raise ConnectorError("down", f"Friday couldn't reach {self.name}: check the internet connection") from error
        if answer.status_code in allow:
            return answer
        if answer.status_code in (401, 407):
            raise ConnectorError("token", f"{self.name} didn't accept the token: make a new one and paste it again")
        if answer.status_code == 403:
            raise ConnectorError("access", f"{self.name} refused: the token can't see this (check its permissions)")
        if answer.status_code == 429:
            after = answer.headers.get("retry-after", "")
            wait = int(after) if after.isdigit() else None
            raise ConnectorError("rate", f"{self.name} asked Friday to slow down: it tries again later", wait)
        if answer.status_code >= 500:
            raise ConnectorError("down", f"{self.name} is having trouble ({answer.status_code}): Friday tries again")
        if answer.status_code >= 400:
            raise ConnectorError("answer", f"{self.name} refused the request ({answer.status_code})")
        return answer

    def json(self, method: str, path: str, allow: tuple[int, ...] = (), **kw: Any) -> Any:
        answer = self.call(method, path, allow, **kw)
        try:
            return answer.json()
        except ValueError as error:
            raise ConnectorError("answer", f"{self.name} answered with something Friday can't read") from error


def pages(fetch: Callable[[str | None], tuple[list[Any], str | None]], most: int = 100) -> Iterator[Any]:
    """Every result of a paged list, following the cursor; at most `most` pages (a runaway cursor stops)."""
    cursor: str | None = None
    for _ in range(most):
        found, cursor = fetch(cursor)
        yield from found
        if not cursor:
            return
