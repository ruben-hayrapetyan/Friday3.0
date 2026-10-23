"""The sync job (DESIGN §22.1–22.6): read the sources that are due, store what is new, and turn it into
suggestions. Feeds and Google calendars go through fixed rules (`ingest/ics.py`); documents and mail
(`commands/mail.py`) through the LLM (`ingest/extract.py`) within the day's budget. A trusted source's fixed
events go straight in, as `sync:<source>`, logged and undoable; so does dropping one that disappeared or that you
declined. The server's job loop runs this every minute; the simulator may too.
"""

import json
import sqlite3
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from friday.commands.inbox import record_spend, spend
from friday.commands.mail import read_mail
from friday.commands.suggesting import suggest, take
from friday.core.db import one, rows
from friday.core.integrations import GcalSettings
from friday.core.settings import minutes_of
from friday.core.time import format_utc, parse_utc, planning_date
from friday.ingest import extract, ics, llm
from friday.ingest.ics import Found
from friday.planner.store import area_names, kv_get, kv_set, load_settings
from friday.sync import gcal, google_auth

Fetch = Callable[[str], str]
FAILURES_FOR_BANNER = 3


def sync(
    conn: sqlite3.Connection,
    now_utc: int,
    user_id: int = 1,
    fetch: Fetch = ics.fetch,
    client: Any | None = None,
    folder: Path | None = None,
    google: Any | None = None,
    mail: Any | None = None,
) -> int:
    """Read what is due and extract what is new; returns how many suggestions were made. `folder` holds the
    Google token; `google` and `mail` are the Calendar and Gmail APIs (made from the token when not given)."""
    settings = load_settings(conn, user_id)
    if settings["time"].timezone is None:
        return 0
    feeds_from_config(conn, settings, user_id)
    forced = kv_get(conn, "sync_now", None, user_id) is not None
    conn.execute("DELETE FROM kv WHERE user_id = ? AND key = 'sync_now'", [user_id])
    made = 0
    for source in rows(conn, "SELECT * FROM sources WHERE user_id = ? AND enabled = 1 AND kind = 'ics'", [user_id]):
        last = parse_utc(source["last_sync_utc"]) if source["last_sync_utc"] else None
        if forced or last is None or now_utc - last >= settings["ingest"].poll_min:
            made += read_feed(conn, source, settings, now_utc, user_id, fetch, client)
    if forced or due(conn, "gcal", settings, now_utc, user_id):

        def calendars() -> int:
            api = google or (google_auth.calendar(folder) if folder and google_auth.connected(folder) else None)
            return read_calendars(conn, settings, now_utc, user_id, api, client) if api else 0

        made += guarded(conn, "gcal", now_utc, user_id, calendars)
    if settings["gmail"].enabled and (forced or due(conn, "gmail", settings, now_utc, user_id)):

        def messages() -> int:
            api = mail or (google_auth.gmail(folder) if folder else None)
            return read_mail(conn, settings, now_utc, user_id, api) if api else 0

        guarded(conn, "gmail", now_utc, user_id, messages)
    made += extract_pending(conn, settings, now_utc, user_id, client)
    return made


def due(conn: sqlite3.Connection, kind: str, settings: dict, now_utc: int, user_id: int) -> bool:
    found = one(conn, "SELECT MIN(last_sync_utc) AS at FROM sources WHERE user_id = ? AND kind = ?", [user_id, kind])
    at = found["at"] if found else None
    return at is None or now_utc - parse_utc(at) >= settings["ingest"].poll_min


def guarded(conn: sqlite3.Connection, kind: str, now_utc: int, user_id: int, read: Callable[[], int]) -> int:
    """Google being down (or the token revoked) shows on its sources and leaves the others to go on."""
    try:
        return read()
    except Exception as error:
        conn.execute(
            "UPDATE sources SET last_error = ?, failures = failures + 1, last_sync_utc = ? "
            "WHERE user_id = ? AND kind = ?",
            [f"{type(error).__name__}: {error}"[:300], format_utc(now_utc), user_id, kind],
        )
        return 0


def read_calendars(
    conn: sqlite3.Connection, settings: dict, now_utc: int, user_id: int, google: Any, client: Any | None = None
) -> int:
    """The calendars you switched on (`gcal.read` only picks the first ones), from yesterday as far ahead as the
    allocator plans: a paper due in five weeks on Canvas is paced from now, not found two weeks before it's due."""
    listed = gcal.calendars(google)
    kv_set(conn, "google_calendars", listed, user_id)
    seed_calendars(conn, settings["gcal"], listed, user_id)
    tz, since = settings["time"].timezone, now_utc - 24 * 60
    until = now_utc + settings["time"].allocator_weeks * 7 * 24 * 60
    made = 0
    for source in rows(conn, "SELECT * FROM sources WHERE user_id = ? AND kind = 'gcal' AND enabled = 1", [user_id]):
        config = json.loads(source["config"])
        way = event_reading(settings, config.get("kind"), settings["gcal"].include_all_day)

        def read(calendar_id: str | None = config.get("calendar"), way: ics.Reading = way) -> list[Found]:
            if calendar_id not in {c["id"] for c in listed}:
                raise LookupError("no longer in your Google account")
            events = gcal.events(google, calendar_id, gcal.rfc3339(since), gcal.rfc3339(until))
            series = {e.get("recurringEventId", "") for e in events} - {""}
            rules = gcal.repeat_rules(google, calendar_id, series)
            found = (ics.google_event(e, tz, way, rules.get(e.get("recurringEventId", ""))) for e in events)
            return [f for f in found if f is not None]

        made += take(conn, source, read, settings, now_utc, user_id, until, client)
    return made


def seed_calendars(conn: sqlite3.Connection, wanted: GcalSettings, listed: list[dict], user_id: int) -> None:
    """A calendar `gcal.read` names becomes a source the first time it is seen; after that, Settings decides."""
    found = rows(conn, "SELECT config FROM sources WHERE user_id = ? AND kind = 'gcal'", [user_id])
    have = {json.loads(r["config"]).get("calendar") for r in found}
    for c in listed:
        conn.execute(  # a calendar renamed in Google, or first named "primary", goes by its name
            "UPDATE OR IGNORE sources SET name = ? WHERE user_id = ? AND kind = 'gcal' "
            "AND json_extract(config, '$.calendar') = ?",
            [c["name"], user_id, c["id"]],
        )
        named = [n for n in wanted.read if n in (c["id"], c["name"]) or (n == "primary" and c["primary"])]
        if named and c["id"] not in have:
            conn.execute(
                "INSERT OR IGNORE INTO sources (user_id, kind, name, config, trusted) VALUES (?, 'gcal', ?, ?, ?)",
                [user_id, c["name"], json.dumps({"calendar": c["id"]}), int(bool(set(named) & set(wanted.trusted)))],
            )


def event_reading(
    settings: dict, kind: str | None, all_day: bool, due: str | None = None, lesson: str | None = None
) -> ics.Reading:
    """A calendar's way of reading events: the kind it names (if that kind still exists), else ingest's patterns."""
    patterns, presets = settings["ingest"], settings["presets"]
    fixed = frozenset(name for name, p in presets.items() if p.when == "fixed")
    return ics.reading(
        due or patterns.due_pattern,
        patterns.exam_pattern,
        lesson or patterns.class_pattern,
        kind=kind if kind in presets else None,
        fixed_kinds=fixed,
        all_day=all_day,
    )


def feeds_from_config(conn: sqlite3.Connection, settings: dict[str, Any], user_id: int) -> None:
    """Feeds listed in settings (`friday.toml`'s `[[sources]]`) exist as sources, matched by name."""
    for feed in settings["sources"]:
        config = json.dumps({"url": feed.url, "due_pattern": feed.due_pattern, "class_pattern": feed.class_pattern})
        conn.execute(
            "INSERT INTO sources (user_id, kind, name, config, trusted) VALUES (?, 'ics', ?, ?, ?) "
            "ON CONFLICT (user_id, kind, name) DO UPDATE SET config = excluded.config, trusted = excluded.trusted",
            [user_id, feed.name, config, int(feed.trusted)],
        )


def read_feed(
    conn: sqlite3.Connection, source: dict, settings: dict, now_utc: int, user_id: int, fetch: Fetch, client: Any
) -> int:
    config = json.loads(source["config"])

    def read() -> list[Found]:
        read = event_reading(settings, None, False, config.get("due_pattern"), config.get("class_pattern"))
        return ics.parse_feed(fetch(config["url"]), settings["time"].timezone, read)

    return take(conn, source, read, settings, now_utc, user_id, None, client)


def extract_pending(conn: sqlite3.Connection, settings: dict, now_utc: int, user_id: int, client: Any | None) -> int:
    """Documents and mail waiting to be read, while the day's budget lasts."""
    pending = rows(
        conn,
        "SELECT r.*, s.kind, s.name AS source, s.trusted FROM raw_inputs r JOIN sources s ON "
        "s.id = r.source_id WHERE r.user_id = ? AND r.status = 'new' AND s.kind IN ('upload', 'gmail') ORDER BY r.id",
        [user_id],
    )
    if not pending:
        return 0
    client = client or llm.client()
    if client is None:
        waiting = {r["source_id"] for r in pending}
        for source_id in waiting:
            why = "No Anthropic API key (secrets.toml), so this waits unread"
            conn.execute("UPDATE sources SET last_error = ? WHERE id = ?", [why, source_id])
        return 0
    tz, budget = settings["time"].timezone, settings["llm"]
    today = planning_date(now_utc, tz, minutes_of(settings["time"].day_start))
    areas, presets = list(area_names(conn, user_id).values()), list(settings["presets"])
    made = 0
    for r in pending:
        used = spend(conn, user_id, today.isoformat())
        if used["calls"] >= budget.daily_calls or used["tokens"] >= budget.daily_tokens:
            break  # the rest wait for tomorrow; Settings and the inbox show the budget
        try:
            proposals, syllabus, tokens = extract.extract(
                client,
                budget.model,
                r["content"] + thread_note(conn, r),
                r["media_type"],
                today,
                tz,
                areas,
                presets,
                settings["notes"],
            )
        except Exception as error:
            if provider_down(error):  # every input would fail the same way; they wait, the source shows why
                status = getattr(error, "status_code", None)
                said = (
                    f"The AI refused the key from {llm.key_source()[1]}"
                    if status in (401, 403)
                    else f"{settings['llm'].model} won't take Friday's request"
                    if status in (400, 404)
                    else "The AI is unavailable"
                )
                why = f"{said}: {error}"[:300]
                conn.execute("UPDATE sources SET last_error = ? WHERE id = ?", [why, r["source_id"]])
                break
            conn.execute("UPDATE raw_inputs SET status = 'failed', error = ? WHERE id = ?", [str(error)[:300], r["id"]])
            continue
        record_spend(conn, user_id, today.isoformat(), tokens)
        batch = f"{r['title'] or 'document'} {uuid.uuid4().hex[:6]}" if syllabus else None
        made += suggest(conn, settings, now_utc, user_id, r["id"], proposals, bool(r["trusted"]), r["source"], batch)
        conn.execute("UPDATE raw_inputs SET status = 'extracted' WHERE id = ?", [r["id"]])
    return made


def thread_note(conn: sqlite3.Connection, r: dict) -> str:
    """What earlier messages of a mail thread already gave, so the AI doesn't propose it again in other words."""
    if not r["thread_id"] or r["media_type"] != "text/plain":
        return ""
    found = rows(
        conn,
        "SELECT json_extract(s.input, '$.title') AS title FROM suggestions s "
        "JOIN raw_inputs i ON i.id = s.raw_input_id WHERE i.source_id = ? AND i.thread_id = ? AND i.id != ? "
        "AND s.command = 'add' "
        "AND s.status IN ('pending', 'accepted')",
        [r["source_id"], r["thread_id"], r["id"]],
    )
    titles = [f["title"] for f in found if f["title"]]
    if not titles:
        return ""
    return (
        "\n\n[Friday already has these from earlier in this thread; propose only what is new, and nothing that "
        f"says one of these again: {'; '.join(titles)}]"
    )


def provider_down(error: Exception) -> bool:
    """A bad key, a rate limit or an outage, rather than something about this one input."""
    status = getattr(error, "status_code", None)
    unreachable = type(error).__name__ in ("APIConnectionError", "APITimeoutError")
    about_model = status in (400, 404) and "model" in str(error)  # a retired model, or a request it won't take
    return unreachable or about_model or status in (401, 403, 429) or (status or 0) >= 500


def failing_sources(conn: sqlite3.Connection, user_id: int) -> list[str]:
    """Sources that failed often enough in a row for a banner."""
    found = rows(
        conn, "SELECT name, last_error FROM sources WHERE user_id = ? AND failures >= ?", [user_id, FAILURES_FOR_BANNER]
    )
    return [f"{r['name']} can't be read: {r['last_error']}" for r in found]
