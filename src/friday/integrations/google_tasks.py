"""Google Tasks (C96, your choice: both ways; C110). Your answer (11 Nov): it rides Friday's own Google sign-in
(sync/google_auth.py), which asks for Tasks too once you connect it (TASKS_SCOPE), rather than a sign-in of its own.
The Tasks API (https://tasks.googleapis.com/tasks/v1) with that account's access token, renewed as Google's are.

What comes in is the open tasks of every list (GET users/@me/lists, then each list's tasks, not completed or hidden;
pages by nextPageToken). Google Tasks keeps a due day (the API's time is always midnight). Done here completes it
(PATCH status), opened again makes it needsAction; completed or deleted there is done here. A task is known as
"<list id>/<task id>"."""

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar, Literal

from friday.integrations.base import Caps, ConnectorError, Http, Remote, Transport
from friday.sync import google_auth

API = "https://tasks.googleapis.com/tasks/v1"


def access_token(folder: Path, account: str) -> str:
    """The account's Google access token, when it has allowed Tasks."""
    creds = google_auth.credentials(folder, account)
    if creds is None:
        raise ConnectorError("token", f"{account} isn't signed in to Google any more: sign in again in the Google box")
    if not creds.has_scopes([google_auth.TASKS_SCOPE]):
        raise ConnectorError("access", f"{account} hasn't allowed Google Tasks: press Sign in with Google in its box")
    return str(creds.token)


ACCESS: list[Callable[[Path, str], str]] = [access_token]  # a stand-in's, in tests


class GoogleTasks:
    kind: ClassVar[str] = "google_tasks"
    name: ClassVar[str] = "Google Tasks"
    caps: ClassVar[Caps] = Caps(two_way=True, lengths=False)
    fields: ClassVar[tuple[str, ...]] = ("account", "folder")

    def __init__(self, token: str, config: dict[str, Any] | None = None, transport: Transport = None):
        config = config or {}
        self.account = str(config.get("account") or "")
        folder = Path(str(config.get("folder") or "."))
        if not self.account:
            raise ConnectorError("token", "Sign in with Google first, allowing Tasks")
        # a token given is used as it is (a script's, the contract's); else the Google sign-in's, renewed by it
        given = token.strip()
        base = os.environ.get("FRIDAY_API_GOOGLE_TASKS") or API  # another address: only a fake service, in tests

        def bearer() -> dict[str, str]:
            return {"Authorization": f"Bearer {given or ACCESS[0](folder, self.account)}"}

        self.http = Http(self.name, base, {}, transport, fresh=bearer)

    def check(self) -> str:
        self.every("/users/@me/lists")
        return self.account

    def every(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        page: str | None = None
        for _ in range(100):
            answer = self.http.json("GET", path, params=(params or {}) | {"maxResults": 100}
                                    | ({"pageToken": page} if page else {}))  # fmt: skip
            if not isinstance(answer, dict):
                raise ConnectorError("answer", "Google Tasks answered in a shape Friday doesn't know")
            found += answer.get("items") or []
            page = answer.get("nextPageToken")
            if not page:
                break
        return found

    def read(self) -> list[Remote]:
        out: list[Remote] = []
        for task_list in self.every("/users/@me/lists"):
            tasks = self.every(f"/lists/{task_list['id']}/tasks", {"showCompleted": "false", "showHidden": "false"})
            out += [remote(t, task_list) for t in tasks if t.get("status") != "completed" and not t.get("deleted")]
        return out

    def write(self, external_id: str, op: Literal["done", "reopen"]) -> None:
        list_id, task_id = external_id.split("/", 1)
        body = {"status": "completed"} if op == "done" else {"status": "needsAction", "completed": None}
        self.http.call("PATCH", f"/lists/{list_id}/tasks/{task_id}", json=body)


def remote(task: dict[str, Any], task_list: dict[str, Any]) -> Remote:
    where = str(task_list.get("title") or "")
    notes = str(task.get("notes") or "").strip()
    return Remote(
        external_id=f"{task_list['id']}/{task['id']}",
        title=str(task.get("title") or "Untitled task").strip(),
        due=str(task["due"])[:10] if task.get("due") else None,  # a day: Google keeps no time for a task
        notes="\n\n".join(x for x in (notes, f"In Google Tasks: {where}" if where else "") if x),
        url=task.get("webViewLink"),
        done=task.get("status") == "completed",
        firm=True,
    )
