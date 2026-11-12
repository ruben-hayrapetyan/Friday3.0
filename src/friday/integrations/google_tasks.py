"""Google Tasks (C96, your choice: both ways; C110). Your answer (11 Nov): it rides Friday's own Google sign-in
(sync/google_auth.py), which asks for Tasks too once you connect it (TASKS_SCOPE), rather than a sign-in of its own.
The Tasks API (https://tasks.googleapis.com/tasks/v1) with that account's access token, renewed as Google's are.

What comes in is the open tasks of every list (GET users/@me/lists, then each list's tasks, not completed or hidden;
pages by nextPageToken). Google Tasks keeps a due day (the API's time is always midnight). Done here completes it
(PATCH status), opened again makes it needsAction; completed or deleted there is done here. A task is known as
"<list id>/<task id>".

Or through a script in your own Google account (C130, your choice 11 Nov: Friday's Google app is capped at 100 people
until Google verifies it, and downloads don't carry it). The Google Tasks box gives you the script with a key made for
this Friday; you deploy it as a Web app (Execute as: Me, Who has access: Anyone) and paste its link. Friday keeps
"<link>#<key>" as the token and POSTs {key, op} to the link: "check", "read" (every list's open tasks, in one
answer), "done", "reopen". Google answers a Web app's POST with a redirect to script.googleusercontent.com, where the
answer waits. A wrong key, the Tasks service not added, or a link that isn't the script's, is said with what to do.
No limit on people: each one's script is their own."""

import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar, Literal

from friday.integrations.base import Caps, ConnectorError, Http, Remote, Transport
from friday.sync import google_auth

API = "https://tasks.googleapis.com/tasks/v1"
# A script's Web app link: script.google.com/macros/s/<id>/exec, or a Workspace account's /a/macros/<domain>/s/<id>/exec
SCRIPT = re.compile(r"^https://script\.google\.com/(?:a/macros/[\w.-]+|macros)/s/[\w-]{20,}/exec$")
SCRIPT_V = 1  # the script's protocol, as web/src/settings/tasksScript.ts writes it
REDEPLOY = "Deploy → Manage deployments → ✎ → Version: New version → Deploy"


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
        self.script: Script | None = None
        if "#" in token or token.strip().startswith("http") or (token.strip() and not self.account):
            self.script = Script(token, transport)
            self.kept = {"via": "script"}  # in its config: Google's own sign-in needn't ask for Tasks for it
            return
        if not self.account:
            raise ConnectorError("token", "Sign in with Google first, allowing Tasks")
        # a token given is used as it is (a script's, the contract's); else the Google sign-in's, renewed by it
        given = token.strip()
        base = os.environ.get("FRIDAY_API_GOOGLE_TASKS") or API  # another address: only a fake service, in tests

        def bearer() -> dict[str, str]:
            return {"Authorization": f"Bearer {given or ACCESS[0](folder, self.account)}"}

        self.http = Http(self.name, base, {}, transport, fresh=bearer)

    def check(self) -> str:
        if self.script:
            return self.script.check()
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
        if self.script:
            return [remote(t, task_list) for task_list in self.script.read() for t in task_list.get("tasks") or []
                    if t.get("status") != "completed" and not t.get("deleted")]  # fmt: skip
        out: list[Remote] = []
        for task_list in self.every("/users/@me/lists"):
            tasks = self.every(f"/lists/{task_list['id']}/tasks", {"showCompleted": "false", "showHidden": "false"})
            out += [remote(t, task_list) for t in tasks if t.get("status") != "completed" and not t.get("deleted")]
        return out

    def write(self, external_id: str, op: Literal["done", "reopen"]) -> None:
        list_id, task_id = external_id.split("/", 1)
        if self.script:
            self.script.ask(op, list=list_id, task=task_id)
            return
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


class Script:
    """Your Google Tasks script's Web app (C130): its link and the key this Friday made it with."""

    name = "Your Google Tasks script"

    def __init__(self, token: str, transport: Transport = None):
        link, _, self.key = token.strip().partition("#")
        link = link.strip().split("?")[0]
        if link.endswith("/dev"):
            raise ConnectorError("token", "That's the script's test link (it ends in /dev): paste the Web app link, "
                                 "the one ending in /exec, from Deploy → Manage deployments")  # fmt: skip
        base = os.environ.get("FRIDAY_API_GOOGLE_TASKS_SCRIPT")  # a fake script, in tests
        if not (SCRIPT.match(link) or (base and link.startswith(base))):
            raise ConnectorError("token", "That isn't a Google Apps Script Web app link: after Deploy, copy the Web "
                                 "app URL (https://script.google.com/macros/s/…/exec) and paste it here")  # fmt: skip
        if not self.key:
            raise ConnectorError("token", "The script's key is missing: connect from Friday's Google Tasks box")
        # httpx ends a base address with "/": the link's folder is the base, and "exec" each request's path
        self.folder, self.leaf = link.rsplit("/", 1)
        self.http = Http(self.name, self.folder + "/", {}, transport)

    def ask(self, op: str, **more: str) -> dict[str, Any]:
        try:
            answer = self.http.call("POST", self.leaf, json={"key": self.key, "op": op, "v": SCRIPT_V} | more,
                                    allow=(404,), follow_redirects=True)  # fmt: skip
        except ConnectorError as error:
            if error.problem in ("token", "access"):  # Google's 401/403: the deployment isn't open to Friday
                said = "Google refused the script's link: in the script, Deploy → Manage deployments, check "
                raise ConnectorError("token", said + "Execute as: Me and Who has access: Anyone") from error
            raise
        if answer.url.host == "accounts.google.com":
            raise ConnectorError("token", "The script asks for a Google sign-in: in the script, Deploy → Manage "
                                 "deployments → ✎, set Who has access to Anyone, and deploy")  # fmt: skip
        if answer.status_code == 404:
            raise ConnectorError("token", "Google has no script at that link (the deployment may have been archived): "
                                 "copy the Web app link again from Deploy → Manage deployments")  # fmt: skip
        try:
            body = answer.json()
        except ValueError as error:
            raise ConnectorError("token", "The script's link answered with a web page, not Friday's script: check "
                                 "it's the Web app link (ending in /exec), deployed for Anyone, and that you "
                                 "allowed the script when Google asked") from error  # fmt: skip
        if not isinstance(body, dict):
            raise ConnectorError("answer", "The script answered in a shape Friday doesn't know")
        said = str(body.get("error") or "")
        if said == "key":
            raise ConnectorError("token", "The script's key isn't this Friday's: copy the script from Friday's Google "
                                 f"Tasks box again, paste it over the old one, save, then {REDEPLOY}")  # fmt: skip
        if "Tasks is not defined" in said:
            raise ConnectorError("access", "The script can't reach Google Tasks yet: in the script editor, next to "
                                 f"Services press +, add Google Tasks API, save, then {REDEPLOY}")  # fmt: skip
        if said == "op":
            raise ConnectorError("answer", f"The script is older than this Friday: copy it again, then {REDEPLOY}")
        if said:
            raise ConnectorError("answer", f"The script said: {said[:200]}")
        return body

    def check(self) -> str:
        return str(self.ask("check").get("account") or "your Google account")

    def read(self) -> list[dict[str, Any]]:
        lists = self.ask("read").get("lists")
        if not isinstance(lists, list):
            raise ConnectorError("answer", "The script answered in a shape Friday doesn't know")
        return [t for t in lists if isinstance(t, dict) and t.get("id")]
