"""Mail into the inbox (DESIGN §22.4): the newest messages matching `gmail.query` are stored, and only those
passing the pre-filter (a sender domain or keyword you listed; no LLM) wait for extraction, with their PDFs as
documents of their own. Everything else is kept as `ignored` and never leaves the machine. Run by the sync job, for
each Google account that lets Friday read its mail, each into a source of its own; a message that came to two of
your accounts (forwarded from school, say) is read once.
"""

import hashlib
import json
import re
import sqlite3
from collections.abc import Callable
from typing import Any

from friday.api.commands import Changed, ItemRef, MailLogInput
from friday.api.views import MailOut
from friday.commands.registry import Ctx, command, query
from friday.core.db import one, rows
from friday.core.integrations import GmailSettings
from friday.core.items import FieldError
from friday.core.plain import kept
from friday.core.time import format_local, format_utc, parse_utc, to_local
from friday.sync import gmail
from friday.sync.google_auth import LEGACY

SOURCE = "Gmail"
MAIL_KINDS = ("gmail", "mail")  # Gmail's sources, and other mailboxes' by app password (C99): all of it your mail
OLDER = "A newer message in its thread was read instead (it quotes this one)"
ELSEWHERE = "The same message came to another of your Google accounts and was seen there"
WITH_PDFS = "To be read on the next reading of your mail, with its PDFs"


def read_mail(
    conn: sqlite3.Connection,
    settings: dict,
    now_utc: int,
    user_id: int,
    api: Callable[[], Any],
    account: str,
    kind: str = "gmail",
    label: str = SOURCE,
) -> int:
    """Store an account's new messages; returns how many will be read by the AI. Its mail being down (or the sign-in
    expired) shows on the account's source, and the other accounts go on. `kind` and `label`: Gmail's, or another
    mailbox read by app password ("mail", "iCloud Mail": sync/imap_any.py, C99)."""
    source = mail_source(conn, user_id, account, kind, label)
    if not source["enabled"]:
        return 0
    try:
        passed = read_messages(conn, settings["gmail"], api(), source, now_utc, user_id)
    except Exception as error:
        conn.execute(
            "UPDATE sources SET last_error = ?, failures = failures + 1, last_sync_utc = ? WHERE id = ?",
            [kept(error, label), format_utc(now_utc), source["id"]],
        )
        return 0
    conn.execute(
        "UPDATE sources SET last_error = NULL, failures = 0, last_sync_utc = ? WHERE id = ?",
        [format_utc(now_utc), source["id"]],
    )
    return passed


def mail_source(
    conn: sqlite3.Connection, user_id: int, account: str, kind: str = "gmail", label: str = SOURCE
) -> dict[str, Any]:
    """An account's Gmail source, made the first time its mail is read: "Gmail" while it's the only one, else named
    with its address. The one kept from before Friday kept several accounts (no account in it) goes to the first
    account read; one put away when its account was removed comes back with it."""
    mine = rows(conn, "SELECT * FROM sources WHERE user_id = ? AND kind = ? ORDER BY id", [user_id, kind])
    found = next((s for s in mine if json.loads(s["config"]).get("account", LEGACY) == account), None)
    if found is None and account != LEGACY:
        found = next((s for s in mine if not json.loads(s["config"]).get("account")), None)
    if found is None:
        name = label if all(s["name"] != label for s in mine) else f"{label} ({account or 'another account'})"
        config = json.dumps({"account": account} if account else {})
        conn.execute(
            "INSERT INTO sources (user_id, kind, name, config) VALUES (?, ?, ?, ?)", [user_id, kind, name, config]
        )
        return mail_source(conn, user_id, account, kind, label)
    config = json.loads(found["config"])
    back = config.pop("account_removed", False)
    claimed = config | ({"account": account} if account else {})
    if claimed != json.loads(found["config"]):
        enabled = 1 if back else found["enabled"]
        conn.execute(
            "UPDATE sources SET config = ?, enabled = ? WHERE id = ?", [json.dumps(claimed), enabled, found["id"]]
        )
        found = found | {"config": json.dumps(claimed), "enabled": enabled}
    return found


def read_messages(
    conn: sqlite3.Connection, wanted: GmailSettings, service: Any, source: dict[str, Any], now_utc: int, user_id: int
) -> int:
    seen = {
        r["external_id"] for r in rows(conn, "SELECT external_id FROM raw_inputs WHERE source_id = ?", [source["id"]])
    }
    fetch_again(conn, service, source, now_utc, user_id)
    listed = gmail.message_ids(service, wanted.query, wanted.max_per_sync)
    newest = {}  # thread → its newest message, which quotes the others
    for message_id, thread in listed:
        newest.setdefault(thread, message_id)
    passed = 0
    for message_id, thread in listed:
        if message_id in seen:
            continue
        mail = gmail.read(service, message_id)
        skipped = OLDER if newest[thread] != message_id else elsewhere(conn, user_id, source["id"], mail.text)
        skipped = skipped or why_skipped(mail, wanted)
        # Its PDFs first: if Google fails one, nothing of the message is kept, so the next sync reads it again whole
        # (saved first, the message would count as seen and its syllabus would never come).
        pdfs = (
            [(pdf, gmail.attachment(service, mail.id, pdf.attachment_id)) for pdf in mail.pdfs] if not skipped else []
        )
        save(conn, user_id, source["id"], mail.id, mail.subject, "text/plain", mail.text, now_utc, skipped, thread)
        if skipped is None:
            passed += 1
            conn.execute(  # earlier messages still waiting are read through this one
                "UPDATE raw_inputs SET status = 'ignored', error = ? WHERE source_id = ? AND thread_id = ? "
                "AND status = 'new' AND external_id != ? AND external_id NOT LIKE ?",
                [OLDER, source["id"], thread, mail.id, f"{mail.id}#%"],
            )
            for pdf, content in pdfs:
                save(
                    conn,
                    user_id,
                    source["id"],
                    f"{mail.id}#{pdf.name}",
                    pdf.name,
                    "application/pdf",
                    content,
                    now_utc,
                    None,
                )
    return passed


def fetch_again(conn: sqlite3.Connection, service: Any, source: dict[str, Any], now_utc: int, user_id: int) -> None:
    """Skipped messages you asked to be read after all (`mail_retry`), with the PDFs a skipped message never fetched
    (the audit, 30 Oct: a skipped syllabus was read without its syllabus): theirs first, then the message waits to be
    read with them."""
    for r in rows(
        conn,
        "SELECT id, external_id FROM raw_inputs WHERE source_id = ? AND status = 'ignored' AND error = ?",
        [source["id"], WITH_PDFS],
    ):
        mail = gmail.read(service, r["external_id"])
        pdfs = [(pdf, gmail.attachment(service, mail.id, pdf.attachment_id)) for pdf in mail.pdfs]
        for pdf, content in pdfs:
            save(
                conn,
                user_id,
                source["id"],
                f"{mail.id}#{pdf.name}",
                pdf.name,
                "application/pdf",
                content,
                now_utc,
                None,
            )
        conn.execute("UPDATE raw_inputs SET status = 'new', error = NULL WHERE id = ?", [r["id"]])


def elsewhere(conn: sqlite3.Connection, user_id: int, source_id: int, text: str) -> str | None:
    """Why a message isn't read again: the very same one (headers and all) came to another of your accounts."""
    digest = hashlib.sha256(text.encode()).hexdigest()
    found = one(
        conn,
        "SELECT 1 FROM raw_inputs r JOIN sources s ON s.id = r.source_id WHERE s.user_id = ? "
        "AND s.kind IN ('gmail', 'mail') AND r.source_id != ? AND r.content_hash = ? LIMIT 1",
        [user_id, source_id, digest],
    )
    return ELSEWHERE if found else None


# "Send me your abstract by Nov 1": a person asking for something by a day, with no keyword in it.
BY_A_DAY = re.compile(
    r"\bby (?:(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*|tomorrow|tonight|noon|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{1,2}|\d{1,2}/\d{1,2})\b",
    re.IGNORECASE,
)


def why_skipped(mail: gmail.Mail, wanted: GmailSettings) -> str | None:
    """The pre-filter: mail from a domain you listed (or its subdomains) is read; so is mail with one of your
    keywords (or its plural), in the subject for bulk mail (whose bodies say "deadline" to sell things); so is
    mail from a person asking for something by a day. None means read it."""
    domain = mail.sender.rsplit("@", 1)[-1]
    if any(domain == d or domain.endswith("." + d) for d in wanted.sender_domains):
        return None
    words = "|".join(re.escape(k) for k in wanted.keywords)
    found = bool(words) and re.search(rf"\b({words})s?\b", mail.subject if mail.bulk else mail.text, re.IGNORECASE)
    if found or (not mail.bulk and BY_A_DAY.search(mail.text)):
        return None
    if mail.bulk:
        return "Bulk mail, no keyword in its subject and not from a sender you listed"
    return "No keyword you listed, and not from a sender you listed"


def save(
    conn: sqlite3.Connection,
    user_id: int,
    source_id: int,
    external_id: str,
    title: str,
    media_type: str,
    content: str,
    now_utc: int,
    skipped: str | None,
    thread: str | None = None,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO raw_inputs (user_id, source_id, external_id, received_utc, content_hash, title, "
        "media_type, content, status, error, thread_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            user_id,
            source_id,
            external_id,
            format_utc(now_utc),
            hashlib.sha256(content.encode()).hexdigest(),
            title,
            media_type,
            content,
            "ignored" if skipped else "new",
            skipped,
            thread,
        ],
    )


STATUS = {"extracted": "read", "ignored": "skipped", "failed": "failed", "new": "waiting"}


@query("mail_log")
def mail_log(ctx: Ctx, inp: MailLogInput) -> list[MailOut]:
    """The newest mail Friday saw: read, skipped by the pre-filter, failed or waiting, and why."""
    found = rows(
        ctx.conn,
        "SELECT r.*, (SELECT COUNT(*) FROM suggestions s WHERE s.raw_input_id = r.id) AS found FROM raw_inputs r "
        "JOIN sources o ON o.id = r.source_id WHERE r.user_id = ? AND o.kind IN ('gmail', 'mail') "
        "ORDER BY r.id DESC LIMIT ?",
        [ctx.user_id, inp.limit],
    )
    return [
        MailOut(
            id=r["id"],
            subject=r["title"] or "(no subject)",
            sender=next((line[6:] for line in r["content"].splitlines()[:1] if line.startswith("From: ")), ""),
            received=format_local(to_local(parse_utc(r["received_utc"]), ctx.tz)),
            status=STATUS[r["status"]],  # type: ignore[arg-type]
            why=r["error"],
            found=r["found"],
        )
        for r in found
    ]


@command("mail_retry")
def mail_retry(ctx: Ctx, inp: ItemRef) -> Changed:
    """Read a message with the AI after all (on the next sync): a skipped or failed one, or one read with nothing
    found in it (30 Oct: an invitation read as marketing)."""
    found = ctx.db.fetch("raw_inputs", {"id": inp.id})
    source = ctx.db.fetch("sources", {"id": found["source_id"]}) if found else None
    if source is None or source["kind"] not in MAIL_KINDS:
        raise FieldError("id", "only a message from your mail can be read again")
    nothing = (
        found is not None
        and found["status"] == "extracted"
        and not ctx.conn.execute("SELECT 1 FROM suggestions WHERE raw_input_id = ? LIMIT 1", [inp.id]).fetchone()
    )
    if found is None or (found["status"] not in ("ignored", "failed") and not nothing):
        raise FieldError("id", "only a skipped or failed message, or one with nothing found, can be read again")
    if found["status"] == "ignored" and found["media_type"] == "text/plain":
        # skipped, so its PDFs were never fetched: the next reading of your mail, due now, fetches them with it
        ctx.db.update("raw_inputs", {"id": inp.id}, {"error": WITH_PDFS})
        ctx.db.update("sources", {"id": source["id"]}, {"last_sync_utc": None})
        return Changed(message="It's read on the next sync, with its PDFs")
    ctx.db.update("raw_inputs", {"id": inp.id}, {"status": "new", "error": None})
    return Changed(message="It's read on the next sync")
