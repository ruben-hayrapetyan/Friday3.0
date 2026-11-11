"""A stand-in for Microsoft Graph's To Do (https://graph.microsoft.com/v1.0) and Microsoft's token endpoint, the parts
Friday uses, as Microsoft's reference has them: GET me, GET me/todo/lists, GET me/todo/lists/{id}/tasks ($filter on
status, $top; pages by @odata.nextLink), PATCH a task's status; and POST …/oauth2/v2.0/token (a code with its PKCE
verifier, or a refresh token, for an access token that expires in an hour). Tasks: `id`, `title`, `status`
(notStarted, inProgress, completed…), `dueDateTime` {dateTime, timeZone} (a day at midnight), `body` {content,
contentType}."""

import base64
import hashlib
import itertools
import json
from typing import Any
from urllib.parse import parse_qs

import httpx

from tests.integrations.kit import FakeService, Harness

ACCESS, REFRESH = "ms-access-1", "ms-refresh-1"
TOKENS = json.dumps({"access_token": ACCESS, "refresh_token": REFRESH, "expires_at": 4_102_444_800})  # in 2100


class FakeGraph(FakeService):
    host = "graph.microsoft.com"

    def __init__(self, token: str, page_size: int = 100):
        super().__init__(ACCESS)
        self.lists = [{"id": "L-tasks", "displayName": "Tasks", "wellknownListName": "defaultList"},
                      {"id": "L-home", "displayName": "Home", "wellknownListName": "none"}]  # fmt: skip
        self.tasks: dict[str, dict[str, Any]] = {}
        self.page_size = page_size
        self.ids = itertools.count(1)
        self.codes: dict[str, str] = {}  # a sign-in's code → its PKCE challenge
        self.messages: dict[str, dict[str, Any]] = {}  # Outlook's inbox, newest last
        self.issued = 1

    def add(self, title: str, due: str | None = None, in_list: str = "L-tasks", body: str = "") -> str:
        task_id = f"AAMk{next(self.ids):04d}"
        self.tasks[task_id] = {"id": task_id, "list": in_list, "title": title, "status": "notStarted",
                               "importance": "normal", "body": {"content": body, "contentType": "text"},
                               "dueDateTime": {"dateTime": f"{due[:10]}T00:00:00.0000000", "timeZone": "UTC"}
                               if due else None}  # fmt: skip
        return task_id

    def mail(self, sender: str, subject: str, body: str, received: str = "2026-10-19T14:00:00Z",
             conversation: str | None = None, pdf: bool = False, bulk: bool = False) -> str:  # fmt: skip
        message_id = f"AAkALg{len(self.messages) + 1:04d}"  # an immutable id, as Prefer: IdType="ImmutableId" gives
        self.messages[message_id] = {
            "id": message_id, "conversationId": conversation or f"conv-{message_id}", "subject": subject,
            "from": {"emailAddress": {"name": sender.split("@")[0], "address": sender}},
            "toRecipients": [{"emailAddress": {"address": "maria@outlook.com"}}], "receivedDateTime": received,
            "body": {"contentType": "text", "content": body}, "hasAttachments": pdf,
            "internetMessageHeaders": [{"name": "List-Unsubscribe", "value": "<mailto:u@x>"}] if bulk else [],
        }  # fmt: skip
        return message_id

    def path(self, request: httpx.Request) -> str:
        return request.url.path.removeprefix("/v1.0")

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "login.microsoftonline.com":
            return self.token_endpoint(request)
        return super().handle(request)

    def token_endpoint(self, request: httpx.Request) -> httpx.Response:
        asked = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        if asked.get("grant_type") == "authorization_code":
            challenge = self.codes.pop(asked.get("code", ""), None)
            made = base64.urlsafe_b64encode(hashlib.sha256(asked.get("code_verifier", "").encode()).digest())
            if challenge is None or made.rstrip(b"=").decode() != challenge:
                return httpx.Response(400, json={"error": "invalid_grant", "error_description": "AADSTS70000"})
        elif asked.get("grant_type") != "refresh_token" or asked.get("refresh_token") != REFRESH:
            return httpx.Response(400, json={"error": "invalid_grant"})
        self.issued += 1
        self.token = f"ms-access-{self.issued}"
        return httpx.Response(200, json={"token_type": "Bearer", "access_token": self.token, "expires_in": 3599,
                                         "refresh_token": REFRESH, "scope": "Tasks.ReadWrite User.Read"})  # fmt: skip

    def writes(self) -> list[str]:
        return [f"PATCH {self.path(r)}" for r in self.requests if r.method == "PATCH"]

    def respond(self, request: httpx.Request) -> httpx.Response:
        path, method, params = self.path(request), request.method, request.url.params
        if method == "GET" and path == "/me":
            return httpx.Response(200, json={"displayName": "Maria Lopez", "mail": None,
                                             "userPrincipalName": "maria@outlook.com"})  # fmt: skip
        if method == "GET" and path == "/me/mailFolders/inbox/messages":
            assert 'IdType="ImmutableId"' in request.headers.get("prefer", ""), request.headers
            since = params["$filter"].removeprefix("receivedDateTime ge ")
            found = sorted((m for m in self.messages.values() if m["receivedDateTime"] >= since),
                           key=lambda m: m["receivedDateTime"], reverse=True)  # fmt: skip
            return httpx.Response(200, json={"value": [{"id": m["id"], "conversationId": m["conversationId"]}
                                                       for m in found[: int(params["$top"])]]})  # fmt: skip
        if method == "GET" and path.startswith("/me/messages/"):
            parts = path.strip("/").split("/")
            message = self.messages.get(parts[2])
            if message is None:
                return httpx.Response(404, json={"error": {"code": "ErrorItemNotFound"}})
            if len(parts) == 3:
                return httpx.Response(200, json=message)
            pdf = {"id": "att-1", "name": "Syllabus.pdf", "contentType": "application/pdf", "size": 1200}
            if len(parts) == 4:
                return httpx.Response(200, json={"value": [pdf] if message["hasAttachments"] else []})
            return httpx.Response(200, json=pdf | {"contentBytes": "JVBERi0xLjQ="})
        if method == "GET" and path == "/me/todo/lists":
            return httpx.Response(200, json={"value": self.lists})
        parts = path.strip("/").split("/")
        if parts[:3] == ["me", "todo", "lists"] and len(parts) >= 5 and parts[4] == "tasks":
            if method == "GET":
                assert params.get("$filter") == "status ne 'completed'", params
                found = [self.shown(t) for t in self.tasks.values() if t["list"] == parts[3]
                         and t["status"] != "completed"]  # fmt: skip
                skip = int(params.get("$skip", 0))
                size = min(int(params.get("$top", 10)), self.page_size)
                body: dict[str, Any] = {"value": found[skip : skip + size]}
                if skip + size < len(found):
                    body["@odata.nextLink"] = str(request.url.copy_merge_params({"$skip": skip + size}))
                return httpx.Response(200, json=body)
            if method == "PATCH" and len(parts) == 6:
                task = self.tasks.get(parts[5])
                if task is None or task["list"] != parts[3]:
                    return httpx.Response(404, json={"error": {"code": "ErrorItemNotFound"}})
                task["status"] = self.body(request)["status"]
                return httpx.Response(200, json=self.shown(task))
        return httpx.Response(404, json={"error": {"code": "BadRequest", "message": f"No {method} {path}"}})

    @staticmethod
    def shown(t: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in t.items() if k != "list"}


def _move(fake: FakeGraph, task: str, due: str) -> None:
    fake.tasks[task]["dueDateTime"] = {"dateTime": f"{due[:10]}T00:00:00.0000000", "timeZone": "UTC"}


HARNESS = Harness(
    kind="microsoft_todo",
    token=TOKENS,
    fake=FakeGraph,
    add=lambda fake, title, due=None, minutes=None: fake.add(title, due),
    move=_move,
    rename=lambda fake, task, title: fake.tasks[task].update(title=title),
    finish=lambda fake, task: fake.tasks[task].update(status="completed"),
    is_done=lambda fake, task: fake.tasks[task]["status"] == "completed",
    two_way=True,
    lengths=False,
    times=False,
)
