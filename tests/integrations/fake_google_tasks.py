"""A stand-in for Google's Tasks API (https://tasks.googleapis.com/tasks/v1), the parts Friday uses, as Google's
reference has them: GET users/@me/lists, GET lists/{id}/tasks (showCompleted, showHidden, maxResults at most 100,
pageToken / nextPageToken), PATCH lists/{id}/tasks/{id} (`status`, `completed`). Tasks: `id`, `title`, `notes`,
`status` (needsAction, completed), `due` (a day, as RFC 3339 at midnight UTC), `webViewLink`."""

import itertools
from typing import Any

import httpx

from tests.integrations.kit import FakeService, Harness

PREFIX = "/tasks/v1"
ACCOUNT = "maria@gmail.com"


class FakeGoogleTasks(FakeService):
    host = "tasks.googleapis.com"

    def __init__(self, token: str, page_size: int = 100):
        super().__init__(token)
        self.lists = [{"id": "MDE", "title": "My Tasks"}, {"id": "MDI", "title": "Groceries"}]
        self.tasks: dict[str, dict[str, Any]] = {}
        self.page_size = page_size
        self.ids = itertools.count(1)

    def add(self, title: str, due: str | None = None, in_list: str = "MDE", notes: str = "") -> str:
        task_id = f"dGFzay{next(self.ids):04d}"
        self.tasks[task_id] = {"id": task_id, "list": in_list, "title": title, "notes": notes, "status": "needsAction",
                               "due": f"{due[:10]}T00:00:00.000Z" if due else None,
                               "webViewLink": f"https://tasks.google.com/task/{task_id}"}  # fmt: skip
        return task_id

    def path(self, request: httpx.Request) -> str:
        return request.url.path.removeprefix(PREFIX)

    def paged(self, request: httpx.Request, found: list[Any]) -> httpx.Response:
        size = min(int(request.url.params.get("maxResults", 20)), 100, self.page_size)
        start = int(request.url.params.get("pageToken") or 0)
        body: dict[str, Any] = {"kind": "tasks#tasks", "items": found[start : start + size]}
        if start + size < len(found):
            body["nextPageToken"] = str(start + size)
        return httpx.Response(200, json=body)

    def respond(self, request: httpx.Request) -> httpx.Response:
        path, method, params = self.path(request), request.method, request.url.params
        if method == "GET" and path == "/users/@me/lists":
            return self.paged(request, self.lists)
        parts = path.strip("/").split("/")
        if parts[0] == "lists" and len(parts) >= 3 and parts[2] == "tasks":
            if method == "GET":
                assert params.get("showCompleted") == "false", params
                found = [{k: v for k, v in t.items() if k != "list" and v is not None} for t in self.tasks.values()
                         if t["list"] == parts[1] and t["status"] != "completed"]  # fmt: skip
                return self.paged(request, found)
            if method == "PATCH" and len(parts) == 4:
                task = self.tasks.get(parts[3])
                if task is None:
                    return httpx.Response(404, json={"error": {"code": 404, "message": "Task not found."}})
                task["status"] = self.body(request)["status"]
                return httpx.Response(200, json=task)
        return httpx.Response(404, json={"error": {"code": 404, "message": f"No {method} {path}"}})


HARNESS = Harness(
    kind="google_tasks",
    token="gt-stand-in-access",  # a token given is used as it is; Friday's own use the Google sign-in's
    fake=FakeGoogleTasks,
    add=lambda fake, title, due=None, minutes=None: fake.add(title, due),
    move=lambda fake, task, due: fake.tasks[task].update(due=f"{due[:10]}T00:00:00.000Z"),
    rename=lambda fake, task, title: fake.tasks[task].update(title=title),
    finish=lambda fake, task: fake.tasks[task].update(status="completed"),
    is_done=lambda fake, task: fake.tasks[task]["status"] == "completed",
    two_way=True,
    lengths=False,
    times=False,
    fields={"account": ACCOUNT, "folder": "."},
)
