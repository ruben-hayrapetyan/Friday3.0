"""Linear (C96, your choice: both ways; C104). Its GraphQL API at https://api.linear.app/graphql with a personal API
key (Linear's Settings → Security & access → Personal API keys), sent bare in the Authorization header, as Linear asks.

What comes in is the open issues assigned to you (viewer.assignedIssues, not completed or canceled; pages of 100 by
cursor), as Work tasks (C97: a tracker's to-do), each with its identifier and team. Linear's due date is a day; its
estimate is in points, not time, so no length. Done here moves the issue to its team's first Done state, opened again
to its first Todo state (issueUpdate stateId); one completed or canceled in Linear is done here. GraphQL says what
went wrong in its body: a refused key, "slow down", or anything else, each in words."""

import os
from typing import Any, ClassVar, Literal

from friday.integrations.base import Caps, ConnectorError, Http, Remote, Transport, pages

API = "https://api.linear.app"
TOKEN_PAGE = "https://linear.app/settings/account/security"
OPEN = '{state: {type: {nin: ["completed", "canceled"]}}}'

ME = "query Me { viewer { id name email } }"
MINE = (
    "query Mine($after: String) { viewer { assignedIssues(first: 100, after: $after, filter: " + OPEN + ") {"
    " nodes { id identifier title description dueDate url state { type } team { name } }"
    " pageInfo { hasNextPage endCursor } } } }"
)
STATES = "query States($id: String!) { issue(id: $id) { team { states { nodes { id name type position } } } } }"
MOVE = "mutation Move($id: String!, $state: String!) { issueUpdate(id: $id, input: {stateId: $state}) { success } }"


class Linear:
    kind: ClassVar[str] = "linear"
    name: ClassVar[str] = "Linear"
    caps: ClassVar[Caps] = Caps(two_way=True, lengths=False, kind="Work task")

    def __init__(self, token: str, config: dict[str, Any] | None = None, transport: Transport = None):
        if not token.strip():
            raise ConnectorError("token", f"No Linear key: make one at {TOKEN_PAGE} and paste it here")
        base = os.environ.get("FRIDAY_API_LINEAR") or API  # another address: only a fake service, in system tests
        self.http = Http(self.name, base, {"Authorization": token.strip()}, transport)

    def ask(self, query: str, **variables: Any) -> dict[str, Any]:
        operation = query.split("(")[0].split("{")[0].split()[-1]
        found = self.http.json("POST", "/graphql", allow=(400,),
                               json={"query": query, "variables": variables, "operationName": operation})  # fmt: skip
        if not isinstance(found, dict):
            raise ConnectorError("answer", "Linear answered in a shape Friday doesn't know")
        for error in found.get("errors") or []:
            code = str((error.get("extensions") or {}).get("code") or "").upper()
            if code in ("AUTHENTICATION_ERROR", "UNAUTHENTICATED"):
                raise ConnectorError("token", "Linear didn't accept the token: make a new API key and paste it again")
            if code == "RATELIMITED":
                raise ConnectorError("rate", "Linear asked Friday to slow down: it tries again later")
            raise ConnectorError("answer", f"Linear refused the request: {str(error.get('message') or '')[:160]}")
        if not isinstance(found.get("data"), dict):
            raise ConnectorError("answer", "Linear answered in a shape Friday doesn't know")
        return found["data"]

    def check(self) -> str:
        me = self.ask(ME).get("viewer") or {}
        return str(me.get("email") or me.get("name") or "your Linear")

    def read(self) -> list[Remote]:
        def page(after: str | None) -> tuple[list[Any], str | None]:
            issues = ((self.ask(MINE, after=after).get("viewer") or {}).get("assignedIssues")) or {}
            info = issues.get("pageInfo") or {}
            return issues.get("nodes") or [], info.get("endCursor") if info.get("hasNextPage") else None

        return [remote(i) for i in pages(page) if (i.get("state") or {}).get("type") not in ("completed", "canceled")]

    def write(self, external_id: str, op: Literal["done", "reopen"]) -> None:
        issue = self.ask(STATES, id=external_id).get("issue")
        if issue is None:
            return  # deleted in Linear since: nothing left to change
        states = (((issue.get("team") or {}).get("states")) or {}).get("nodes") or []
        wanted = ("completed",) if op == "done" else ("unstarted", "backlog")
        found = sorted((s for s in states if s.get("type") in wanted),
                       key=lambda s: (wanted.index(s["type"]), s.get("position") or 0))  # fmt: skip
        if not found:
            raise ConnectorError(
                "answer", f"Linear's team has no {'Done' if op == 'done' else 'Todo'} state to move it to"
            )
        if not (self.ask(MOVE, id=external_id, state=found[0]["id"]).get("issueUpdate") or {}).get("success"):
            raise ConnectorError("answer", "Linear didn't save the change")


def remote(issue: dict[str, Any]) -> Remote:
    team = (issue.get("team") or {}).get("name")
    where = f"In Linear: {issue.get('identifier')}" + (f" ({team})" if team else "") if issue.get("identifier") else ""
    return Remote(
        external_id=str(issue["id"]),
        title=str(issue.get("title") or "Untitled issue").strip(),
        due=issue.get("dueDate") or None,
        notes="\n\n".join(x for x in (str(issue.get("description") or "").strip(), where) if x),
        url=issue.get("url"),
        done=(issue.get("state") or {}).get("type") in ("completed", "canceled"),
        firm=True,
    )
