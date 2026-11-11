"""A stand-in for Notion's API (https://api.notion.com/v1, Notion-Version 2026-03-11), the parts Friday uses, as
Notion's reference has them: GET users/me (the integration's bot, its workspace), POST search filtered to data
sources (only those shared with the integration), GET data_sources/{id} (its properties), POST
data_sources/{id}/query (a filter, page_size at most 100, start_cursor, has_more and next_cursor), GET and PATCH
pages/{id}. Pages look as Notion sends them: properties by name, a title as rich text, a date {start, end,
time_zone} whose times carry the workspace's offset, a checkbox or a status {id, name, color}, `in_trash`.

Lists: "Tasks" (a Done checkbox, Due, Estimate (min)) is the one the contract drives; "Projects" (Notion's own
Status, Deadline), "Team board" (an Assignee column: a team's) and "Reading list" (nothing that says done) are there
for the glass-box tests. Its token is a personal access token unless made `personal=False` (an integration's secret,
whose bot belongs to the workspace, not to you)."""

import itertools
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from tests.integrations.kit import FakeService, Harness

PREFIX = "/v1"
VERSION = "2026-03-11"
ZONE = ZoneInfo("America/New_York")  # the workspace's: new_app's
ME = "u-maria"  # the personal token's creator


def rich(text: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": {"content": text, "link": None}, "plain_text": text, "href": None,
             "annotations": {"bold": False, "italic": False, "code": False, "color": "default"}}]  # fmt: skip


def notion_date(when: str | None) -> dict[str, Any] | None:
    """A day as itself; a local time with the workspace's offset, as Notion answers."""
    if not when:
        return None
    if "T" not in when:
        return {"start": when, "end": None, "time_zone": None}
    moment = datetime.fromisoformat(when).replace(tzinfo=ZONE)
    return {"start": moment.isoformat(timespec="milliseconds"), "end": None, "time_zone": None}


STATUS = {
    "options": [{"id": "s1", "name": "Not started", "color": "default"},
                {"id": "s2", "name": "In progress", "color": "blue"},
                {"id": "s3", "name": "Done", "color": "green"}, {"id": "s4", "name": "Dropped", "color": "gray"}],
    "groups": [{"id": "g1", "name": "To-do", "color": "gray", "option_ids": ["s1"]},
               {"id": "g2", "name": "In progress", "color": "blue", "option_ids": ["s2"]},
               {"id": "g3", "name": "Complete", "color": "green", "option_ids": ["s3", "s4"]}],
}  # fmt: skip

SOURCES: dict[str, dict[str, Any]] = {
    "ds-tasks": {"title": "Tasks", "properties": {
        "Name": {"id": "title", "type": "title", "title": {}},
        "Done": {"id": "a1", "type": "checkbox", "checkbox": {}},
        "Due": {"id": "a2", "type": "date", "date": {}},
        "Created": {"id": "a5", "type": "created_time", "created_time": {}},
        "Estimate (min)": {"id": "a3", "type": "number", "number": {"format": "number"}},
        "Tags": {"id": "a4", "type": "multi_select", "multi_select": {"options": []}},
    }},
    "ds-projects": {"title": "Projects", "properties": {
        "Project": {"id": "title", "type": "title", "title": {}},
        "Status": {"id": "b1", "type": "status", "status": STATUS},
        "Deadline": {"id": "b2", "type": "date", "date": {}},
        "Kickoff": {"id": "b3", "type": "date", "date": {}},
        "Hours": {"id": "b4", "type": "number", "number": {"format": "number"}},
    }},
    "ds-team": {"title": "Team board", "properties": {
        "Task": {"id": "title", "type": "title", "title": {}},
        "Done": {"id": "d1", "type": "checkbox", "checkbox": {}},
        "Assignee": {"id": "d2", "type": "people", "people": {}},
        "Due": {"id": "d3", "type": "date", "date": {}},
    }},
    "ds-reading": {"title": "Reading list", "properties": {
        "Title": {"id": "title", "type": "title", "title": {}},
        "Author": {"id": "c1", "type": "rich_text", "rich_text": {}},
    }},
}  # fmt: skip


class FakeNotion(FakeService):
    host = "api.notion.com"

    def __init__(
        self, token: str, page_size: int = 100, shared: tuple[str, ...] = ("ds-tasks",), personal: bool = True
    ):
        super().__init__(token)
        self.personal = personal
        self.pages: dict[str, dict[str, Any]] = {}
        self.shared = list(shared)  # the data sources shared with the integration (••• → Connections)
        self.page_size = page_size
        self.ids = itertools.count(1)

    def add(self, title: str, due: str | None = None, minutes: int | None = None, source: str = "ds-tasks",
            **extra: Any) -> str:  # fmt: skip
        page_id = f"2a{next(self.ids):06d}-0000-4000-8000-{len(self.pages):012d}"
        names = SOURCES[source]["properties"]
        title_prop = next(n for n, p in names.items() if p["type"] == "title")
        props: dict[str, Any] = {title_prop: {"id": "title", "type": "title", "title": rich(title)}}
        if source == "ds-tasks":
            props |= {"Done": {"id": "a1", "type": "checkbox", "checkbox": False},
                      "Due": {"id": "a2", "type": "date", "date": notion_date(due)},
                      "Estimate (min)": {"id": "a3", "type": "number", "number": minutes},
                      "Created": {"id": "a5", "type": "created_time",
                                  "created_time": "2026-11-01T12:00:00.000Z"}}  # fmt: skip
        if source == "ds-team":
            props |= {"Done": {"id": "d1", "type": "checkbox", "checkbox": False},
                      "Assignee": {"id": "d2", "type": "people",
                                   "people": [{"object": "user", "id": who} for who in extra.get("people", [])]},
                      "Due": {"id": "d3", "type": "date", "date": notion_date(due)}}  # fmt: skip
        if source == "ds-projects":
            props |= {"Status": {"id": "b1", "type": "status", "status": STATUS["options"][extra.get("status", 0)]},
                      "Deadline": {"id": "b2", "type": "date", "date": extra.get("date", notion_date(due))},
                      "Kickoff": {"id": "b3", "type": "date", "date": notion_date("2026-10-01")},
                      "Hours": {"id": "b4", "type": "number", "number": extra.get("hours")}}  # fmt: skip
        self.pages[page_id] = {
            "object": "page", "id": page_id, "created_time": "2026-11-01T12:00:00.000Z",
            "last_edited_time": "2026-11-01T12:00:00.000Z", "in_trash": False, "is_locked": False,
            "parent": {"type": "data_source_id", "data_source_id": source, "database_id": f"db-{source}"},
            "url": f"https://www.notion.so/{title.replace(' ', '-')}-{page_id.replace('-', '')}", "public_url": None,
            "properties": props,
        }  # fmt: skip
        return page_id

    def source(self, source_id: str) -> dict[str, Any]:
        s = SOURCES[source_id]
        return {"object": "data_source", "id": source_id, "title": rich(s["title"]), "properties": s["properties"],
                "parent": {"type": "database_id", "database_id": f"db-{source_id}"}, "in_trash": False}  # fmt: skip

    def path(self, request: httpx.Request) -> str:
        return request.url.path.removeprefix(PREFIX)

    def writes(self) -> list[str]:
        """Only what changes Notion: search and query are POSTs that read."""
        return [w for w in super().writes() if not w.startswith("POST ")]

    def respond(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("notion-version") != VERSION:
            return httpx.Response(400, json={"object": "error", "code": "missing_version", "message": "Notion-Version"})
        path, method = self.path(request), request.method
        parts = path.strip("/").split("/")
        if method == "GET" and path == "/users/me":
            owner = (
                {"type": "user", "user": {"object": "user", "id": ME}}
                if self.personal
                else {"type": "workspace", "workspace": True}
            )
            return httpx.Response(200, json={"object": "user", "id": "bot-1", "type": "bot", "name": "Friday",
                                             "bot": {"owner": owner, "workspace_name": "Maria's Notion"}})  # fmt: skip
        if method == "POST" and path == "/search":
            body = self.body(request)
            assert body["filter"] == {"property": "object", "value": "data_source"}, body
            return self.paged([self.source(s) for s in self.shared], body)
        if parts[0] == "data_sources" and len(parts) >= 2:
            if parts[1] not in self.shared:
                return httpx.Response(404, json={"object": "error", "code": "object_not_found"})
            if method == "GET" and len(parts) == 2:
                return httpx.Response(200, json=self.source(parts[1]))
            if method == "POST" and parts[2:] == ["query"]:
                body = self.body(request)
                found = [p for p in self.pages.values()
                         if p["parent"]["data_source_id"] == parts[1] and not p["in_trash"]
                         and matches(p, body.get("filter"))]  # fmt: skip
                return self.paged(found, body)
        if parts[0] == "pages" and len(parts) == 2:
            page = self.pages.get(parts[1])
            if page is None or page["parent"]["data_source_id"] not in self.shared:
                return httpx.Response(404, json={"object": "error", "code": "object_not_found"})
            if method == "PATCH":
                for name, value in self.body(request)["properties"].items():
                    if "status" in value:
                        value = {"status": next(o for o in STATUS["options"] if o["name"] == value["status"]["name"])}
                    page["properties"][name].update(value)
            return httpx.Response(200, json=page)
        return httpx.Response(404, json={"object": "error", "code": "invalid_request_url", "message": path})

    def paged(self, results: list[Any], body: dict[str, Any]) -> httpx.Response:
        size = min(int(body.get("page_size", 100)), 100, self.page_size)
        start = int(body.get("start_cursor") or 0)
        more = start + size < len(results)
        return httpx.Response(200, json={"object": "list", "results": results[start : start + size],
                                         "next_cursor": str(start + size) if more else None, "has_more": more,
                                         "type": "page_or_data_source", "page_or_data_source": {}})  # fmt: skip


def matches(page: dict[str, Any], f: dict[str, Any] | None) -> bool:
    if not f:
        return True
    if "and" in f:
        return all(matches(page, g) for g in f["and"])
    value = page["properties"][f["property"]]
    if "checkbox" in f:
        return value["checkbox"] == f["checkbox"]["equals"]
    if "people" in f:
        return f["people"]["contains"] in [p["id"] for p in value["people"]]
    if "status" in f:
        return value["status"]["name"] != f["status"]["does_not_equal"]
    raise AssertionError(f"a filter the stand-in doesn't know: {f}")


def _set(fake: FakeNotion, page_id: str, prop: str, value: dict[str, Any]) -> None:
    fake.pages[page_id]["properties"][prop].update(value)


HARNESS = Harness(
    kind="notion",
    token="ntn_stand-in-not-a-real-secret",  # not shaped like a real one: no scanner takes it for a leak
    fake=FakeNotion,
    add=lambda fake, title, due=None, minutes=None: fake.add(title, due, minutes),
    move=lambda fake, page_id, due: _set(fake, page_id, "Due", {"date": notion_date(due)}),
    rename=lambda fake, page_id, title: _set(fake, page_id, "Name", {"title": rich(title)}),
    finish=lambda fake, page_id: _set(fake, page_id, "Done", {"checkbox": True}),
    is_done=lambda fake, page_id: fake.pages[page_id]["properties"]["Done"]["checkbox"],
    two_way=True,
    lengths=True,
)
