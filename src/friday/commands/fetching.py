"""The sync job (DESIGN §22.1–22.6): read the sources that are due, store what is new, and turn it into
suggestions. Feeds and Google calendars go through fixed rules (`ingest/ics.py`); documents and mail
(`commands/mail.py`) through the LLM (`ingest/extract.py`) within the day's budget. A trusted source's fixed
events go straight in, as `sync:<source>`, logged and undoable; so does dropping one that disappeared or that you
declined. The server's job loop runs this every minute; the simulator may too.
"""

import json
import re
import sqlite3
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from friday.commands.duplicates import set_aside_waiting
from friday.commands.inbox import record_spend, spend
from friday.commands.mail import read_mail
from friday.commands.suggesting import suggest, take, write_raw
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
    # What you uploaded first: you're waiting on it (30 Oct: a syllabus uploaded in setup waited five minutes behind
    # a new user's first read of every calendar on the Mac).
    made = extract_pending(conn, settings, now_utc, user_id, client, kinds=("upload",))
    forced = kv_get(conn, "sync_now", None, user_id) is not None
    conn.execute("DELETE FROM kv WHERE user_id = ? AND key = 'sync_now'", [user_id])
    for source in rows(conn, "SELECT * FROM sources WHERE user_id = ? AND enabled = 1 AND kind = 'ics'", [user_id]):
        last = parse_utc(source["last_sync_utc"]) if source["last_sync_utc"] else None
        if forced or last is None or now_utc - last >= settings["ingest"].poll_min:
            made += read_feed(conn, source, settings, now_utc, user_id, fetch, client)
    if forced or due(conn, "gcal", settings, now_utc, user_id):
        calendar_apis = google_auth.per_account(google, folder, google_auth.calendar)

        def calendars() -> int:
            return read_calendars(conn, settings, now_utc, user_id, calendar_apis, client, folder)

        made += guarded(conn, "gcal", now_utc, user_id, calendars) if calendar_apis else 0
    if forced or kv_get(conn, "mac_sync_now", None, user_id) is not None:
        conn.execute("DELETE FROM kv WHERE user_id = ? AND key = 'mac_sync_now'", [user_id])
        made += read_mac(conn, settings, now_utc, user_id, client)
    if settings["gmail"].enabled and (forced or due(conn, "gmail", settings, now_utc, user_id)):
        # Each account that lets Friday read its mail, into a source of its own; one failing leaves the others.
        mail_apis = google_auth.per_account(mail, folder, google_auth.gmail, (google_auth.GMAIL_SCOPE,))
        for account, api in mail_apis.items():
            read_mail(conn, settings, now_utc, user_id, api, account)
    made += extract_pending(conn, settings, now_utc, user_id, client)
    # What waits is checked again each pass, read or not: something you added since may be what it proposes.
    set_aside_waiting(conn, settings, user_id, now_utc, write_raw(conn))
    return made


def due(conn: sqlite3.Connection, kind: str, settings: dict, now_utc: int, user_id: int) -> bool:
    found = one(  # a source switched off (or a removed account's) isn't read, so it doesn't make the rest due
        conn,
        "SELECT MIN(last_sync_utc) AS at, COUNT(*) > COUNT(last_sync_utc) AS unread FROM sources "
        "WHERE user_id = ? AND kind = ? AND enabled = 1",
        [user_id, kind],
    )
    at = found["at"] if found else None
    # one not read yet (new, or asked to read again) makes them due, though another was read a minute ago
    return at is None or bool(found and found["unread"]) or now_utc - parse_utc(at) >= settings["ingest"].poll_min


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
    conn: sqlite3.Connection,
    settings: dict,
    now_utc: int,
    user_id: int,
    apis: dict[str, google_auth.Api],
    client: Any | None = None,
    folder: Path | None = None,
) -> int:
    """The calendars you switched on (`gcal.read` only picks the first ones), each through its own account, from
    yesterday as far ahead as the allocator plans: a paper due in five weeks on Canvas is paced from now, not found
    two weeks before it's due."""
    listed, services, broken = list_calendars(conn, apis, user_id, folder)
    kv_set(conn, "google_calendars", listed, user_id)
    seed_calendars(conn, settings["gcal"], listed, user_id)
    owners = {c["id"]: c.get("account", google_auth.LEGACY) for c in listed}
    tz, since = settings["time"].timezone, now_utc - 24 * 60
    until = now_utc + settings["time"].allocator_weeks * 7 * 24 * 60
    made = 0
    for source in rows(conn, "SELECT * FROM sources WHERE user_id = ? AND kind = 'gcal' AND enabled = 1", [user_id]):
        config = json.loads(source["config"])
        way = event_reading(settings, config.get("kind"), settings["gcal"].include_all_day)

        def read(calendar_id: str | None = config.get("calendar"), way: ics.Reading = way) -> list[Found]:
            if calendar_id not in owners:
                raise LookupError("no longer in your Google account")
            if owners[calendar_id] in broken:  # its account can't be read now (an expired sign-in, say)
                raise broken[owners[calendar_id]]
            account = google_auth.which(services, owners[calendar_id])
            if account is None:
                raise LookupError(f"{owners[calendar_id]} isn't connected any more")
            google = services[account]
            events = gcal.events(google, calendar_id, gcal.rfc3339(since), gcal.rfc3339(until))
            series = {e.get("recurringEventId", "") for e in events} - {""}
            rules = gcal.repeat_rules(google, calendar_id, series)
            found = (ics.google_event(e, tz, way, rules.get(e.get("recurringEventId", ""))) for e in events)
            return [f for f in found if f is not None]

        made += take(conn, source, read, settings, now_utc, user_id, until, client)
    return made


def read_mac(conn: sqlite3.Connection, settings: dict, now_utc: int, user_id: int, client: Any | None = None) -> int:
    """The Mac's calendars you switched on, from what the Mac app last posted (`mac_sync`): read as Google's are, in
    the window it posted, so an event gone from it is suggested dropped."""
    listed = {c["id"] for c in kv_get(conn, "mac_calendars", [], user_id)}
    events = kv_get(conn, "mac_events", {}, user_id)
    window = kv_get(conn, "mac_window", None, user_id)
    if window is None:
        return 0
    tz, made = settings["time"].timezone, 0
    for source in rows(conn, "SELECT * FROM sources WHERE user_id = ? AND kind = 'mac' AND enabled = 1", [user_id]):
        config = json.loads(source["config"])
        way = event_reading(settings, config.get("kind"), settings["gcal"].include_all_day)

        def read(calendar_id: str | None = config.get("calendar"), way: ics.Reading = way) -> list[Found]:
            if calendar_id not in listed:
                raise LookupError("no longer on your Mac")
            found = (ics.google_event(e, tz, way) for e in events.get(calendar_id, []))
            return [f for f in found if f is not None]

        made += take(conn, source, read, settings, now_utc, user_id, window["until"], client)
    return made


def list_calendars(
    conn: sqlite3.Connection, apis: dict[str, google_auth.Api], user_id: int, folder: Path | None
) -> tuple[list[dict], dict[str, Any], dict[str, Exception]]:
    """Every account's calendars, each once, with the account it's read through; the accounts' APIs; and why
    each account that couldn't be listed couldn't. That one's calendars stay as last listed, so they aren't taken
    for gone, and fail with the reason when read."""
    before = kv_get(conn, "google_calendars", [], user_id)
    found: list[dict] = []
    services: dict[str, Any] = {}
    broken: dict[str, Exception] = {}
    for account, api in apis.items():
        try:
            service = api()
            listed = gcal.calendars(service)
        except Exception as error:
            broken[account] = error
            found += [c for c in before if c.get("account", google_auth.LEGACY) == account]
            continue
        if account == google_auth.LEGACY:  # the token from before Friday kept several: its primary calendar names it
            account = next((c["id"] for c in listed if c["primary"]), google_auth.LEGACY)
            if folder is not None:
                google_auth.adopt(folder, account)
        services[account] = service
        found += [c | {"account": account} for c in listed]
    return named(merged(found)), services, broken


def merged(listed: list[dict]) -> list[dict]:
    """Each calendar once, though several accounts list it (one shared with your other account, say): read through
    the first account that may change it, else the first that has it. `accounts` keeps them all, to fall back on
    when one is removed."""
    by_id: dict[str, dict] = {}
    for c in listed:
        seen = by_id.get(c["id"])
        if seen is None:
            by_id[c["id"]] = c | {"accounts": [c["account"]]}
            continue
        better = c if c.get("writable") and not seen.get("writable") else seen
        by_id[c["id"]] = better | {"accounts": [*seen["accounts"], c["account"]]}
    return list(by_id.values())


def named(listed: list[dict]) -> list[dict]:
    """Each calendar's name in Friday (its source's): its own, or with its account's address when an earlier
    account has one by that name ("Holidays in United States (me@cornell.edu)"), numbered when one account has
    two. The first account's keep their own names, so adding another renames nothing you had."""
    taken: dict[str, str] = {}  # a name given → the account it was given in
    out = []
    for c in listed:
        name = c["name"]
        if name in taken and taken[name] != c["account"] and c["account"]:
            name = f"{name} ({c['account']})"
        base, n = name, 1
        while name in taken:
            n += 1
            name = f"{base} {n}"
        taken[name] = c["account"]
        out.append(c | {"source_name": name})
    return out


def seed_calendars(conn: sqlite3.Connection, wanted: GcalSettings, listed: list[dict], user_id: int) -> None:
    """A calendar `gcal.read` names becomes a source the first time it is seen; after that, Settings decides. One
    that was read until its account was removed is read again once the account is back."""
    found = rows(conn, "SELECT config FROM sources WHERE user_id = ? AND kind = 'gcal'", [user_id])
    have = {json.loads(r["config"]).get("calendar") for r in found}
    for c in listed:
        name = c.get("source_name", c["name"])
        conn.execute(  # a calendar renamed in Google, or first named "primary", goes by its name
            "UPDATE OR IGNORE sources SET name = ? WHERE user_id = ? AND kind = 'gcal' "
            "AND json_extract(config, '$.calendar') = ?",
            [name, user_id, c["id"]],
        )
        conn.execute(
            "UPDATE sources SET enabled = 1, config = json_remove(config, '$.account_removed') "
            "WHERE user_id = ? AND kind = 'gcal' AND json_extract(config, '$.calendar') = ? "
            "AND json_extract(config, '$.account_removed')",
            [user_id, c["id"]],
        )
        named = [n for n in wanted.read if n in (c["id"], c["name"]) or (n == "primary" and c["primary"])]
        if named and c["id"] not in have:
            conn.execute(
                "INSERT OR IGNORE INTO sources (user_id, kind, name, config, trusted) VALUES (?, 'gcal', ?, ?, ?)",
                [user_id, name, json.dumps({"calendar": c["id"]}), int(bool(set(named) & set(wanted.trusted)))],
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


def extract_pending(
    conn: sqlite3.Connection,
    settings: dict,
    now_utc: int,
    user_id: int,
    client: Any | None,
    kinds: tuple[str, ...] = ("upload", "gmail"),
) -> int:
    """Documents and mail waiting to be read (of these kinds of source), while the day's budget lasts."""
    pending = rows(
        conn,
        "SELECT r.*, s.kind, s.name AS source, s.trusted FROM raw_inputs r JOIN sources s ON s.id = r.source_id "
        f"WHERE r.user_id = ? AND r.status = 'new' AND s.kind IN ({', '.join('?' for _ in kinds)}) ORDER BY r.id",
        [user_id, *kinds],
    )
    if not pending:
        return 0
    client = client or llm.client(settings["llm"])
    if client is None:
        waiting = {r["source_id"] for r in pending}
        for source_id in waiting:
            why = f"{llm.missing(settings['llm'])}, so this waits unread"
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
                    f"The AI refused the key from {llm.key_source(settings['llm'].provider)[1]}"
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


# Google's word for a sign-in it no longer takes (expired, or taken back in your Google account); the same test as
# the web app's `wantsSignIn`, which keeps the raw error to offer "Connect again".
SIGN_IN_GONE = re.compile(r"RefreshError|invalid_grant|insufficient authentication", re.IGNORECASE)


# No way to the internet (8 Nov: Wi-Fi off, the banner read "TransportError: HTTPSConnectionPool(host=
# 'oauth2.googleapis.com', …) Failed to resolve …" for each of four sources): a name that can't be looked up, or no
# network at all. The same test as the web app's `offline`. A slow or refusing server isn't this: it keeps its words.
OFFLINE = re.compile(
    r"NameResolutionError|nodename nor servname|name resolution|Name or service not known|getaddrinfo failed|"
    r"Network is unreachable|No route to host|Errno (?:8|51|65|101)\b",
    re.IGNORECASE,
)


def failing_sources(conn: sqlite3.Connection, user_id: int) -> list[str]:
    """Sources that failed often enough in a row for a banner, in words that say what to do (2 Nov: the banner read
    "RefreshError: ('invalid_grant: Token has been expired or revoked.', …)"); with no internet, one line for all."""
    found = rows(
        conn,
        "SELECT name, last_error FROM sources WHERE user_id = ? AND failures >= ? ORDER BY id",
        [user_id, FAILURES_FOR_BANNER],
    )
    away = [r["name"] for r in found if is_offline(r["last_error"])]
    said = [f"{r['name']} can't be read: {why(r['last_error'])}" for r in found if not is_offline(r["last_error"])]
    return ([offline_words(away)] if away else []) + said


def is_offline(error: str | None) -> bool:
    return bool(error and OFFLINE.search(error) and not SIGN_IN_GONE.search(error))


def offline_words(names: list[str]) -> str:
    """'Friday can't reach the internet, so Gmail and canvas weren't read. …'"""
    listed = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"
    was = "wasn't" if len(names) == 1 else "weren't"
    return (
        f"Friday can't reach the internet, so {listed} {was} read. It keeps "
        "planning with what it has and reads again once you're back online."
    )


def why(error: str | None) -> str:
    if error and SIGN_IN_GONE.search(error):
        return "Google's sign-in for it expired or was taken back. Connect it again in Settings → Integrations."
    if is_offline(error):
        return "Friday can't reach the internet. It reads again once you're back online."
    return error or "it failed, with no reason given"
