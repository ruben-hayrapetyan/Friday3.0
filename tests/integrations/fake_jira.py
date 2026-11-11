"""A stand-in for Jira Cloud's REST API v3 at a site (https://acme.atlassian.net/rest/api/3), the parts Friday uses,
as Atlassian's reference has them: GET myself, GET search/jql (jql, fields, maxResults, nextPageToken; `isLast`),
GET and POST issue/{id}/transitions. Basic auth: your email and API token. Issues: `id`, `key`, `fields` {summary,
duedate (a day), status {name, statusCategory {key: new | indeterminate | done}}, project {key, name}}. The workflow:
To Do → In Progress → Done, and Done → Reopened (a To Do-category status), as a simple Jira project has it."""

import base64
import itertools
from typing import Any

import httpx

from tests.integrations.kit import FakeService, Harness

PREFIX = "/rest/api/3"
EMAIL = "maria@acme.test"
ME = "557058:maria"
STATUSES = {
    "todo": {"id": "10000", "name": "To Do", "statusCategory": {"key": "new", "name": "To Do"}},
    "doing": {"id": "3", "name": "In Progress", "statusCategory": {"key": "indeterminate", "name": "In Progress"}},
    "done": {"id": "10001", "name": "Done", "statusCategory": {"key": "done", "name": "Done"}},
    "reopened": {"id": "4", "name": "Reopened", "statusCategory": {"key": "new", "name": "To Do"}},
}
MOVES = {  # from a status: (transition id, its name, to)
    "todo": [("11", "Start", "doing"), ("31", "Done", "done")],
    "doing": [("21", "Stop", "todo"), ("31", "Done", "done")],
    "done": [("41", "Reopen", "reopened")],
    "reopened": [("11", "Start", "doing"), ("31", "Done", "done")],
}


class FakeJira(FakeService):
    host = "acme.atlassian.net"

    def __init__(self, token: str, page_size: int = 100, stuck_token: bool = False):
        super().__init__(token)
        self.issues: dict[str, dict[str, Any]] = {}
        self.page_size = page_size
        self.stuck_token = stuck_token  # hands the same nextPageToken back forever, as developers report it can
        self.ids = itertools.count(10_001)

    def add(self, title: str, due: str | None = None, assignee: str | None = ME, status: str = "todo") -> str:
        issue_id = str(next(self.ids))
        self.issues[issue_id] = {"id": issue_id, "key": f"SHOP-{int(issue_id) - 10_000}", "assignee": assignee,
                                 "status": status, "summary": title, "duedate": due[:10] if due else None}  # fmt: skip
        return issue_id

    def shown(self, i: dict[str, Any]) -> dict[str, Any]:
        return {"id": i["id"], "key": i["key"], "self": f"https://{self.host}{PREFIX}/issue/{i['id']}", "fields": {
            "summary": i["summary"], "duedate": i["duedate"], "status": STATUSES[i["status"]],
            "project": {"id": "10000", "key": "SHOP", "name": "Shop redesign"}}}  # fmt: skip

    def authorized(self, request: httpx.Request) -> bool:
        said = base64.b64encode(f"{EMAIL}:{self.token}".encode()).decode()
        return request.headers.get("authorization") == f"Basic {said}"

    def path(self, request: httpx.Request) -> str:
        return request.url.path.removeprefix(PREFIX)

    def writes(self) -> list[str]:
        return [f"POST {self.path(r)}" for r in self.requests if r.method == "POST"]

    def respond(self, request: httpx.Request) -> httpx.Response:
        assert request.url.host == self.host, request.url
        path, method, params = self.path(request), request.method, request.url.params
        if method == "GET" and path == "/myself":
            return httpx.Response(200, json={"accountId": ME, "emailAddress": EMAIL, "displayName": "Maria Lopez"})
        if method == "GET" and path == "/search/jql":
            assert params["jql"].startswith("assignee = currentUser() AND statusCategory != Done"), params
            mine = [i for i in self.issues.values() if i["assignee"] == ME and i["status"] != "done"]
            start = int(params.get("nextPageToken") or 0) if not self.stuck_token else 0
            size = min(int(params.get("maxResults", 50)), 100, self.page_size)
            more = start + size < len(mine)
            body: dict[str, Any] = {"issues": [self.shown(i) for i in mine[start : start + size]], "isLast": not more}
            if more:
                body["nextPageToken"] = "stuck" if self.stuck_token else str(start + size)
                body["isLast"] = False
            return httpx.Response(200, json=body)
        parts = path.strip("/").split("/")
        if len(parts) == 3 and parts[0] == "issue" and parts[2] == "transitions":
            issue = self.issues.get(parts[1])
            if issue is None:
                return httpx.Response(
                    404, json={"errorMessages": ["Issue does not exist or you do not have permission"]}
                )
            moves = MOVES[issue["status"]]
            if method == "GET":
                return httpx.Response(200, json={"transitions": [{"id": t, "name": n, "to": STATUSES[to]}
                                                                 for t, n, to in moves]})  # fmt: skip
            wanted = self.body(request)["transition"]["id"]
            to = next((to for t, _, to in moves if t == wanted), None)
            if to is None:
                return httpx.Response(400, json={"errorMessages": ["Transition id is not valid for this issue"]})
            issue["status"] = to
            return httpx.Response(204)
        return httpx.Response(404, json={"errorMessages": [f"No {method} {path}"]})


HARNESS = Harness(
    kind="jira",
    token="ATATT-stand-in-not-a-real-token",  # not shaped like a real one: no scanner takes it for a leak
    fake=FakeJira,
    add=lambda fake, title, due=None, minutes=None: fake.add(title, due),
    move=lambda fake, issue, due: fake.issues[issue].update(duedate=due[:10]),
    rename=lambda fake, issue, title: fake.issues[issue].update(summary=title),
    finish=lambda fake, issue: fake.issues[issue].update(status="done"),
    is_done=lambda fake, issue: fake.issues[issue]["status"] == "done",
    two_way=True,
    lengths=False,
    times=False,
    fields={"site": "acme.atlassian.net", "email": EMAIL},
)
