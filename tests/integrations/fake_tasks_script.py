"""A stand-in for your Google Tasks script (C130), deployed as a Web app, as Google serves one: a POST to its /exec
link answers 302 with a one-time link on script.googleusercontent.com, where the script's answer waits (a GET). The
script is web/src/settings/tasksScript.ts; this answers its protocol over the same tasks as the Tasks API's stand-in:
{key, op: check | read | done | reopen, list, task}. A wrong key is {"error": "key"}; the Tasks service not added,
the ReferenceError Apps Script throws."""

import itertools
from typing import Any

import httpx

from tests.integrations.fake_google_tasks import FakeGoogleTasks
from tests.integrations.kit import Harness

LINK = "https://script.google.com/macros/s/AKfycbz-stand-in-deployment-id_0123456789/exec"
KEY = "k3y-made-by-this-friday"
ACCOUNT = "maria@gmail.com"
ECHO = "script.googleusercontent.com"


class FakeTasksScript(FakeGoogleTasks):
    host = "script.google.com"
    hosts = {"script.google.com", ECHO, "accounts.google.com"}

    def __init__(self, token: str, page_size: int = 100):
        super().__init__(token, page_size)
        self.key = token.partition("#")[2]
        self.waiting: dict[str, dict[str, Any]] = {}
        self.numbers = itertools.count(1)
        self.tasks_service = True  # the Google Tasks API service added in the editor
        self.access = "anyone"  # Who has access: "anyone", or "google" (any Google account: a sign-in page)
        self.asked: list[dict[str, Any]] = []

    def authorized(self, request: httpx.Request) -> bool:
        return True  # the script checks the key itself, in its answer

    def respond(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "accounts.google.com":
            return httpx.Response(200, text="<html><title>Sign in - Google Accounts</title></html>")
        if request.url.host == ECHO and request.method == "GET":
            body = self.waiting.pop(request.url.params.get("user_content_key", ""), None)
            return httpx.Response(200, json=body) if body else httpx.Response(404, text="<html>Not found</html>")
        if request.method != "POST" or str(request.url).split("?")[0] != LINK:
            return httpx.Response(404, text="<html><body>Sorry, unable to open the file at this time.</body></html>")
        if self.access == "google":
            return httpx.Response(302, headers={"location": "https://accounts.google.com/ServiceLogin?continue=x"})
        ask = self.body(request)
        self.asked.append(ask)
        number = f"echo{next(self.numbers)}"
        self.waiting[number] = self.answer(ask)
        return httpx.Response(302, headers={"location": f"https://{ECHO}/macros/echo?user_content_key={number}"})

    def answer(self, ask: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(ask, dict) or ask.get("key") != self.key:
            return {"error": "key"}
        if not self.tasks_service:
            return {"error": "Tasks is not defined"}
        op = ask.get("op")
        if op == "check":
            return {"ok": True, "v": 1, "account": ACCOUNT, "lists": len(self.lists)}
        if op == "read":
            return {"ok": True, "v": 1, "lists": [{"id": tl["id"], "title": tl["title"], "tasks": [
                {k: v for k, v in t.items() if k != "list" and v is not None}
                for t in self.tasks.values() if t["list"] == tl["id"] and t["status"] != "completed"]}
                for tl in self.lists]}  # fmt: skip
        if op in ("done", "reopen"):
            task = self.tasks.get(str(ask.get("task")))
            if task is None or task["list"] != ask.get("list"):
                return {"error": "API call to tasks.tasks.patch failed with error: Task not found."}
            task["status"] = "completed" if op == "done" else "needsAction"
            return {"ok": True}
        return {"error": "op"}

    def writes(self) -> list[str]:
        """What the script was asked to change: "done <task>"."""
        return [f"{a['op']} {a.get('task')}" for a in self.asked if a.get("op") in ("done", "reopen")]


HARNESS = Harness(
    kind="google_tasks",
    label="google_tasks_script",
    token=f"{LINK}#{KEY}",
    fake=FakeTasksScript,
    add=lambda fake, title, due=None, minutes=None: fake.add(title, due),
    move=lambda fake, task, due: fake.tasks[task].update(due=f"{due[:10]}T00:00:00.000Z"),
    rename=lambda fake, task, title: fake.tasks[task].update(title=title),
    finish=lambda fake, task: fake.tasks[task].update(status="completed"),
    is_done=lambda fake, task: fake.tasks[task]["status"] == "completed",
    two_way=True,
    lengths=False,
    times=False,
    token_word="script",
)
