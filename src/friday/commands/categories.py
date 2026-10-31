"""An event's category, and who said (31 Oct: "the way you classified was just based on string? this seems like a very
fragile way to do this"; of the ways offered, clues, with Claude asked only what they leave unclear, for cost).

Yours, when you chose one for its title (`event_category`); else your always-words' (a category's pattern, now
optional); else Claude's, asked once a title with its clues as context (`commands/rating.py`, a call Friday makes for
the skip ratings anyway); else the clues', when they're sure (`core/clues.py`). When the event most like it is one you
chose a category for, the clues come before Claude: what you choose spreads to the events like it. Unsure, the clues'
guess is offered on the card, never painted.

An event on a calendar that doesn't count as busy, others' room bookings, isn't guessed at (31 Oct: Library Rooms'
"Rohan: Olin 603" came out Social, by the friend's name): it wears its calendar's colour unless you choose for it.
"""

import hashlib
import re
import sqlite3
from dataclasses import dataclass

from friday.commands.registry import Ctx
from friday.core.calendars import Category, CategorySettings, calendar_counts, category_of, rating_key
from friday.core.clues import Clues, clues_of, known_from
from friday.core.db import one, rows
from friday.planner.store import event_links, kv_get, load_settings, settings_version

CHOICES = "event_categories"  # kv: {title key: a category's name, or "" for none}
SENDER = re.compile(r"^From:.*?@([\w.-]+)", re.MULTILINE)


@dataclass(frozen=True)
class Placed:
    category: Category | None
    by: str | None = None  # "you", "always", "similar", "claude"
    like: str | None = None  # the event it's like, when the clues decided
    hint: str | None = None  # the clues' unsure guess: offered, not painted


def senders(conn: sqlite3.Connection, user_id: int) -> dict[int, str]:
    """Events made from an email, by its sender's domain ("janestreet.com")."""
    found = rows(
        conn,
        "SELECT s.item_id, r.content FROM suggestions s JOIN raw_inputs r ON r.id = s.raw_input_id "
        "JOIN sources so ON so.id = r.source_id WHERE s.user_id = ? AND so.kind = 'gmail' AND s.item_id IS NOT NULL",
        [user_id],
    )
    return {r["item_id"]: m.group(1).lower() for r in found if (m := SENDER.search(r["content"][:2000]))}


def label(
    key: str,
    title: str,
    chosen: dict[str, str],
    categories: CategorySettings,
    rated: dict[str, dict[str, str]],
    guessed: bool = True,
) -> tuple[str | None, str]:
    """A title's category for the clues to learn from, and who said: you, your words, or Claude (not for an event
    that isn't `guessed` at)."""
    named = {c.name for c in categories.categories}
    if key in chosen:
        return (chosen[key] if chosen[key] in named else None), "you"
    rule = category_of(title, categories)
    if rule is not None:
        return rule.name, "always"
    guess = (rated.get(key) or {}).get("category") if guessed else None
    return (guess if guess in named else None), "claude"


def build(conn: sqlite3.Connection, user_id: int, categories: CategorySettings) -> Clues:
    chosen = kv_get(conn, CHOICES, {}, user_id) or {}
    rated = kv_get(conn, "event_ratings", {}, user_id) or {}
    links = event_links(conn, user_id)
    sent = senders(conn, user_id)
    busy = load_settings(conn, user_id)["busy"]
    found = []
    for r in rows(
        conn,
        "SELECT id, title, location FROM items WHERE user_id = ? AND when_kind = 'fixed' AND status != 'dropped'",
        [user_id],
    ):
        key = rating_key(r["title"])
        calendar = links[r["id"]].calendar if r["id"] in links else None
        category, by = label(key, r["title"], chosen, categories, rated, calendar_counts(calendar, busy))
        found.append((key, r["title"], clues_of(r["title"], calendar, r["location"], sent.get(r["id"])), category, by))
    return Clues(known_from(found))


_MODELS: dict[tuple[object, ...], Clues] = {}


def fingerprint(conn: sqlite3.Connection, user_id: int) -> tuple[object, ...]:
    """What the clues are learned from, cheaply: kept between requests until an event, a choice, a rating or the
    settings change."""
    path = conn.execute("PRAGMA database_list").fetchone()[2]
    items = one(
        conn,
        "SELECT count(*) AS n, max(updated_utc) AS u, total(id) AS s FROM items WHERE user_id = ? "
        "AND when_kind = 'fixed'",
        [user_id],
    )
    raw = one(conn, "SELECT count(*) AS n, max(id) AS m FROM raw_inputs WHERE user_id = ?", [user_id])
    said = rows(
        conn, "SELECT value FROM kv WHERE user_id = ? AND key IN ('event_ratings', ?) ORDER BY key", [user_id, CHOICES]
    )
    digest = hashlib.sha1("|".join(r["value"] for r in said).encode()).hexdigest()
    counts = tuple(items.values()) if items else ()
    seen = tuple(raw.values()) if raw else ()
    return (path, user_id, counts, seen, settings_version(conn, user_id), digest)


def clues_for(conn: sqlite3.Connection, user_id: int, categories: CategorySettings) -> Clues:
    key = fingerprint(conn, user_id)
    if key not in _MODELS:
        if len(_MODELS) >= 8:
            _MODELS.clear()
        _MODELS[key] = build(conn, user_id, categories)
    return _MODELS[key]


def model(ctx: Ctx) -> Clues:
    if "clues" not in ctx.memo:
        ctx.memo["clues"] = clues_for(ctx.conn, ctx.user_id, ctx.settings["categories"])
    found: Clues = ctx.memo["clues"]
    return found


def told(
    conn: sqlite3.Connection, user_id: int, categories: CategorySettings, events: list[dict[str, object]]
) -> dict[str, str]:
    """What Friday knows of each event's title, for Claude to weigh: its calendar, its place, the sender, the event
    it's most like and that one's category. Keyed by title."""
    clues = clues_for(conn, user_id, categories)
    links = event_links(conn, user_id)
    sent = senders(conn, user_id)
    out: dict[str, str] = {}
    for e in events:
        item_id, title, location = e["id"], str(e["title"]), e.get("location")
        calendar = links[item_id].calendar if isinstance(item_id, int) and item_id in links else None
        sender = sent.get(item_id) if isinstance(item_id, int) else None
        verdict = clues.judge(clues_of(title, calendar, str(location or ""), sender), skip=rating_key(title))
        like = next((k for k in clues.known if k.title == verdict.like), None) if verdict.like else None
        parts = [
            f"calendar: {calendar}" if calendar else "",
            f"place: {location}" if location else "",
            f"from: {sender}" if sender else "",
            f'like "{like.title}" ({like.category})' if like else "",
        ]
        if any(parts):
            out[title] = "; ".join(p for p in parts if p)
    return out


def place(ctx: Ctx, item_id: int | None, title: str, calendar: str | None, location: str | None) -> Placed:
    """An event's category, and who said."""
    categories = ctx.settings["categories"]
    named = {c.name: c for c in reversed(categories.categories)}  # the first of two with one name
    key = rating_key(title)
    if "event_choices" not in ctx.memo:
        ctx.memo["event_choices"] = kv_get(ctx.conn, CHOICES, {}, ctx.user_id) or {}
        ctx.memo["event_ratings"] = kv_get(ctx.conn, "event_ratings", {}, ctx.user_id) or {}
        ctx.memo["senders"] = senders(ctx.conn, ctx.user_id)
        ctx.memo["placed"] = {}
    memo: dict[tuple[object, ...], Placed] = ctx.memo["placed"]
    sender = ctx.memo["senders"].get(item_id)
    asked = (key, calendar, location, sender)
    if asked in memo:
        return memo[asked]
    chosen = ctx.memo["event_choices"].get(key)
    rule = category_of(title, categories)
    if chosen is not None:
        found = Placed(named.get(chosen), "you")
    elif rule is not None:
        found = Placed(rule, "always")
    elif not calendar_counts(calendar, ctx.settings["busy"]):
        found = Placed(None)  # others' bookings: its calendar's colour
    else:
        verdict = model(ctx).judge(clues_of(title, calendar, location, sender), skip=key)
        clued = named.get(verdict.category or "") if verdict.sure else None
        guess = named.get((ctx.memo["event_ratings"].get(key) or {}).get("category") or "")
        if clued is not None and verdict.like_by == "you":
            found = Placed(clued, "similar", verdict.like)
        elif guess is not None:
            found = Placed(guess, "claude")
        elif clued is not None:
            found = Placed(clued, "similar", verdict.like)
        else:
            found = Placed(None, hint=verdict.category if verdict.category in named else None)
    memo[asked] = found
    return found
