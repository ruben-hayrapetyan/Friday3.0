"""Todoist (C96, your choice: both ways). Its API v1 (https://api.todoist.com/api/v1, as Doist's own
todoist-api-python uses it): open tasks from GET tasks in pages of up to 200 (`results`, `next_cursor`); a task's
`due.date` is a day ("2026-11-20"), a local time ("2026-11-20T17:00:00") or UTC ("…Z"), its `deadline.date` a day,
its `duration` an amount in minutes or days; done is POST tasks/{id}/close, open again POST tasks/{id}/reopen. A
personal token from Todoist's Settings → Integrations → Developer, sent as a Bearer token."""

import os
from typing import Any, ClassVar, Literal

from friday.integrations.base import Caps, ConnectorError, Http, Remote, Transport, pages

API = "https://api.todoist.com/api/v1"
TOKEN_PAGE = "https://app.todoist.com/app/settings/integrations/developer"
DAY_MIN = 8 * 60  # a duration in days is a working day each


class Todoist:
    kind: ClassVar[str] = "todoist"
    name: ClassVar[str] = "Todoist"
    caps: ClassVar[Caps] = Caps(two_way=True, lengths=True)

    def __init__(self, token: str, config: dict[str, Any] | None = None, transport: Transport = None):
        if not token.strip():
            raise ConnectorError("token", f"No Todoist token: copy yours from {TOKEN_PAGE}")
        base = os.environ.get("FRIDAY_API_TODOIST") or API  # another address: only a fake service, in system tests
        self.http = Http(self.name, base, {"Authorization": f"Bearer {token.strip()}"}, transport)

    def check(self) -> str:
        """Todoist's API has no "who am I": one project read proves the token (Doist's SDK lists no user call)."""
        self.http.json("GET", "/projects", params={"limit": 1})
        return "your Todoist"

    def read(self) -> list[Remote]:
        def page(cursor: str | None) -> tuple[list[Any], str | None]:
            params: dict[str, Any] = {"limit": 200} | ({"cursor": cursor} if cursor else {})
            found = self.http.json("GET", "/tasks", params=params)
            if not isinstance(found, dict) or not isinstance(found.get("results"), list):
                raise ConnectorError("answer", "Todoist's list of tasks came back in a shape Friday doesn't know")
            return found["results"], found.get("next_cursor")

        return [remote(t) for t in pages(page) if not t.get("checked") and not t.get("is_deleted")]

    def write(self, external_id: str, op: Literal["done", "reopen"]) -> None:
        self.http.call("POST", f"/tasks/{external_id}/{'close' if op == 'done' else 'reopen'}")


def remote(task: dict[str, Any]) -> Remote:
    """A Todoist task as Friday reads it: its due, else its deadline; its duration as minutes."""
    due = (task.get("due") or {}).get("date") or (task.get("deadline") or {}).get("date")
    return Remote(
        external_id=str(task["id"]),
        title=str(task.get("content") or "Untitled task").strip(),
        due=local_minutes(due),
        minutes=minutes(task.get("duration")),
        notes=str(task.get("description") or ""),
        url=f"https://app.todoist.com/app/task/{task['id']}",
        done=bool(task.get("checked")),
    )


def local_minutes(due: str | None) -> str | None:
    """ "2026-11-20T17:00:00" → "2026-11-20T17:00" (Friday's times are to the minute); a day or UTC kept."""
    if not due:
        return None
    if "T" not in due:
        return due[:10]
    zulu = due.endswith("Z")
    stamp = due.rstrip("Z")[:16]
    return stamp + "Z" if zulu else stamp


def minutes(duration: dict[str, Any] | None) -> int | None:
    if not duration or not isinstance(duration.get("amount"), int) or duration["amount"] <= 0:
        return None
    return duration["amount"] * (DAY_MIN if duration.get("unit") == "day" else 1)
