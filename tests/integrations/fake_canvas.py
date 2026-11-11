"""A stand-in for a school's Canvas API (https://canvas.cornell.edu/api/v1), the parts Friday uses, as Instructure's
reference has them: GET users/self, GET planner/items (start_date, end_date, per_page; pages by the Link header's
rel="next"), GET planner/overrides, POST planner/overrides and PUT planner/overrides/{id} (`marked_complete`).
Planner items look as Canvas sends them: `plannable_id`, `plannable_type` (assignment, quiz, discussion_topic,
calendar_event, planner_note…), `plannable` {id, title, due_at (UTC), points_possible, assignment_id for a quiz},
`planner_override` {id, marked_complete} or null, `submissions` {submitted, excused, graded…} or false, `html_url`
(a path), `context_name` (the course). A due picked as a day in Canvas is 11:59pm that day, your time."""

import itertools
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from tests.integrations.kit import FakeService, Harness

PREFIX = "/api/v1"
SITE = "canvas.cornell.edu"
ZONE = ZoneInfo("America/New_York")  # new_app's


def canvas_due(when: str | None) -> str | None:
    if not when:
        return None
    local = (
        datetime.fromisoformat(when) if "T" in when else datetime.combine(datetime.fromisoformat(when), time(23, 59))
    )
    return local.replace(tzinfo=ZONE).astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeCanvas(FakeService):
    host = SITE

    def __init__(self, token: str, page_size: int = 100):
        super().__init__(token)
        self.items: dict[str, dict[str, Any]] = {}
        self.overrides: dict[int, dict[str, Any]] = {}
        self.page_size = page_size
        self.ids = itertools.count(51_001)
        self.override_ids = itertools.count(1)

    def add(self, title: str, due: str | None = None, kind: str = "assignment", course: str = "CS 2110",
            points: float | None = 10, assignment: int | None = None) -> str:  # fmt: skip
        plannable_id = next(self.ids)
        plannable: dict[str, Any] = {"id": plannable_id, "title": title, "due_at": canvas_due(due),
                                     "points_possible": points}  # fmt: skip
        if kind == "quiz":
            plannable["assignment_id"] = assignment or plannable_id + 900_000
        path = {"assignment": "assignments", "quiz": "quizzes", "discussion_topic": "discussion_topics"}.get(kind, "x")
        key = f"{kind}:{plannable_id}"
        self.items[key] = {
            "plannable_id": plannable_id, "plannable_type": kind, "plannable": plannable, "planner_override": None,
            "submissions": {"submitted": False, "excused": False, "graded": False, "late": False, "missing": False}
            if kind != "calendar_event" else False,
            "html_url": f"/courses/301/{path}/{plannable_id}", "context_name": course, "course_id": 301,
            "plannable_date": plannable["due_at"],
        }  # fmt: skip
        return key

    def mark(self, key: str, done: bool) -> None:
        item = self.items[key]
        o = item["planner_override"]
        if o is None:
            o = {"id": next(self.override_ids), "plannable_type": item["plannable_type"],
                 "plannable_id": item["plannable_id"], "marked_complete": done, "dismissed": False}  # fmt: skip
            self.overrides[o["id"]] = o
            item["planner_override"] = o
        o["marked_complete"] = done

    def path(self, request: httpx.Request) -> str:
        return request.url.path.removeprefix(PREFIX)

    def writes(self) -> list[str]:
        return [f"{r.method} {self.path(r)}" for r in self.requests if r.method in ("POST", "PUT")]

    def paged(self, request: httpx.Request, found: list[Any]) -> httpx.Response:
        size = min(int(request.url.params.get("per_page", 10)), 100, self.page_size)
        page = int(request.url.params.get("page", 1))
        headers = {}
        if page * size < len(found):
            nxt = request.url.copy_merge_params({"page": page + 1})
            headers["Link"] = f'<{nxt}>; rel="next", <{request.url.copy_merge_params({"page": 1})}>; rel="first"'
        return httpx.Response(200, json=found[(page - 1) * size : page * size], headers=headers)

    def respond(self, request: httpx.Request) -> httpx.Response:
        path, method = self.path(request), request.method
        if method == "GET" and path == "/users/self":
            return httpx.Response(200, json={"id": 4401, "name": "Maria Lopez", "short_name": "Maria"})
        if method == "GET" and path == "/planner/items":
            assert {"start_date", "end_date"} <= set(request.url.params), request.url  # a window, as Friday asks
            return self.paged(request, list(self.items.values()))
        if method == "GET" and path == "/planner/overrides":
            return self.paged(request, list(self.overrides.values()))
        body = self.body(request)
        if method == "POST" and path == "/planner/overrides":
            key = f"{body['plannable_type']}:{body['plannable_id']}"
            if key not in self.items:
                return httpx.Response(404, json={"errors": [{"message": "The specified resource does not exist."}]})
            self.mark(key, bool(body["marked_complete"]))
            return httpx.Response(200, json=self.items[key]["planner_override"])
        parts = path.strip("/").split("/")
        if method == "PUT" and parts[:2] == ["planner", "overrides"] and len(parts) == 3:
            o = self.overrides.get(int(parts[2]))
            if o is None:
                return httpx.Response(404, json={"errors": [{"message": "The specified resource does not exist."}]})
            o["marked_complete"] = bool(body["marked_complete"])
            return httpx.Response(200, json=o)
        return httpx.Response(404, json={"errors": [{"message": f"No {method} {path}"}]})


def _finish(fake: FakeCanvas, key: str) -> None:
    fake.items[key]["submissions"]["submitted"] = True


def _is_done(fake: FakeCanvas, key: str) -> bool:
    item = fake.items[key]
    return bool((item["planner_override"] or {}).get("marked_complete") or item["submissions"]["submitted"])


HARNESS = Harness(
    kind="canvas",
    token="7~stand-in-not-a-real-token",  # not shaped like a real one: no scanner takes it for a leak
    fake=FakeCanvas,
    add=lambda fake, title, due=None, minutes=None: fake.add(title, due or "2026-11-30"),  # Canvas: dated ones only
    move=lambda fake, key, due: fake.items[key]["plannable"].update(due_at=canvas_due(due)),
    rename=lambda fake, key, title: fake.items[key]["plannable"].update(title=title),
    finish=_finish,
    is_done=_is_done,
    two_way=True,
    lengths=False,
    fields={"site": SITE},
)
