"""Notion (C96, your choice: both ways; C101). Its API at https://api.notion.com/v1, Notion-Version 2026-03-11 (a
database holds data sources; `archived` is `in_trash`), with an internal integration's secret as a Bearer token.

Your answers (10 Nov): the box walks you through a personal access token (it sees what you see); an integration's
secret works the same, seeing only the databases shared with it. Every database that looks like a to-do list is
offered in the box, each with a switch (`config["lists"]`): one with a person column (Assignee, Owner…) is a team's,
off until you switch it on, and then only pages with you in that column are read; your own lists start on.

A to-do list has a title, and a Done checkbox or a Status (Notion's own, whose Complete group means done); its due is
the date property named like one (Due, Deadline, Do date, Date…), else its only date; its length a number named in
minutes or hours ("Estimate (min)", "Hours"). Open pages come from POST data_sources/{id}/query, filtered to not done
(and to you); done or opened again here ticks the checkbox, or sets the Status to the first of its Complete (or To-do)
options, by PATCH pages/{id}. A page is known as "<list id>/<page id>", so a list switched off can let go of exactly
its own to-dos."""

import contextlib
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from friday.integrations.base import Caps, ConnectorError, Http, Remote, Transport, pages

API = "https://api.notion.com/v1"
VERSION = "2026-03-11"
TOKEN_PAGE = "https://www.notion.so/developers/tokens"
DONE_NAMES = ("done", "complete", "completed", "finished", "checked", "check")
DUE_NAMES = ("due", "deadline", "due date", "do date", "date", "when", "due on", "by")
PEOPLE_NAMES = (
    "assignee",
    "assignees",
    "assigned to",
    "assigned",
    "owner",
    "owners",
    "person",
    "people",
    "responsible",
    "who",
    "dri",
)
SHARE = "with an integration's secret, open your to-do database in Notion, then ••• → Connections → add it"


@dataclass(frozen=True)
class Done:
    """How a list says done: its checkbox, or its Status's Complete options (and the To-do one to open it again)."""

    prop: str
    kind: Literal["checkbox", "status"]
    complete: tuple[str, ...] = ()
    to_do: str | None = None


@dataclass(frozen=True)
class TodoList:
    id: str
    name: str
    title: str  # the title property's name
    done: Done
    due: str | None = None
    length: tuple[str, int] | None = None  # (property, minutes per unit)
    people: str | None = None  # its person column: a team's list, read for your pages only

    @property
    def team(self) -> bool:
        return self.people is not None


class Notion:
    kind: ClassVar[str] = "notion"
    name: ClassVar[str] = "Notion"
    caps: ClassVar[Caps] = Caps(two_way=True, lengths=True, lists=True)

    def __init__(self, token: str, config: dict[str, Any] | None = None, transport: Transport = None):
        if not token.strip():
            raise ConnectorError("token", f"No Notion token: make one at {TOKEN_PAGE} and paste it here")
        self.chosen: dict[str, bool] = dict((config or {}).get("lists") or {})
        base = os.environ.get("FRIDAY_API_NOTION") or API  # another address: only a fake service, in system tests
        headers = {"Authorization": f"Bearer {token.strip()}", "Notion-Version": VERSION}
        self.http = Http(self.name, base, headers, transport)

    def check(self) -> str:
        """The token's workspace, and how many to-do lists it can see (or that it can see none yet)."""
        workspace = (self.me().get("bot") or {}).get("workspace_name") or "your Notion"
        lists = self.lists()
        if not lists:
            return f"{workspace}, with no to-do list Friday can see yet ({SHARE})"
        return f"{workspace}, {len(lists)} to-do list{'' if len(lists) == 1 else 's'}: choose which in its box"

    def me(self) -> dict[str, Any]:
        found = self.http.json("GET", "/users/me")
        return found if isinstance(found, dict) else {}

    def my_id(self) -> str | None:
        """You, for "assigned to you": a personal token's creator; an integration's secret has no one (None)."""
        me = self.me()
        if me.get("type") == "person":
            return str(me["id"])
        owner = (me.get("bot") or {}).get("owner") or {}
        return str(owner["user"]["id"]) if owner.get("type") == "user" and owner.get("user") else None

    def on(self, t: TodoList) -> bool:
        """Read now: as you switched it, else your own lists on and a team's off."""
        return self.chosen.get(t.id, not t.team)

    def lists(self) -> list[TodoList]:
        """Every data source shared with the integration that's a to-do list."""

        def page(cursor: str | None) -> tuple[list[Any], str | None]:
            body: dict[str, Any] = {"filter": {"property": "object", "value": "data_source"}, "page_size": 100}
            found = self.http.json("POST", "/search", json=body | ({"start_cursor": cursor} if cursor else {}))
            return listed(found, "shared databases"), found.get("next_cursor") if found.get("has_more") else None

        made = (todo_list(d) for d in pages(page) if not d.get("in_trash"))
        return [t for t in made if t is not None]

    def read(self) -> list[Remote]:
        lists = self.lists()
        if not lists:
            raise ConnectorError("access", f"Friday can't see a to-do list in your Notion: {SHARE}")
        reading = [t for t in lists if self.on(t)]
        me = self.my_id() if any(t.team for t in reading) else None
        return [r for t in reading for r in self.open_in(t, me)]

    def open_in(self, t: TodoList, me: str | None = None) -> list[Remote]:
        wanted = not_done(t.done)
        if t.people and me:
            wanted = {"and": [wanted, {"property": t.people, "people": {"contains": me}}]}

        def page(cursor: str | None) -> tuple[list[Any], str | None]:
            body: dict[str, Any] = {"filter": wanted, "page_size": 100}
            found = self.http.json("POST", f"/data_sources/{t.id}/query",
                                   json=body | ({"start_cursor": cursor} if cursor else {}))  # fmt: skip
            return listed(found, f"“{t.name}”"), found.get("next_cursor") if found.get("has_more") else None

        return [remote(p, t) for p in pages(page) if not p.get("in_trash") and not is_done(p, t.done)]

    def write(self, external_id: str, op: Literal["done", "reopen"]) -> None:
        source, page_id = external_id.split("/", 1)
        page = self.http.json("GET", f"/pages/{page_id}")
        if page.get("in_trash"):
            return  # deleted in Notion since: nothing left to change
        t = todo_list(self.http.json("GET", f"/data_sources/{source}"))
        if t is None:
            raise ConnectorError("answer", "That Notion page's list no longer has a Done checkbox or a Status")
        self.http.call("PATCH", f"/pages/{page_id}", json={"properties": {t.done.prop: done_value(t.done, op)}})


def listed(found: Any, what: str) -> list[Any]:
    if not isinstance(found, dict) or not isinstance(found.get("results"), list):
        raise ConnectorError("answer", f"Notion's list of {what} came back in a shape Friday doesn't know")
    return found["results"]


def plain(rich: list[dict[str, Any]] | None) -> str:
    return "".join(str(r.get("plain_text") or "") for r in rich or []).strip()


def named(props: dict[str, Any], kind: str, names: tuple[str, ...]) -> str | None:
    """The property of this type whose name is first in `names` (case and spacing aside); else the only one."""
    of = [n for n, p in props.items() if p.get("type") == kind]
    by = {re.sub(r"[\s_-]+", " ", n.strip().lower()): n for n in of}
    for wanted in names:
        if wanted in by:
            return by[wanted]
    return of[0] if len(of) == 1 else None


def todo_list(source: dict[str, Any]) -> TodoList | None:
    """A data source as a to-do list, or None when it isn't one (no title, or nothing that says done)."""
    props: dict[str, Any] = source.get("properties") or {}
    title = next((n for n, p in props.items() if p.get("type") == "title"), None)
    done = done_of(props)
    if title is None or done is None:
        return None
    return TodoList(
        id=str(source["id"]),
        name=plain(source.get("title")) or "Untitled list",
        title=title,
        done=done,
        due=named(props, "date", DUE_NAMES),
        length=length_of(props),
        people=named(props, "people", PEOPLE_NAMES),
    )


def done_of(props: dict[str, Any]) -> Done | None:
    box = named(props, "checkbox", DONE_NAMES)
    if box:
        return Done(box, "checkbox")
    for name, p in props.items():
        if p.get("type") != "status":
            continue
        options = {o["id"]: o["name"] for o in (p.get("status") or {}).get("options", [])}
        groups = {str(g.get("name", "")).lower(): [options[i] for i in g.get("option_ids", []) if i in options]
                  for g in (p.get("status") or {}).get("groups", [])}  # fmt: skip
        complete = tuple(groups.get("complete", []))
        if complete:
            to_do = (groups.get("to-do") or groups.get("to do") or [None])[0]
            return Done(name, "status", complete, to_do)
    return None


def length_of(props: dict[str, Any]) -> tuple[str, int] | None:
    for name, p in props.items():
        if p.get("type") != "number":
            continue
        said = name.lower()
        if re.search(r"\bmin(ute)?s?\b|\(min\)", said):
            return name, 1
        if re.search(r"\b(hours?|hrs?)\b", said):
            return name, 60
    return None


def not_done(d: Done) -> dict[str, Any]:
    if d.kind == "checkbox":
        return {"property": d.prop, "checkbox": {"equals": False}}
    each = [{"property": d.prop, "status": {"does_not_equal": c}} for c in d.complete]
    return each[0] if len(each) == 1 else {"and": each}


def is_done(page: dict[str, Any], d: Done) -> bool:
    value = (page.get("properties") or {}).get(d.prop) or {}
    if d.kind == "checkbox":
        return bool(value.get("checkbox"))
    return ((value.get("status") or {}).get("name")) in d.complete


def done_value(d: Done, op: Literal["done", "reopen"]) -> dict[str, Any]:
    if d.kind == "checkbox":
        return {"checkbox": op == "done"}
    name = d.complete[0] if op == "done" else d.to_do
    if name is None:
        raise ConnectorError("answer", f"Notion's “{d.prop}” has no To-do option to open it again with")
    return {"status": {"name": name}}


def remote(page: dict[str, Any], t: TodoList) -> Remote:
    props = page.get("properties") or {}
    number = (props.get(t.length[0]) or {}).get("number") if t.length else None
    return Remote(
        external_id=f"{t.id}/{page['id']}",
        title=plain((props.get(t.title) or {}).get("title")) or "Untitled",
        due=due_of((props.get(t.due) or {}).get("date") if t.due else None),
        minutes=round(number * t.length[1]) if t.length and isinstance(number, int | float) and number > 0 else None,
        notes=f"In Notion: {t.name}",
        url=page.get("url"),
        done=is_done(page, t.done),
        firm=True,
    )


def due_of(date: dict[str, Any] | None) -> str | None:
    """A Notion date as Friday reads it: a range's end (it's due when it ends); a day as it is; a time with its offset
    (Notion's own, or its `time_zone`), which the sync puts on your clock."""
    if not date:
        return None
    when = str(date.get("end") or date.get("start") or "")
    if not when:
        return None
    if "T" not in when:
        return when[:10]
    moment = datetime.fromisoformat(when.replace("Z", "+00:00"))
    if moment.tzinfo is None and date.get("time_zone"):
        with contextlib.suppress(ZoneInfoNotFoundError):
            moment = moment.replace(tzinfo=ZoneInfo(str(date["time_zone"])))
    return moment.isoformat(timespec="minutes")
