"""Canvas, by its API (C96, your choice; C107). Your school's Canvas (https://<school's Canvas>/api/v1) with an access
token you make in Canvas (Account → Settings → New access token), as a Bearer token.

Your answers (10 Nov): what comes in is anything in Canvas's planner with a due date (assignments, quizzes, graded
discussions) from four weeks back to six months ahead, not yet submitted or ticked, each with its course and points;
finishing one in Friday ticks it in Canvas's own To Do ("mark as done", which only you see; nothing is submitted),
and submitting or ticking it in Canvas is done here. And the API takes over assignments from the Canvas calendar
feed: that feed keeps bringing course events, but no longer its assignments (commands/fetching.py), and one it
already brought is adopted here (`adopt`), staying the same to-do. Canvas pages by its Link header."""

import json
import os
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar, Literal
from urllib.parse import urlsplit

from friday.core.db import rows
from friday.integrations.base import Caps, ConnectorError, Http, Remote, Transport

KINDS = ("assignment", "quiz", "discussion_topic")
BACK, AHEAD = timedelta(days=28), timedelta(days=183)
HOST = re.compile(r"^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$")


def site_of(given: str) -> str:
    """Your school's Canvas as its address: "canvas.cornell.edu" or a link into it is https://canvas.cornell.edu."""
    text = given.strip()
    host = (urlsplit(text if "//" in text else f"https://{text}").hostname or "").lower()
    if not HOST.match(host):
        raise ConnectorError("token", "Give your school's Canvas address, like canvas.yourschool.edu")
    return f"https://{host}"


def assignment_of(item: dict[str, Any]) -> str | None:
    """The assignment behind a planner item (a quiz's and a graded discussion's have one): the calendar feed's id."""
    plannable = item.get("plannable") or {}
    found = plannable.get("assignment_id") or (plannable.get("assignment") or {}).get("id")
    if found:
        return str(found)
    return str(item.get("plannable_id")) if item.get("plannable_type") == "assignment" else None


class Canvas:
    kind: ClassVar[str] = "canvas"
    name: ClassVar[str] = "Canvas"
    caps: ClassVar[Caps] = Caps(two_way=True, lengths=False, kind="Assignment", late_ok=False)
    fields: ClassVar[tuple[str, ...]] = ("site",)

    def __init__(self, token: str, config: dict[str, Any] | None = None, transport: Transport = None,
                 now: datetime | None = None):  # fmt: skip
        if not token.strip():
            raise ConnectorError("token", "No Canvas token: make one in Canvas under Account → Settings")
        self.site = site_of(str((config or {}).get("site") or ""))
        self.kept = {"site": self.site}
        self.now = now or datetime.now(UTC)
        self.items: dict[str, dict[str, Any]] = {}  # the last read, by external id: what `adopt` matches on
        base = os.environ.get("FRIDAY_API_CANVAS") or self.site  # another address: only a fake service, in tests
        self.http = Http(self.name, base + "/api/v1", {"Authorization": f"Bearer {token.strip()}"}, transport)

    def check(self) -> str:
        me = self.http.json("GET", "/users/self")
        if not isinstance(me, dict):
            raise ConnectorError("answer", "Canvas's answer about you came back in a shape Friday doesn't know")
        return f"{me.get('name') or 'you'} on {self.site.removeprefix('https://')}"

    def paged(self, path: str, params: dict[str, Any]) -> list[Any]:
        """Every page of a Canvas list, by its Link header's next (at most a hundred pages)."""
        found: list[Any] = []
        answer = self.http.call("GET", path, params=params | {"per_page": 100})
        for _ in range(100):
            try:
                page = answer.json()
            except ValueError as error:
                raise ConnectorError("answer", "Canvas answered with something Friday can't read") from error
            if not isinstance(page, list):
                raise ConnectorError("answer", "Canvas's list came back in a shape Friday doesn't know")
            found += page
            nxt = answer.links.get("next", {}).get("url")
            if not nxt:
                break
            answer = self.http.call("GET", nxt)
        return found

    def read(self) -> list[Remote]:
        start, end = (self.now - BACK).date().isoformat(), (self.now + AHEAD).date().isoformat()
        planned = self.paged("/planner/items", {"start_date": start, "end_date": end})
        self.items = {external_id(i): i for i in planned if i.get("plannable_type") in KINDS and due_of(i)}
        return [remote(i, self.site) for i in self.items.values() if not done(i)]

    def write(self, external_id: str, op: Literal["done", "reopen"]) -> None:
        kind, plannable = external_id.split(":", 1)
        marked = op == "done"
        overrides = self.paged("/planner/overrides", {})
        mine = next((o for o in overrides if o.get("plannable_type") == kind
                     and str(o.get("plannable_id")) == plannable), None)  # fmt: skip
        if mine:
            self.http.call("PUT", f"/planner/overrides/{mine['id']}", json={"marked_complete": marked})
        else:
            asked = {"plannable_type": kind, "plannable_id": plannable, "marked_complete": marked}
            self.http.call("POST", "/planner/overrides", json=asked)

    def adopt(self, conn: sqlite3.Connection, source: dict[str, Any]) -> None:
        """What the Canvas calendar feed already brought, now this source's: each assignment the feed read
        (`event-assignment-<id>`) and this read has too becomes this one's, so it stays the same to-do (C107)."""
        host = urlsplit(self.site).hostname
        found = rows(conn, "SELECT id, config FROM sources WHERE kind = 'ics' AND user_id = ?", [source["user_id"]])
        feeds = [s["id"] for s in found if is_canvas_feed(s["config"], host)]
        if not feeds:
            return
        marks = ", ".join("?" * len(feeds))
        for ext, item in self.items.items():
            assignment = assignment_of(item)
            if assignment is None or rows(
                conn, "SELECT 1 FROM raw_inputs WHERE source_id = ? AND external_id = ?", [source["id"], ext]
            ):
                continue
            conn.execute(
                f"UPDATE raw_inputs SET source_id = ?, external_id = ?, content_hash = '', status = 'new' "
                f"WHERE source_id IN ({marks}) AND (external_id = ? OR external_id LIKE ?)",
                [source["id"], ext, *feeds, f"event-assignment-{assignment}", f"event-assignment-{assignment}#%"],
            )


def is_canvas_feed(config: str | None, host: str | None) -> bool:
    """A Canvas calendar feed (…/feeds/calendars/user_….ics) on this school's Canvas."""
    url = str(json.loads(config or "{}").get("url") or "")
    parts = urlsplit(url.replace("webcal://", "https://"))
    return bool(host) and parts.hostname == host and "/feeds/calendars/" in parts.path


def takes_over(conn: sqlite3.Connection, feed: dict[str, Any]) -> bool:
    """This feed is a Canvas calendar feed whose school's Canvas API is connected: its assignments come by the API."""
    found = rows(conn, "SELECT config FROM sources WHERE kind = 'canvas' AND enabled = 1 AND user_id = ?",
                 [feed["user_id"]])  # fmt: skip
    hosts = {urlsplit(str(json.loads(s["config"] or "{}").get("site") or "")).hostname for s in found}
    return any(is_canvas_feed(feed["config"], h) for h in hosts if h)


def let_go(conn: sqlite3.Connection, feed: dict[str, Any]) -> None:
    """The feed's assignments, no longer its own: not read again, not taken as gone (nothing is dropped); the API
    adopts each it reads (`Canvas.adopt`), and one it doesn't stays in your plan as it is."""
    for r in rows(conn, "SELECT id FROM raw_inputs WHERE source_id = ? AND external_id LIKE 'event-assignment-%' "
                  "AND status != 'ignored'", [feed["id"]]):  # fmt: skip
        conn.execute("UPDATE suggestions SET status = 'superseded' WHERE raw_input_id = ? AND status = 'pending'",
                     [r["id"]])  # fmt: skip
        conn.execute("UPDATE raw_inputs SET status = 'ignored' WHERE id = ?", [r["id"]])


def external_id(item: dict[str, Any]) -> str:
    return f"{item.get('plannable_type')}:{item.get('plannable_id')}"


def due_of(item: dict[str, Any]) -> str | None:
    plannable = item.get("plannable") or {}
    return plannable.get("due_at") or (plannable.get("assignment") or {}).get("due_at") or None


def done(item: dict[str, Any]) -> bool:
    submissions = item.get("submissions") or {}
    marked = (item.get("planner_override") or {}).get("marked_complete")
    return bool(
        marked or (isinstance(submissions, dict) and (submissions.get("submitted") or submissions.get("excused")))
    )


def remote(item: dict[str, Any], site: str) -> Remote:
    plannable = item.get("plannable") or {}
    points = plannable.get("points_possible")
    course = str(item.get("context_name") or "").strip()
    said = [x for x in (course, f"{points:g} points" if isinstance(points, int | float) and points else "") if x]
    url = str(item.get("html_url") or "")
    return Remote(
        external_id=external_id(item),
        title=str(plannable.get("title") or plannable.get("name") or "Untitled assignment").strip(),
        due=due_of(item),  # UTC: the sync puts it on your clock
        notes=f"In Canvas: {' · '.join(said)}" if said else "",
        url=url if url.startswith("http") else f"{site}{url}" if url else None,
        done=done(item),
        firm=True,
    )
