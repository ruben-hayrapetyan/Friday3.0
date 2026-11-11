"""A stand-in for GitHub's REST API (https://api.github.com), the parts Friday reads, as GitHub's reference has them:
GET user, GET search/issues (`q`, per_page at most 100, page; `total_count`, `items`). Items look as search sends
them: `id`, `number`, `title`, `state`, `html_url`, `repository_url`, `milestone` {title, due_on}, `assignees`, and a
`pull_request` key on pull requests. The qualifiers Friday sends are understood: is:open, is:issue / is:pr,
assignee:@me, review-requested:@me, archived:false."""

import itertools
from typing import Any

import httpx

from tests.integrations.kit import FakeService, Harness

ME = "maria-l"


class FakeGitHub(FakeService):
    host = "api.github.com"

    def __init__(self, token: str, page_size: int = 100):
        super().__init__(token)
        self.items: dict[str, dict[str, Any]] = {}
        self.page_size = page_size
        self.ids = itertools.count(2_400_000_001)
        self.numbers = itertools.count(1)

    def add(self, title: str, due: str | None = None, assignee: str | None = ME, pr: bool = False,
            reviewer: str | None = None, repo: str = "acme/shop") -> str:  # fmt: skip
        item_id, number = next(self.ids), next(self.numbers)
        milestone = {"title": "v2.0", "due_on": f"{due[:10]}T07:00:00Z"} if due else None
        self.items[str(item_id)] = {
            "id": item_id, "node_id": f"I_{item_id}", "number": number, "title": title, "state": "open",
            "html_url": f"https://github.com/{repo}/{'pull' if pr else 'issues'}/{number}",
            "repository_url": f"https://api.github.com/repos/{repo}", "milestone": milestone,
            "assignees": [{"login": assignee}] if assignee else [], "reviewers": [reviewer] if reviewer else [],
            **({"pull_request": {"url": f"https://api.github.com/repos/{repo}/pulls/{number}"}} if pr else {}),
        }  # fmt: skip
        return str(item_id)

    def respond(self, request: httpx.Request) -> httpx.Response:
        assert request.headers.get("x-github-api-version") == "2022-11-28", request.headers
        path, params = request.url.path, request.url.params
        if request.method == "GET" and path == "/user":
            return httpx.Response(200, json={"login": ME, "id": 101, "type": "User"})
        if request.method == "GET" and path == "/search/issues":
            q = set(params["q"].split())
            assert {"is:open", "archived:false"} <= q, q
            found = [i for i in self.items.values() if i["state"] == "open" and matches(i, q)]
            size = min(int(params.get("per_page", 30)), 100, self.page_size)
            page = int(params.get("page", 1))
            shown = [{k: v for k, v in i.items() if k != "reviewers"} for i in found[(page - 1) * size : page * size]]
            return httpx.Response(200, json={"total_count": len(found), "incomplete_results": False, "items": shown})
        return httpx.Response(404, json={"message": "Not Found"})


def matches(item: dict[str, Any], q: set[str]) -> bool:
    is_pr = "pull_request" in item
    if "is:issue" in q and is_pr or "is:pr" in q and not is_pr:
        return False
    if "assignee:@me" in q and ME not in [a["login"] for a in item["assignees"]]:
        return False
    return not ("review-requested:@me" in q and ME not in item["reviewers"])


HARNESS = Harness(
    kind="github",
    token="github_pat_stand-in-not-a-real-token",  # not shaped like a real one: no scanner takes it for a leak
    fake=FakeGitHub,
    add=lambda fake, title, due=None, minutes=None: fake.add(title, due),
    move=lambda fake, item, due: fake.items[item].update(milestone={"title": "v2.0", "due_on": f"{due}T07:00:00Z"}),
    rename=lambda fake, item, title: fake.items[item].update(title=title),
    finish=lambda fake, item: fake.items[item].update(state="closed"),
    is_done=lambda fake, item: fake.items[item]["state"] == "closed",
    two_way=False,
    lengths=False,
    times=False,
)
