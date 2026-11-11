"""TickTick (C96, your choice: both ways; C111). Its Open API (https://api.ticktick.com/open/v1), signed in on
TickTick's own page (integrations/oauth.py) through Friday's own app at developer.ticktick.com, whose id and secret
ship in Friday (your answer, 11 Nov: TickTick insists on a secret, which can't stay secret in a downloaded app; it
lets no one into anyone's tasks without their own Allow). TICKTICK_CLIENT_ID / _SECRET, overridden by
FRIDAY_TICKTICK_CLIENT_ID / _SECRET; until they're set the box says TickTick isn't ready in this copy of Friday.
TickTick's sign-in lasts about six months and can't be renewed: its box says to sign in again when it runs out.

What comes in is the open tasks of your Inbox and every open list (GET project, then each one's data). A due is the
moment TickTick keeps, or for an all-day task its day in the task's own time zone. Done here completes it (POST
…/complete), opened again sets it back to normal (POST task/{id}, status 0); completed or deleted there is done
here. A task is known as "<list id>/<task id>"."""

import os
from datetime import datetime
from typing import Any, ClassVar, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from friday.integrations.base import Caps, ConnectorError, Http, Remote, Transport
from friday.integrations.oauth import Provider, Session

API = "https://api.ticktick.com/open/v1"
# Friday's app at developer.ticktick.com (Manage Apps → Friday): set once by Friday's developer
TICKTICK_CLIENT_ID = ""
TICKTICK_CLIENT_SECRET = ""
INBOX = "inbox"


def client_id() -> str:
    return (os.environ.get("FRIDAY_TICKTICK_CLIENT_ID") or TICKTICK_CLIENT_ID).strip()


def client_secret() -> str:
    return (os.environ.get("FRIDAY_TICKTICK_CLIENT_SECRET") or TICKTICK_CLIENT_SECRET).strip()


PROVIDER = Provider(
    kind="ticktick", name="TickTick", authorize="https://ticktick.com/oauth/authorize",
    token="https://ticktick.com/oauth/token", client_id=client_id, secret=client_secret,
    scopes=("tasks:read", "tasks:write"), secret_in_body=False,
)  # fmt: skip


class TickTick:
    kind: ClassVar[str] = "ticktick"
    name: ClassVar[str] = "TickTick"
    caps: ClassVar[Caps] = Caps(two_way=True, lengths=False)
    provider: ClassVar[Provider] = PROVIDER

    def __init__(self, token: str, config: dict[str, Any] | None = None, transport: Transport = None):
        self.session = Session(PROVIDER, token, (config or {}).get("_keep"))
        base = os.environ.get("FRIDAY_API_TICKTICK") or API  # another address: only a fake service, in system tests

        def bearer() -> dict[str, str]:
            return {"Authorization": f"Bearer {self.session.access()}"}

        self.http = Http(self.name, base, {}, transport, fresh=bearer)

    def projects(self) -> list[dict[str, Any]]:
        found = self.http.json("GET", "/project")
        if not isinstance(found, list):
            raise ConnectorError("answer", "TickTick's lists came back in a shape Friday doesn't know")
        return [p for p in found if isinstance(p, dict) and not p.get("closed")]

    def check(self) -> str:
        n = len(self.projects())
        return f"your TickTick, {n + 1} list{'s' if n else ''} with the Inbox"  # TickTick has no "who am I"

    def read(self) -> list[Remote]:
        out: list[Remote] = []
        for project in [{"id": INBOX, "name": "Inbox"}, *self.projects()]:
            data = self.http.json("GET", f"/project/{project['id']}/data")
            tasks = (data or {}).get("tasks") if isinstance(data, dict) else None
            if not isinstance(tasks, list):
                raise ConnectorError(
                    "answer", f"TickTick's “{project.get('name')}” came back in a shape Friday doesn't know"
                )
            out += [remote(t, project) for t in tasks if t.get("status", 0) == 0]
        return out

    def write(self, external_id: str, op: Literal["done", "reopen"]) -> None:
        project, task = external_id.split("/", 1)
        if op == "done":
            self.http.call("POST", f"/project/{project}/task/{task}/complete")
        else:
            self.http.call("POST", f"/task/{task}", json={"id": task, "projectId": project, "status": 0})


def due_of(task: dict[str, Any]) -> str | None:
    """TickTick's due ("2026-11-20T21:00:00+0000"); an all-day task's as its day in the task's time zone."""
    raw = task.get("dueDate")
    if not raw:
        return None
    moment = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if not task.get("isAllDay"):
        return moment.isoformat(timespec="minutes")
    try:
        zone = ZoneInfo(str(task.get("timeZone") or "UTC"))
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    return moment.astimezone(zone).date().isoformat()


def remote(task: dict[str, Any], project: dict[str, Any]) -> Remote:
    notes = str(task.get("content") or task.get("desc") or "").strip()
    where = str(project.get("name") or "")
    project_id = str(task.get("projectId") or project["id"])
    return Remote(
        external_id=f"{project_id}/{task['id']}",
        title=str(task.get("title") or "Untitled task").strip(),
        due=due_of(task),
        notes="\n\n".join(x for x in (notes, f"In TickTick: {where}" if where else "") if x),
        url=f"https://ticktick.com/webapp/#p/{project_id}/tasks/{task['id']}",
        done=task.get("status") == 2,
        firm=True,
    )
