"""A stand-in for Linear's GraphQL API (https://api.linear.app/graphql), the operations Friday sends, as Linear's
schema has them: Me (viewer), Mine (viewer.assignedIssues with a state-type filter, first/after, pageInfo), States
(issue.team.states: id, name, type, position) and Move (issueUpdate stateId → success). A personal key comes bare in
the Authorization header; a refused one is HTTP 400 with an AUTHENTICATION_ERROR, as Linear answers. Issues: `id`,
`identifier` (ENG-12), `title`, `description`, `dueDate` (a day), `url`, `state` {type}, `team` {name}, `assignee`."""

import itertools
import uuid
from typing import Any

import httpx

from tests.integrations.kit import FakeService, Harness

ME = "u-maria"
STATES = [
    {"id": "st-backlog", "name": "Backlog", "type": "backlog", "position": 0},
    {"id": "st-todo", "name": "Todo", "type": "unstarted", "position": 1},
    {"id": "st-doing", "name": "In Progress", "type": "started", "position": 2},
    {"id": "st-review", "name": "In Review", "type": "started", "position": 3},
    {"id": "st-done", "name": "Done", "type": "completed", "position": 4},
    {"id": "st-shipped", "name": "Shipped", "type": "completed", "position": 5},
    {"id": "st-canceled", "name": "Canceled", "type": "canceled", "position": 6},
]


class FakeLinear(FakeService):
    host = "api.linear.app"

    def __init__(self, token: str, page_size: int = 100):
        super().__init__(token)
        self.issues: dict[str, dict[str, Any]] = {}
        self.page_size = page_size
        self.numbers = itertools.count(1)

    def add(self, title: str, due: str | None = None, assignee: str | None = ME, state: str = "st-todo",
            **extra: Any) -> str:  # fmt: skip
        number = next(self.numbers)
        issue_id = str(uuid.UUID(int=number))
        self.issues[issue_id] = {
            "id": issue_id, "identifier": f"ENG-{number}", "title": title, "description": extra.get("description"),
            "dueDate": due[:10] if due else None, "url": f"https://linear.app/acme/issue/ENG-{number}",
            "state": next(s for s in STATES if s["id"] == state), "team": {"name": "Engineering"},
            "assignee": assignee,
        }  # fmt: skip
        return issue_id

    def authorized(self, request: httpx.Request) -> bool:
        return request.headers.get("authorization") == self.token

    def handle(self, request: httpx.Request) -> httpx.Response:
        answer = super().handle(request)
        if answer.status_code == 401:  # Linear says a refused key in GraphQL's way, with a 400
            return httpx.Response(400, json={"errors": [{"message": "Authentication required, not authenticated",
                                                         "extensions": {"code": "AUTHENTICATION_ERROR"}}]})  # fmt: skip
        return answer

    def writes(self) -> list[str]:
        """Only mutations change Linear: every request is a POST to /graphql."""
        return [f"mutation {self.body(r)['operationName']}" for r in self.requests
                if self.body(r)["query"].startswith("mutation")]  # fmt: skip

    def respond(self, request: httpx.Request) -> httpx.Response:
        assert request.method == "POST" and request.url.path == "/graphql", request.url
        body = self.body(request)
        op, given = body["operationName"], body.get("variables") or {}
        if op == "Me":
            return ok({"viewer": {"id": ME, "name": "Maria Lopez", "email": "maria@acme.test"}})
        if op == "Mine":
            assert 'nin: ["completed", "canceled"]' in body["query"], body["query"]
            mine = [i for i in self.issues.values() if i["assignee"] == ME
                    and i["state"]["type"] not in ("completed", "canceled")]  # fmt: skip
            start = int(given.get("after") or 0)
            size = min(100, self.page_size)
            more = start + size < len(mine)
            nodes = [{k: v for k, v in i.items() if k != "assignee"} for i in mine[start : start + size]]
            info = {"hasNextPage": more, "endCursor": str(start + size) if more else None}
            return ok({"viewer": {"assignedIssues": {"nodes": nodes, "pageInfo": info}}})
        if op == "States":
            issue = self.issues.get(given["id"])
            return ok({"issue": {"team": {"states": {"nodes": STATES}}} if issue else None})
        if op == "Move":
            self.issues[given["id"]]["state"] = next(s for s in STATES if s["id"] == given["state"])
            return ok({"issueUpdate": {"success": True}})
        unknown = {"message": f"Unknown operation {op}", "extensions": {"code": "GRAPHQL_VALIDATION_FAILED"}}
        return httpx.Response(400, json={"errors": [unknown]})


def ok(data: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json={"data": data})


def _set_state(fake: FakeLinear, issue: str, state: str) -> None:
    fake.issues[issue]["state"] = next(s for s in STATES if s["id"] == state)


HARNESS = Harness(
    kind="linear",
    token="lin_api_stand-in-not-a-real-key",  # not shaped like a real one: no scanner takes it for a leak
    fake=FakeLinear,
    add=lambda fake, title, due=None, minutes=None: fake.add(title, due),
    move=lambda fake, issue, due: fake.issues[issue].update(dueDate=due[:10]),
    rename=lambda fake, issue, title: fake.issues[issue].update(title=title),
    finish=lambda fake, issue: _set_state(fake, issue, "st-done"),
    is_done=lambda fake, issue: fake.issues[issue]["state"]["type"] == "completed",
    two_way=True,
    lengths=False,
    times=False,
)
