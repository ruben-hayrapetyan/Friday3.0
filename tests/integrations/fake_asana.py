"""A stand-in for Asana's API (https://app.asana.com/api/1.0), the parts Friday uses, as Asana's reference has them:
GET users/me (you, your workspaces), GET tasks (assignee and workspace together, completed_since=now for the open
ones, limit at most 100, `offset` from `next_page`), PUT tasks/{gid} ({"data": {"completed": …}}). Every answer is
wrapped in {"data": …}. Tasks look as Asana sends them: `gid`, `name`, `notes`, `due_on` (a day) or `due_at` (a UTC
moment), `completed`, `permalink_url`, `projects` [{gid, name}], `assignee`."""

import itertools
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from tests.integrations.kit import FakeService, Harness

PREFIX = "/api/1.0"
ME = "1200000000000001"
ZONE = ZoneInfo("America/New_York")  # new_app's


def asana_due(when: str | None) -> dict[str, Any]:
    if not when:
        return {"due_on": None, "due_at": None}
    if "T" not in when:
        return {"due_on": when, "due_at": None}
    moment = datetime.fromisoformat(when).replace(tzinfo=ZONE).astimezone(ZoneInfo("UTC"))
    return {"due_on": moment.date().isoformat(), "due_at": moment.strftime("%Y-%m-%dT%H:%M:%S.000Z")}


class FakeAsana(FakeService):
    host = "app.asana.com"

    def __init__(self, token: str, page_size: int = 100):
        super().__init__(token)
        self.tasks: dict[str, dict[str, Any]] = {}
        self.workspaces = [{"gid": "w1", "name": "Acme", "resource_type": "workspace"},
                           {"gid": "w2", "name": "Side project", "resource_type": "workspace"}]  # fmt: skip
        self.page_size = page_size
        self.ids = itertools.count(1_200_000_000_100_001)

    def add(self, title: str, due: str | None = None, workspace: str = "w1", assignee: str | None = ME,
            **extra: Any) -> str:  # fmt: skip
        gid = str(next(self.ids))
        self.tasks[gid] = {
            "gid": gid, "resource_type": "task", "name": title, "notes": extra.get("notes", ""), **asana_due(due),
            "completed": False, "permalink_url": f"https://app.asana.com/1/w/project/p/task/{gid}",
            "projects": extra.get("projects", [{"gid": "p1", "name": "Launch"}]), "workspace": workspace,
            "assignee": {"gid": assignee} if assignee else None,
        }  # fmt: skip
        return gid

    def path(self, request: httpx.Request) -> str:
        return request.url.path.removeprefix(PREFIX)

    def respond(self, request: httpx.Request) -> httpx.Response:
        path, method, params = self.path(request), request.method, request.url.params
        if method == "GET" and path == "/users/me":
            return httpx.Response(200, json={"data": {"gid": ME, "name": "Maria Lopez", "email": "maria@acme.test",
                                                      "workspaces": self.workspaces}})  # fmt: skip
        if method == "GET" and path == "/tasks":
            if not (params.get("assignee") and params.get("workspace")):
                said = "Must specify exactly one of project, tag, section, user task list, or assignee + workspace"
                return httpx.Response(400, json={"errors": [{"message": said}]})
            assert params["assignee"] == "me" and params.get("completed_since") == "now", params
            limit = min(int(params.get("limit", 100)), 100, self.page_size)
            start = int(params.get("offset") or 0)
            mine = [t for t in self.tasks.values() if t["workspace"] == params["workspace"] and not t["completed"]
                    and (t["assignee"] or {}).get("gid") == ME]  # fmt: skip
            page = mine[start : start + limit]
            more = start + limit < len(mine)
            nxt = {"offset": str(start + limit), "path": "/tasks?offset=…", "uri": "https://app.asana.com/…"}
            return httpx.Response(200, json={"data": page, "next_page": nxt if more else None})
        parts = path.strip("/").split("/")
        if method == "PUT" and len(parts) == 2 and parts[0] == "tasks":
            task = self.tasks.get(parts[1])
            if task is None:
                return httpx.Response(404, json={"errors": [{"message": "task: Unknown object"}]})
            task["completed"] = bool(self.body(request)["data"]["completed"])
            return httpx.Response(200, json={"data": task})
        return httpx.Response(404, json={"errors": [{"message": f"No matching route for request: {method} {path}"}]})


def _move(fake: FakeAsana, gid: str, due: str) -> None:
    fake.tasks[gid].update(asana_due(due))


HARNESS = Harness(
    kind="asana",
    token="2/stand-in/not-a-real-token",  # not shaped like a real one: no scanner takes it for a leak
    fake=FakeAsana,
    add=lambda fake, title, due=None, minutes=None: fake.add(title, due),
    move=_move,
    rename=lambda fake, gid, title: fake.tasks[gid].update(name=title),
    finish=lambda fake, gid: fake.tasks[gid].update(completed=True),
    is_done=lambda fake, gid: fake.tasks[gid]["completed"],
    two_way=True,
    lengths=False,
)
