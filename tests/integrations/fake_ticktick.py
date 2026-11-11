"""A stand-in for TickTick's Open API (https://api.ticktick.com/open/v1), the parts Friday uses, as TickTick's
reference has them: GET project, GET project/{id}/data (`inbox` for the Inbox: `project`, `tasks`, `columns`), POST
project/{id}/task/{id}/complete, POST task/{id} (`id`, `projectId` required; `status` 0 normal, 2 completed, -1
abandoned). Tasks: `id`, `projectId`, `title`, `content`, `dueDate` ("2026-10-23T21:00:00+0000"), `isAllDay`,
`timeZone`, `status`. Its Bearer token is the one TickTick's sign-in gives, which lasts about six months."""

import itertools
import json
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from tests.integrations.kit import FakeService, Harness

PREFIX = "/open/v1"
ACCESS = "tt-access-1"
ZONE = "America/New_York"  # new_app's
INBOX_ID = "inbox118904374"


def ticktick_due(when: str | None) -> dict[str, Any]:
    if not when:
        return {"dueDate": None, "isAllDay": False, "timeZone": ZONE}
    day = datetime.fromisoformat(when)
    local = day if "T" in when else datetime.combine(day, time(0))
    utc = local.replace(tzinfo=ZoneInfo(ZONE)).astimezone(ZoneInfo("UTC"))
    return {"dueDate": utc.strftime("%Y-%m-%dT%H:%M:%S+0000"), "isAllDay": "T" not in when, "timeZone": ZONE}


class FakeTickTick(FakeService):
    host = "api.ticktick.com"

    def __init__(self, token: str):
        super().__init__(ACCESS)
        self.projects = [
            {"id": "p-work", "name": "Work", "closed": False},
            {"id": "p-old", "name": "Old", "closed": True},
        ]
        self.tasks: dict[str, dict[str, Any]] = {}
        self.ids = itertools.count(1)

    def add(self, title: str, due: str | None = None, project: str = INBOX_ID, content: str = "") -> str:
        task_id = f"6720{next(self.ids):08x}"
        self.tasks[task_id] = {"id": task_id, "projectId": project, "title": title, "content": content,
                               "status": 0, "priority": 0, **ticktick_due(due)}  # fmt: skip
        return task_id

    def path(self, request: httpx.Request) -> str:
        return request.url.path.removeprefix(PREFIX)

    def writes(self) -> list[str]:
        return [f"POST {self.path(r)}" for r in self.requests if r.method == "POST"]

    def respond(self, request: httpx.Request) -> httpx.Response:
        path, method = self.path(request), request.method
        if method == "GET" and path == "/project":
            return httpx.Response(200, json=self.projects)
        parts = path.strip("/").split("/")
        if method == "GET" and len(parts) == 3 and parts[0] == "project" and parts[2] == "data":
            wanted = INBOX_ID if parts[1] == "inbox" else parts[1]
            tasks = [t for t in self.tasks.values() if t["projectId"] == wanted and t["status"] == 0]
            return httpx.Response(200, json={"project": {"id": wanted}, "tasks": tasks, "columns": []})
        if method == "POST" and len(parts) == 5 and parts[0] == "project" and parts[4] == "complete":
            task = self.tasks.get(parts[3])
            if task is None or task["projectId"] != parts[1]:
                return httpx.Response(404, json={"errorMessage": "task not found"})
            task["status"] = 2
            return httpx.Response(200)
        if method == "POST" and len(parts) == 2 and parts[0] == "task":
            body, task = self.body(request), self.tasks.get(parts[1])
            if task is None or body.get("id") != parts[1] or body.get("projectId") != task["projectId"]:
                return httpx.Response(400, json={"errorMessage": "id and projectId are required"})
            task["status"] = int(body.get("status", task["status"]))
            return httpx.Response(200, json=task)
        return httpx.Response(404, json={"errorMessage": f"No {method} {path}"})


HARNESS = Harness(
    kind="ticktick",
    token=json.dumps({"access_token": ACCESS, "expires_at": 4_102_444_800}),  # no refresh token: TickTick gives none
    fake=FakeTickTick,
    add=lambda fake, title, due=None, minutes=None: fake.add(title, due),
    move=lambda fake, task, due: fake.tasks[task].update(ticktick_due(due)),
    rename=lambda fake, task, title: fake.tasks[task].update(title=title),
    finish=lambda fake, task: fake.tasks[task].update(status=2),
    is_done=lambda fake, task: fake.tasks[task]["status"] == 2,
    two_way=True,
    lengths=False,
)
