"""Friday's own updater (HOSTED.md H118–H124, H145–H147, H169).

The Mac app starts its server with its version and the update feed's address (FRIDAY_APP_VERSION, FRIDAY_UPDATE_FEED):
every build but Friday Test (Mac/build.sh). It looks at launch and once a month (the `updates` job), and when you press
Check now in Settings → Updates. A newer version shows as a popup at the next launch with every newer version's notes
(H124, H139); Later hides it until the next launch (H145). Update downloads it in the background, checks it and unpacks
it beside the app, then the Mac app swaps it in, right away or when you quit (H146). The first time the new version
opens, what changed is shown once (H118). Yours looks as a downloaded copy does (H169); a server without a feed (Friday
Test, fridayd run from the code) never looks, and Settings says so."""

import logging
import os
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from friday.api.types import Empty
from friday.api.views import UpdateStatusOut, UpdateVersionOut
from friday.commands.connecting import data_file
from friday.commands.registry import Ctx, command, query
from friday.core.db import connect
from friday.core.items import FieldError
from friday.core.time import to_local
from friday.planner.store import kv_get, kv_set
from friday.sync import updates as net

log = logging.getLogger("friday.updates")
MONTH_MIN = 30 * 24 * 60


@dataclass
class Run:
    """This server run's updater: the popup put off with Later, and a check or download going on."""

    later: bool = False
    looked: bool = False  # the launch's look has been made
    state: Literal["idle", "checking", "downloading", "ready", "failed"] = "idle"
    progress: float = 0.0
    message: str | None = None
    staged: str | None = None
    stop: bool = False
    thread: threading.Thread | None = field(default=None, repr=False)


RUNS: dict[Path, Run] = {}
LOCK = threading.Lock()


def feed_url() -> str | None:
    return os.environ.get("FRIDAY_UPDATE_FEED") or None


def have() -> str | None:
    return os.environ.get("FRIDAY_APP_VERSION") or None


def staging_folder() -> Path:
    """Where a new version is unpacked: the user's Caches, on the same disk as Applications, so the swap is a rename."""
    chosen = os.environ.get("FRIDAY_UPDATE_DIR")
    return Path(chosen) if chosen else Path.home() / "Library" / "Caches" / "Friday" / "updates"


def cant_replace() -> str | None:
    """Why this copy couldn't swap a new version in (an account that can't write to Applications), or None."""
    where = os.environ.get("FRIDAY_APP_PATH")
    if not where or (os.access(Path(where).parent, os.W_OK) and os.access(where, os.W_OK)):
        return None
    return (f"this Mac account can't replace Friday in {Path(where).parent}, so download the new version from the "
            "site instead")  # fmt: skip


def run_for(conn: sqlite3.Connection) -> Run:
    with LOCK:
        return RUNS.setdefault(data_file(conn).parent, Run())


# Looking


def check(conn: sqlite3.Connection, now_utc: int, user_id: int = 1) -> None:
    """Read the feed and keep what's newer, with every version's notes (for what changed after updating)."""
    url, mine = feed_url(), have()
    if not url or not mine:
        return
    feed = net.fetch_feed(url, version=mine)
    notes = kv_get(conn, "update_notes", {}, user_id)
    for entry in feed["versions"]:
        notes[entry["version"]] = entry
    kv_set(conn, "update_notes", notes, user_id)
    kv_set(conn, "update_newer", [v["version"] for v in net.newer(feed, mine)], user_id)
    kv_set(conn, "update_checked", now_utc, user_id)
    conn.commit()


def due(conn: sqlite3.Connection, now_utc: int, user_id: int = 1) -> bool:
    """At launch (once each run) and once a month after (H121)."""
    run = run_for(conn)
    last = kv_get(conn, "update_checked", None, user_id)
    return bool(feed_url()) and (not run.looked or last is None or now_utc - last >= MONTH_MIN)


def check_due(conn: sqlite3.Connection, now_utc: int, user_id: int = 1) -> None:
    """The `updates` job: look when due; a failure is kept to show in Settings, never raised at you."""
    run = run_for(conn)
    run.looked = True
    if have() and kv_get(conn, "update_seen", None, user_id) is None:  # the first run: nothing to tell about
        kv_set(conn, "update_seen", have(), user_id)
        conn.commit()
    try:
        check(conn, now_utc, user_id)
        if run.state == "failed" and run.staged is None:
            run.state, run.message = "idle", None
    except net.UpdateError as wrong:
        log.info("update check: %s", wrong)
        run.message = f"Couldn't look for an update: {wrong}."


# What the page shows


def entry_out(entry: dict) -> UpdateVersionOut:
    notes = entry.get("notes", {})
    return UpdateVersionOut(
        version=entry["version"],
        released=entry.get("released", ""),
        summary=notes.get("summary", ""),
        new=notes.get("new", []),
        changed=notes.get("changed", []),
        fixed=notes.get("fixed", []),
    )


def whats_new(conn: sqlite3.Connection, user_id: int) -> list[dict]:
    """What changed since the version you last saw, newest first, until you've read it (H118): the notes kept from
    the checks made before updating."""
    mine, seen = have(), kv_get(conn, "update_seen", None, user_id)
    if not mine or not seen or net.version_key(mine) <= net.version_key(seen):
        return []
    low, high = net.version_key(seen), net.version_key(mine)
    notes = kv_get(conn, "update_notes", {}, user_id)
    between = [e for v, e in notes.items() if low < net.version_key(v) <= high]
    return sorted(between, key=lambda e: net.version_key(e["version"]), reverse=True)


def status(ctx: Ctx) -> UpdateStatusOut:
    run = run_for(ctx.conn)
    mine = have()
    notes = kv_get(ctx.conn, "update_notes", {}, ctx.user_id)
    newer = [notes[v] for v in kv_get(ctx.conn, "update_newer", [], ctx.user_id) if v in notes]
    if mine:
        newer = [e for e in newer if net.version_key(e["version"]) > net.version_key(mine)]
    checked = kv_get(ctx.conn, "update_checked", None, ctx.user_id)
    return UpdateStatusOut(
        checks=bool(feed_url() and mine),
        have=mine,
        last_checked=to_local(checked, ctx.tz).isoformat(timespec="minutes") if checked is not None else None,
        state=run.state,
        progress=run.progress,
        message=run.message,
        versions=[entry_out(e) for e in newer],
        popup=bool(newer) and not run.later and run.state in ("idle", "failed"),
        whats_new=[entry_out(e) for e in whats_new(ctx.conn, ctx.user_id)],
        restart=ctx.settings["updates"].restart,
        staged=run.staged if run.state == "ready" else None,
    )


@query("update_status")
def update_status(ctx: Ctx, inp: Empty) -> UpdateStatusOut:
    """Friday's version, whether a newer one is out with what each newer version changes, and how an update is
    going; what changed in the version you now have, until you've seen it."""
    return status(ctx)


# What you can do


def in_background(ctx: Ctx, run: Run, work: str) -> None:
    db = data_file(ctx.conn)
    now, user_id = ctx.now_utc, ctx.user_id

    def go() -> None:
        conn = connect(db)
        try:
            if work == "check":
                check(conn, now, user_id)
                run.state, run.message = "idle", None
            else:
                fetch(conn, run, user_id)
        except net.UpdateError as wrong:
            run.state, run.message = "failed", f"{str(wrong)[0].upper()}{str(wrong)[1:]}."
        finally:
            conn.close()

    run.thread = threading.Thread(target=go, name=f"update-{work}", daemon=True)
    run.thread.start()


def fetch(conn: sqlite3.Connection, run: Run, user_id: int) -> None:
    newest = kv_get(conn, "update_newer", [], user_id)
    notes = kv_get(conn, "update_notes", {}, user_id)
    if not newest or newest[0] not in notes:
        raise net.UpdateError("there's no newer version to download")
    folder = staging_folder() / newest[0]
    image = net.download(notes[newest[0]], folder, progress=lambda p: setattr(run, "progress", p),
                         cancelled=lambda: run.stop, version=have())  # fmt: skip
    run.staged = str(net.unpack(image, folder))
    image.unlink(missing_ok=True)
    run.state, run.message = "ready", None


@command("update_check", logged=False)
def update_check(ctx: Ctx, inp: Empty) -> UpdateStatusOut:
    """Look for a newer Friday now (Settings → Updates). Returns at once; `update_status` says how it went."""
    if not feed_url() or not have():
        raise FieldError("updates", "this Friday is built from its code here, so it doesn't look for updates")
    run = run_for(ctx.conn)
    if run.state not in ("checking", "downloading"):
        run.state, run.message = "checking", None
        in_background(ctx, run, "check")
    return status(ctx)


@command("update_later", logged=False)
def update_later(ctx: Ctx, inp: Empty) -> UpdateStatusOut:
    """Put the update popup off until Friday next opens (H145)."""
    run_for(ctx.conn).later = True
    return status(ctx)


@command("update_start", logged=False)
def update_start(ctx: Ctx, inp: Empty) -> UpdateStatusOut:
    """Download the newest version, check it and unpack it; the Mac app then swaps it in, right away or when you
    quit, as Settings says (H146). Returns at once; `update_status` gives its progress."""
    run = run_for(ctx.conn)
    if not status(ctx).versions:
        raise FieldError("updates", "there's no newer version to download")
    if why := cant_replace():
        raise FieldError("updates", why)
    if run.state not in ("downloading", "ready"):
        run.state, run.progress, run.message, run.stop = "downloading", 0.0, None, False
        in_background(ctx, run, "download")
    return status(ctx)


@command("update_stop", logged=False)
def update_stop(ctx: Ctx, inp: Empty) -> UpdateStatusOut:
    """Stop a download that's going on; nothing is changed."""
    run = run_for(ctx.conn)
    if run.state == "downloading":
        run.stop = True
        if run.thread is not None:
            run.thread.join(10)
        run.state, run.message = "idle", "Stopped. Nothing was changed."
    return status(ctx)


@command("whats_new_seen", logged=False)
def whats_new_seen(ctx: Ctx, inp: Empty) -> UpdateStatusOut:
    """You've read what changed in this version: it isn't shown again."""
    if have():
        kv_set(ctx.conn, "update_seen", have(), ctx.user_id)
    return status(ctx)
