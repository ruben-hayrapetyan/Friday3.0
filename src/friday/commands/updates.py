"""Friday's own updater.

The Mac app starts its server with its version and the update feed's address (FRIDAY_APP_VERSION,
FRIDAY_UPDATE_FEED): every build but Friday Test (Mac/build.sh). It looks at launch, once a day after (the `updates`
job), whenever Friday's window opens, and when you press Check now in Settings → Updates (H208: it looked once a
month, and Friday's server runs for weeks, so a new version went unseen). A newer version shows as a popup with every
newer version's notes (H124, H139); Later puts that version off until the same time tomorrow, and a newer one than it
asks at once (H209). Update downloads it in the background, checks it and unpacks it beside the app, then the Mac app
swaps it in, right away or when you quit (H146). The first time the new version opens, what changed is shown once
(H118). Yours looks as a downloaded copy does (H169); a server without a feed (Friday Test, fridayd run from the
code) never looks, and Settings says so.

Test users (H224–H227): a code the hub made, typed in Settings → Updates, is kept with your data and sent with
every look and download from then on; the site answers with the test users' feed (their version on top) and whose code
it is, or that it doesn't know it. Leaving forgets the code: you keep the version you have, and are offered the next
version everyone gets that's newer than it."""

import logging
import os
import re
import sqlite3
import threading
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from friday.api.commands import TestUserJoinInput
from friday.api.types import Empty
from friday.api.views import TestUserOut, UpdateStatusOut, UpdateVersionOut
from friday.commands.connecting import data_file
from friday.commands.registry import Ctx, command, query
from friday.core.db import connect, transaction
from friday.core.items import FieldError
from friday.core.time import to_zoned
from friday.planner.store import kv_get, kv_set
from friday.sync import updates as net

log = logging.getLogger("friday.updates")
DAY_MIN = 24 * 60


@dataclass
class Run:
    """This server run's updater: a check or download going on."""

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


def test_code(conn: sqlite3.Connection, user_id: int) -> str | None:
    found = kv_get(conn, "update_test_user", None, user_id)
    return found["code"] if found else None


def check(conn: sqlite3.Connection, now_utc: int, user_id: int = 1) -> bool:
    """Read the feed and keep what's newer, with every version's notes (for what changed after updating). A test
    user's code goes with it, and what the site says of the code is kept. All of it is written at once, so the page
    never sees the code known before the versions it brings; and only if the code is still the one sent (you may
    have joined or left while it looked): False when the answer was for another code and was dropped."""
    url, mine = feed_url(), have()
    if not url or not mine:
        return True
    code = test_code(conn, user_id)
    feed = net.fetch_feed(url, version=mine, test_code=code)
    with transaction(conn) if not conn.in_transaction else nullcontext(conn):
        if test_code(conn, user_id) != code:
            return False
        if code:  # a site that doesn't answer about the code (one from before test users) doesn't know it
            name = feed.get("test_user") if isinstance(feed.get("test_user"), str) else None
            kv_set(conn, "update_test_user", {"code": code, "name": name, "known": name is not None}, user_id)
        notes = kv_get(conn, "update_notes", {}, user_id)
        for entry in feed["versions"]:
            notes[entry["version"]] = entry
        kv_set(conn, "update_notes", notes, user_id)
        kv_set(conn, "update_newer", [v["version"] for v in net.newer(feed, mine)], user_id)
        kv_set(conn, "update_checked", now_utc, user_id)
    conn.commit()
    return True


def due(conn: sqlite3.Connection, now_utc: int, user_id: int = 1) -> bool:
    """At launch (once each run) and once a day after (H208)."""
    run = run_for(conn)
    last = kv_get(conn, "update_checked", None, user_id)
    return bool(feed_url()) and (not run.looked or last is None or now_utc - last >= DAY_MIN)


def put_off(conn: sqlite3.Connection, newest: str | None, now_utc: int, user_id: int) -> bool:
    """Whether Later put this version off and it isn't the same time tomorrow yet (H209): a newer one asks at once."""
    later = kv_get(conn, "update_later", None, user_id)
    return bool(later and newest and later["version"] == newest and now_utc < later["until"])


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
        test=bool(entry.get("test")),
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
    joined = kv_get(ctx.conn, "update_test_user", None, ctx.user_id)
    return UpdateStatusOut(
        checks=bool(feed_url() and mine),
        have=mine,
        # with its zone (19 Nov: without it, a Mac in another zone than Friday's read it hours off: "just now" always)
        last_checked=to_zoned(checked, ctx.tz).isoformat(timespec="minutes") if checked is not None else None,
        state=run.state,
        progress=run.progress,
        message=run.message,
        versions=[entry_out(e) for e in newer],
        popup=bool(newer)
        and run.state in ("idle", "failed")
        and not put_off(ctx.conn, newer[0]["version"] if newer else None, ctx.now_utc, ctx.user_id),
        whats_new=[entry_out(e) for e in whats_new(ctx.conn, ctx.user_id)],
        restart=ctx.settings["updates"].restart,
        staged=run.staged if run.state == "ready" else None,
        test_user=TestUserOut(**joined) if joined else None,
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
                if not check(conn, now, user_id):  # you joined or left while it looked: once more, with the code now
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
                         cancelled=lambda: run.stop, version=have(), test_code=test_code(conn, user_id))  # fmt: skip
    run.staged = str(net.unpack(image, folder))
    image.unlink(missing_ok=True)
    run.state, run.message = "ready", None


def look_now(ctx: Ctx) -> UpdateStatusOut:
    if not feed_url() or not have():
        raise FieldError("updates", "this Friday is built from its code here, so it doesn't look for updates")
    run = run_for(ctx.conn)
    if run.state not in ("checking", "downloading"):
        run.state, run.message = "checking", None
        in_background(ctx, run, "check")
    return status(ctx)


@command("update_check", logged=False)
def update_check(ctx: Ctx, inp: Empty) -> UpdateStatusOut:
    """Look for a newer Friday now (Settings → Updates). Returns at once; `update_status` says how it went."""
    return look_now(ctx)


CODE_LETTERS = re.compile(r"[A-Z0-9]{8}")


@command("update_test_join", logged=False)
def update_test_join(ctx: Ctx, inp: TestUserJoinInput) -> UpdateStatusOut:
    """Become a test user with the code you were given (H224): kept, and checked with the site now; from then on
    Friday is offered the versions released to test users. Returns at once; `update_status` says what the site said."""
    if not feed_url() or not have():
        raise FieldError("code", "this Friday doesn't look for updates, so it can't be a test user")
    typed = re.sub(r"[\s-]", "", inp.code.upper())
    if not CODE_LETTERS.fullmatch(typed):
        raise FieldError("code", "a test user's code is eight letters and digits, like K7QF-29XM")
    code = f"{typed[:4]}-{typed[4:]}"
    kv_set(ctx.conn, "update_test_user", {"code": code, "name": None, "known": None}, ctx.user_id)
    ctx.conn.commit()
    return look_now(ctx)


@command("update_test_leave", logged=False)
def update_test_leave(ctx: Ctx, inp: Empty) -> UpdateStatusOut:
    """Stop being a test user: the code is forgotten, you keep the version you have, and from now on you're offered
    only everyone's versions (a newer one than yours)."""
    notes = kv_get(ctx.conn, "update_notes", {}, ctx.user_id)
    newer = [v for v in kv_get(ctx.conn, "update_newer", [], ctx.user_id) if not notes.get(v, {}).get("test")]
    kv_set(ctx.conn, "update_test_user", None, ctx.user_id)
    kv_set(ctx.conn, "update_newer", newer, ctx.user_id)  # the test users' version isn't offered now, even before
    ctx.conn.commit()  # the look below answers
    return look_now(ctx) if feed_url() and have() else status(ctx)


@command("update_later", logged=False)
def update_later(ctx: Ctx, inp: Empty) -> UpdateStatusOut:
    """Put the newest version off until the same time tomorrow (H209); a newer one than it asks at once."""
    newest = kv_get(ctx.conn, "update_newer", [], ctx.user_id)
    if newest:
        kv_set(ctx.conn, "update_later", {"version": newest[0], "until": ctx.now_utc + DAY_MIN}, ctx.user_id)
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
