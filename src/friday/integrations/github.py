"""GitHub (C96; C106). Its REST API at https://api.github.com with a fine-grained personal access token, read-only.

Your answers (10 Nov): what comes in is the open issues assigned to you and the pull requests whose review is asked
of you, in every repository the token can see (GET search/issues: `is:open is:issue assignee:@me` and `is:open is:pr
review-requested:@me`, pages of 100); Friday only reads GitHub, since closing an issue is public on a shared repo, so
an issue closed there (by you, or by a merged pull request) is done here, and so is a review you've given; finishing
one in Friday changes nothing on GitHub. The token is fine-grained: all repositories, Issues and Pull requests
read-only. GitHub keeps no due date but a milestone's, a day; an issue is a Work task, a review "Review: …"."""

import os
from typing import Any, ClassVar, Literal

from friday.integrations.base import Caps, ConnectorError, Http, Remote, Transport

API = "https://api.github.com"
TOKEN_PAGE = "https://github.com/settings/personal-access-tokens/new"
QUERIES = {
    "issue": "is:open is:issue assignee:@me archived:false",
    "review": "is:open is:pr review-requested:@me archived:false",
}
MOST = 1000  # GitHub's search gives at most a thousand results


class GitHub:
    kind: ClassVar[str] = "github"
    name: ClassVar[str] = "GitHub"
    caps: ClassVar[Caps] = Caps(two_way=False, lengths=False, kind="Work task")

    def __init__(self, token: str, config: dict[str, Any] | None = None, transport: Transport = None):
        if not token.strip():
            raise ConnectorError("token", f"No GitHub token: make a fine-grained one at {TOKEN_PAGE} and paste it here")
        base = os.environ.get("FRIDAY_API_GITHUB") or API  # another address: only a fake service, in system tests
        headers = {"Authorization": f"Bearer {token.strip()}", "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28"}  # fmt: skip
        self.http = Http(self.name, base, headers, transport)

    def check(self) -> str:
        me = self.http.json("GET", "/user")
        if not isinstance(me, dict) or not me.get("login"):
            raise ConnectorError("answer", "GitHub's answer about you came back in a shape Friday doesn't know")
        return f"@{me['login']}"

    def read(self) -> list[Remote]:
        return [remote(item, what) for what, q in QUERIES.items() for item in self.search(q)]

    def search(self, q: str) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        for page in range(1, MOST // 100 + 1):
            answer = self.http.json("GET", "/search/issues", params={"q": q, "per_page": 100, "page": page})
            if not isinstance(answer, dict) or not isinstance(answer.get("items"), list):
                raise ConnectorError("answer", "GitHub's search came back in a shape Friday doesn't know")
            found += answer["items"]
            if not answer["items"] or len(found) >= int(answer.get("total_count") or 0):
                break
        return found

    def write(self, external_id: str, op: Literal["done", "reopen"]) -> None:
        raise AssertionError("GitHub is read only (C106): nothing goes back")


def remote(item: dict[str, Any], what: str) -> Remote:
    repo = "/".join(str(item.get("repository_url") or "").split("/")[-2:])
    milestone = item.get("milestone") or {}
    title = str(item.get("title") or "Untitled").strip()
    return Remote(
        external_id=str(item["id"]),
        title=f"Review: {title}" if what == "review" else title,
        due=str(milestone["due_on"])[:10] if milestone.get("due_on") else None,  # a milestone's day
        notes=f"On GitHub: {repo}#{item.get('number')}" + (f", {milestone['title']}" if milestone.get("title") else ""),
        url=item.get("html_url"),
        done=item.get("state") == "closed",
        firm=True,
    )
