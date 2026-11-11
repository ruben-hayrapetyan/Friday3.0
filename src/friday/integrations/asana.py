"""Asana (C96, your choice: both ways; C103). Its API at https://app.asana.com/api/1.0 with a personal access token
(Asana's developer console → Create new token) as a Bearer token.

What comes in is your My tasks: the open tasks assigned to you, in each workspace you're in (GET tasks with assignee
me, workspace, completed_since now; pages of 100 by `offset`). A task's `due_at` is a moment (UTC), else `due_on` a
day; it keeps no length. A tracker's to-do is a Work task (C97). Done here completes it (PUT tasks/{gid}), opened
again un-completes it; one completed or deleted in Asana is done here."""

import os
from typing import Any, ClassVar, Literal

from friday.integrations.base import Caps, ConnectorError, Http, Remote, Transport, pages

API = "https://app.asana.com/api/1.0"
TOKEN_PAGE = "https://app.asana.com/0/my-apps"
FIELDS = "name,notes,due_on,due_at,completed,permalink_url,projects.name"


class Asana:
    kind: ClassVar[str] = "asana"
    name: ClassVar[str] = "Asana"
    caps: ClassVar[Caps] = Caps(two_way=True, lengths=False, kind="Work task")

    def __init__(self, token: str, config: dict[str, Any] | None = None, transport: Transport = None):
        if not token.strip():
            raise ConnectorError("token", f"No Asana token: make one at {TOKEN_PAGE} and paste it here")
        base = os.environ.get("FRIDAY_API_ASANA") or API  # another address: only a fake service, in system tests
        self.http = Http(self.name, base, {"Authorization": f"Bearer {token.strip()}"}, transport)

    def me(self) -> dict[str, Any]:
        found = self.http.json("GET", "/users/me", params={"opt_fields": "name,email,workspaces.name"})
        data = found.get("data") if isinstance(found, dict) else None
        if not isinstance(data, dict):
            raise ConnectorError("answer", "Asana's answer about you came back in a shape Friday doesn't know")
        return data

    def check(self) -> str:
        me = self.me()
        return str(me.get("email") or me.get("name") or "your Asana")

    def read(self) -> list[Remote]:
        me = self.me()
        return [r for w in me.get("workspaces") or [] for r in self.mine_in(str(w["gid"]))]

    def mine_in(self, workspace: str) -> list[Remote]:
        def page(offset: str | None) -> tuple[list[Any], str | None]:
            params = {"assignee": "me", "workspace": workspace, "completed_since": "now", "limit": 100,
                      "opt_fields": FIELDS} | ({"offset": offset} if offset else {})  # fmt: skip
            found = self.http.json("GET", "/tasks", params=params)
            if not isinstance(found, dict) or not isinstance(found.get("data"), list):
                raise ConnectorError("answer", "Asana's list of tasks came back in a shape Friday doesn't know")
            return found["data"], (found.get("next_page") or {}).get("offset")

        return [remote(t) for t in pages(page) if not t.get("completed")]

    def write(self, external_id: str, op: Literal["done", "reopen"]) -> None:
        self.http.call("PUT", f"/tasks/{external_id}", json={"data": {"completed": op == "done"}})


def remote(task: dict[str, Any]) -> Remote:
    projects = ", ".join(str(p.get("name")) for p in task.get("projects") or [] if p.get("name"))
    notes = "\n\n".join(
        x for x in (str(task.get("notes") or "").strip(), f"In Asana: {projects}" if projects else "") if x
    )
    return Remote(
        external_id=str(task["gid"]),
        title=str(task.get("name") or "Untitled task").strip(),
        due=task.get("due_at") or task.get("due_on") or None,  # a moment in UTC (the sync localises), else a day
        notes=notes,
        url=task.get("permalink_url"),
        done=bool(task.get("completed")),
        firm=True,
    )
