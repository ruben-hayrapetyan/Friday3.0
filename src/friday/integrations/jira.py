"""Jira Cloud (C96, your choice: both ways; C105). Its REST API v3 at your site (https://<team>.atlassian.net), with
your Atlassian email and an API token (id.atlassian.com → Security → API tokens) as Basic auth. The site has to be an
Atlassian Cloud address, so your token is never sent anywhere else.

What comes in is the open issues assigned to you (JQL `assignee = currentUser() AND statusCategory != Done`, by the
enhanced search, GET search/jql, pages of 100 by nextPageToken; a token Jira hands back twice stops the paging, which
developers report it can), as Work tasks, each with its key and project. Jira's due date is a day. Done here takes the
issue through its first transition into a Done-category status; opened again, into a To Do-category one (Jira's
workflows differ by project, so Friday asks which transitions it has). One done in Jira is done here."""

import base64
import os
import re
from collections.abc import Iterator
from typing import Any, ClassVar, Literal

from friday.integrations.base import Caps, ConnectorError, Http, Remote, Transport

TOKEN_PAGE = "https://id.atlassian.com/manage-profile/security/api-tokens"
JQL = "assignee = currentUser() AND statusCategory != Done ORDER BY duedate ASC"
FIELDS = "summary,duedate,status,project"
SITE = re.compile(r"^(?:https?://)?([a-z0-9][a-z0-9-]*)(?:\.atlassian\.net)?/?.*$", re.IGNORECASE)


def site_of(given: str) -> str:
    """Your site as Jira's address: "acme", "acme.atlassian.net" or a link into it are https://acme.atlassian.net."""
    found = SITE.match(given.strip())
    if not given.strip() or not found or ("." in given and ".atlassian.net" not in given.lower()):
        raise ConnectorError("token", "Give your Jira site, like yourteam.atlassian.net (Jira Cloud only)")
    return f"https://{found.group(1).lower()}.atlassian.net"


class Jira:
    kind: ClassVar[str] = "jira"
    name: ClassVar[str] = "Jira"
    caps: ClassVar[Caps] = Caps(two_way=True, lengths=False, kind="Work task")
    fields: ClassVar[tuple[str, ...]] = ("site", "email")

    def __init__(self, token: str, config: dict[str, Any] | None = None, transport: Transport = None):
        config = config or {}
        email = str(config.get("email") or "").strip()
        if not token.strip():
            raise ConnectorError("token", f"No Jira token: make an API token at {TOKEN_PAGE} and paste it here")
        if "@" not in email:
            raise ConnectorError("token", "Give the email you sign in to Jira with: Jira's token needs it")
        self.site = site_of(str(config.get("site") or ""))
        self.kept = {"site": self.site, "email": email}
        base = os.environ.get("FRIDAY_API_JIRA") or self.site  # another address: only a fake service, in system tests
        basic = base64.b64encode(f"{email}:{token.strip()}".encode()).decode()
        self.http = Http(self.name, base + "/rest/api/3", {"Authorization": f"Basic {basic}"}, transport)

    def check(self) -> str:
        me = self.http.json("GET", "/myself")
        if not isinstance(me, dict):
            raise ConnectorError("answer", "Jira's answer about you came back in a shape Friday doesn't know")
        return f"{me.get('displayName') or me.get('emailAddress') or 'you'} on {self.site.removeprefix('https://')}"

    def issues(self) -> Iterator[dict[str, Any]]:
        token: str | None = None
        seen: set[str] = set()
        for _ in range(100):
            params = {"jql": JQL, "fields": FIELDS, "maxResults": 100} | ({"nextPageToken": token} if token else {})
            found = self.http.json("GET", "/search/jql", params=params)
            if not isinstance(found, dict) or not isinstance(found.get("issues"), list):
                raise ConnectorError("answer", "Jira's list of issues came back in a shape Friday doesn't know")
            yield from found["issues"]
            token = found.get("nextPageToken")
            if found.get("isLast") or not token or token in seen:
                return
            seen.add(token)

    def read(self) -> list[Remote]:
        return [remote(i, self.site) for i in self.issues() if category(i) != "done"]

    def write(self, external_id: str, op: Literal["done", "reopen"]) -> None:
        found = self.http.json("GET", f"/issue/{external_id}/transitions")
        wanted = "done" if op == "done" else "new"
        moves = [t for t in (found or {}).get("transitions", [])
                 if ((t.get("to") or {}).get("statusCategory") or {}).get("key") == wanted]  # fmt: skip
        if not moves:
            where = "Done" if op == "done" else "To Do"
            raise ConnectorError("answer", f"Jira's workflow has no step from this issue's status to {where}")
        self.http.call("POST", f"/issue/{external_id}/transitions", json={"transition": {"id": moves[0]["id"]}})


def category(issue: dict[str, Any]) -> str | None:
    status = (issue.get("fields") or {}).get("status") or {}
    return (status.get("statusCategory") or {}).get("key")


def remote(issue: dict[str, Any], site: str) -> Remote:
    f = issue.get("fields") or {}
    project = (f.get("project") or {}).get("name")
    return Remote(
        external_id=str(issue["id"]),
        title=str(f.get("summary") or "Untitled issue").strip(),
        due=f.get("duedate") or None,
        notes=f"In Jira: {issue.get('key')}" + (f" ({project})" if project else ""),
        url=f"{site}/browse/{issue.get('key')}",
        done=category(issue) == "done",
        firm=True,
    )
