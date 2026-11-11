"""Microsoft To Do (C96, your choice: both ways; C109). Microsoft Graph (https://graph.microsoft.com/v1.0), signed in
in your browser with Microsoft's own page (integrations/oauth.py) through Friday's own app in Microsoft Entra: a public
app with no secret (your answer, 11 Nov), so its id ships in Friday (MS_CLIENT_ID; FRIDAY_MS_CLIENT_ID overrides it),
for personal (Outlook.com, Hotmail) and school or work accounts alike.

What comes in is the open tasks of every To Do list (GET me/todo/lists, then each list's tasks not completed; pages by
@odata.nextLink). To Do's due date is a day. Done here completes the task (PATCH status), opened again makes it not
started; completed or deleted in To Do is done here. A task is known as "<list id>/<task id>"."""

import os
from typing import Any, ClassVar, Literal

from friday.integrations.base import Caps, ConnectorError, Http, Remote, Transport
from friday.integrations.oauth import Provider, Session

API = "https://graph.microsoft.com/v1.0"
AUTHORITY = "https://login.microsoftonline.com/common/oauth2/v2.0"
# Friday's app in Microsoft Entra (portal.azure.com → App registrations → Friday → Application (client) ID): public,
# set once by Friday's developer
MS_CLIENT_ID = ""


def client_id() -> str:
    return (os.environ.get("FRIDAY_MS_CLIENT_ID") or MS_CLIENT_ID).strip()


TODO = Provider(
    kind="microsoft_todo", name="Microsoft To Do", authorize=f"{AUTHORITY}/authorize", token=f"{AUTHORITY}/token",
    client_id=client_id, scopes=("offline_access", "User.Read", "Tasks.ReadWrite"), extra={"prompt": "select_account"},
)  # fmt: skip


class MicrosoftTodo:
    kind: ClassVar[str] = "microsoft_todo"
    name: ClassVar[str] = "Microsoft To Do"
    caps: ClassVar[Caps] = Caps(two_way=True, lengths=False)
    provider: ClassVar[Provider] = TODO

    def __init__(self, token: str, config: dict[str, Any] | None = None, transport: Transport = None):
        config = config or {}
        self.session = Session(self.provider, token, config.get("_keep"))
        base = os.environ.get("FRIDAY_API_GRAPH") or API  # another address: only a fake service, in system tests
        self.http = Http(
            self.name, base, {}, transport, fresh=lambda: {"Authorization": f"Bearer {self.session.access()}"}
        )

    def check(self) -> str:
        me = self.http.json("GET", "/me", params={"$select": "displayName,mail,userPrincipalName"})
        if not isinstance(me, dict):
            raise ConnectorError("answer", "Microsoft's answer about you came back in a shape Friday doesn't know")
        return str(me.get("mail") or me.get("userPrincipalName") or me.get("displayName") or "your Microsoft account")

    def every(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Every page of a Graph list, by @odata.nextLink (at most a hundred pages)."""
        found: list[dict[str, Any]] = []
        answer = self.http.json("GET", path, params=params or {})
        for _ in range(100):
            if not isinstance(answer, dict) or not isinstance(answer.get("value"), list):
                raise ConnectorError("answer", "Microsoft's list came back in a shape Friday doesn't know")
            found += answer["value"]
            nxt = answer.get("@odata.nextLink")
            if not nxt:
                break
            answer = self.http.json("GET", nxt)
        return found

    def read(self) -> list[Remote]:
        out: list[Remote] = []
        for todo_list in self.every("/me/todo/lists"):
            tasks = self.every(f"/me/todo/lists/{todo_list['id']}/tasks",
                               {"$filter": "status ne 'completed'", "$top": 100})  # fmt: skip
            out += [remote(t, todo_list) for t in tasks if t.get("status") != "completed"]
        return out

    def write(self, external_id: str, op: Literal["done", "reopen"]) -> None:
        list_id, task_id = external_id.split("/", 1)
        status = "completed" if op == "done" else "notStarted"
        self.http.call("PATCH", f"/me/todo/lists/{list_id}/tasks/{task_id}", json={"status": status})


def remote(task: dict[str, Any], todo_list: dict[str, Any]) -> Remote:
    due = (task.get("dueDateTime") or {}).get("dateTime")
    body = task.get("body") or {}
    notes = str(body.get("content") or "").strip() if body.get("contentType", "text") == "text" else ""
    where = str(todo_list.get("displayName") or "")
    return Remote(
        external_id=f"{todo_list['id']}/{task['id']}",
        title=str(task.get("title") or "Untitled task").strip(),
        due=str(due)[:10] if due else None,  # To Do keeps a day
        notes="\n\n".join(x for x in (notes, f"In To Do: {where}" if where else "") if x),
        url="https://to-do.office.com/tasks/",
        done=task.get("status") == "completed",
        firm=True,
    )
