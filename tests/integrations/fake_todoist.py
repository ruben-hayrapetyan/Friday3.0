"""A stand-in for Todoist's API v1 (https://api.todoist.com/api/v1), the parts Friday uses, as Doist's own
todoist-api-python calls them: GET /projects (to prove a token), GET /tasks in pages (`results`, `next_cursor`,
`limit` at most 200), POST /tasks/{id}/close and /reopen (204). Tasks look as Todoist sends them: `content`,
`description`, `due` {date, string, is_recurring, timezone, lang}, `deadline`, `duration` {amount, unit}, `checked`."""

import itertools
from typing import Any

import httpx

from tests.integrations.kit import FakeService, Harness

PREFIX = "/api/v1"


class FakeTodoist(FakeService):
    host = "api.todoist.com"

    def __init__(self, token: str, page_size: int = 50):
        super().__init__(token)
        self.tasks: dict[str, dict[str, Any]] = {}
        self.page_size = page_size
        self.ids = itertools.count(6_000_000_001)

    def add(self, title: str, due: str | None = None, minutes: int | None = None, **extra: Any) -> str:
        task_id = str(next(self.ids))
        self.tasks[task_id] = {
            "id": task_id, "content": title, "description": extra.get("description", ""), "project_id": "p1",
            "section_id": None, "parent_id": None, "labels": [], "priority": extra.get("priority", 1),
            "due": {"date": due, "string": due, "lang": "en", "is_recurring": False, "timezone": None} if due else None,
            "deadline": extra.get("deadline"),
            "duration": {"amount": minutes, "unit": "minute"} if minutes else extra.get("duration"),
            "checked": False, "is_deleted": False, "child_order": len(self.tasks),
            "added_at": "2026-11-01T12:00:00.000000Z", "updated_at": "2026-11-01T12:00:00.000000Z",
        }  # fmt: skip
        return task_id

    def path(self, request: httpx.Request) -> str:
        return request.url.path.removeprefix(PREFIX)

    def respond(self, request: httpx.Request) -> httpx.Response:
        path, method = self.path(request), request.method
        if method == "GET" and path == "/projects":
            return httpx.Response(200, json={"results": [{"id": "p1", "name": "Inbox"}], "next_cursor": None})
        if method == "GET" and path == "/tasks":
            limit = min(int(request.url.params.get("limit", 50)), 200, self.page_size)
            start = int(request.url.params.get("cursor") or 0)
            open_ = [t for t in self.tasks.values() if not t["checked"] and not t["is_deleted"]]
            page = open_[start : start + limit]
            more = start + limit < len(open_)
            return httpx.Response(200, json={"results": page, "next_cursor": str(start + limit) if more else None})
        parts = path.strip("/").split("/")
        if method == "POST" and len(parts) == 3 and parts[0] == "tasks" and parts[2] in ("close", "reopen"):
            task = self.tasks.get(parts[1])
            if task is None or task["is_deleted"]:
                return httpx.Response(404, json={"error": "Task not found"})
            task["checked"] = parts[2] == "close"
            return httpx.Response(204)
        return httpx.Response(404, json={"error": f"no {method} {path}"})


def _move(fake: FakeTodoist, task_id: str, due: str) -> None:
    fake.tasks[task_id]["due"] = {"date": due, "string": due, "lang": "en", "is_recurring": False, "timezone": None}


HARNESS = Harness(
    kind="todoist",
    token="0123456789abcdef0123456789abcdef01234567",
    fake=FakeTodoist,
    add=lambda fake, title, due=None, minutes=None: fake.add(title, due, minutes),
    move=_move,
    rename=lambda fake, task_id, title: fake.tasks[task_id].update(content=title),
    finish=lambda fake, task_id: fake.tasks[task_id].update(checked=True),
    is_done=lambda fake, task_id: fake.tasks[task_id]["checked"],
    two_way=True,
    lengths=True,
)
