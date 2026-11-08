"""An error as you'd want to read it on the spot (8 Nov: "make all errors and warnings very user friendly so that they
can debug it on the spot"): what happened in words, and what to do, or that Friday tries again by itself. What a
programmer wants (the exception, its text, the address) goes to the log, never in front of you: a feed's link in an
error was its private token on screen, and "HttpError: <HttpError 404 when requesting https://…>" said nothing.

Errors are told apart by their type's name and the status they carry, so this needs none of the libraries that
raise them (httpx, Google's client, the AI providers' SDKs)."""

import logging
import re

log = logging.getLogger("friday.sources")

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


DETAILS = "the details are in Settings → Advanced → Diagnose"


def status_of(error: BaseException) -> int | None:
    """The HTTP status an error carries, however its library keeps it."""
    for holder in (error, getattr(error, "response", None), getattr(error, "resp", None)):
        for name in ("status_code", "status"):
            value = getattr(holder, name, None) if holder is not None else None
            if isinstance(value, int) and 100 <= value < 600:
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
    return None


def plain(error: BaseException, who: str = "It") -> str:
    """`who` is what failed, as the sentence should start: "Google", "The AI", "The calendar link"."""
    kind = type(error).__name__
    said = str(error)
    status = status_of(error)
    # Friday's own words (raised as LookupError, or one of Friday's own errors): just the words
    if said and (kind == "LookupError" or type(error).__module__.startswith("friday.")):
        return said[0].upper() + said[1:]
    if status is not None:
        return by_status(status, who, said)
    if "Timeout" in kind or isinstance(error, TimeoutError):
        return f"{who} didn't answer in time. Friday tries again by itself."
    if kind in ("ConnectError", "ConnectionError", "RemoteProtocolError", "APIConnectionError") or isinstance(
        error, ConnectionError
    ):
        return f"{who} couldn't be reached. Friday tries again by itself; if it lasts, check the address in Settings."
    if kind == "JSONDecodeError" or "Expecting value" in said:
        return f"{who} answered with something Friday couldn't read. Friday tries again by itself; {DETAILS}."
    # What it said is kept, short and without links: a model's refusal ("tool_choice is not supported") is the reason.
    reason = f"{kind}: {without_links(said)[:160]}" if said else kind
    return f"{who} failed in a way Friday didn't expect ({reason}). Friday tries again by itself; {DETAILS}."


def by_status(status: int, who: str, said: str) -> str:
    if status in (401, 403):
        if who == "The AI":
            return f"The AI refused the key ({status}). Check or replace it in Settings → AI."
        return f"{who} refused Friday's access ({status}). Connect it again in Settings → Integrations."
    if status == 400 and who == "The AI":
        return "The AI model won't take Friday's request (400). Choose another model in Settings → AI."
    if status == 404:
        if who == "The AI" and "model" in said.lower():
            return "That AI model isn't offered any more (404). Choose another in Settings → AI."
        gone = "it may have moved or been deleted. Check it in Settings → Integrations."
        return f"{who} isn't there any more (404): {gone}"
    if status == 429:
        return f"{who} asked Friday to slow down (429: too many requests). Friday waits and tries again by itself."
    if status >= 500:
        later = "Friday tries again by itself; nothing to do unless it lasts."
        return f"{who} had a problem on its side ({status}). {later}"
    return f"{who} said no ({status}); {DETAILS}."


def without_links(text: str) -> str:
    """An error's words with any address taken out: a feed's link holds its private token."""
    # any scheme (webcal:// too), and a bare path with a query ("url: /feed.ics?token=…")
    return re.sub(r"\b[a-z][a-z0-9+.-]*://\S+|(?<=url: )/\S*\?\S+", "(link)", text, flags=re.IGNORECASE)


def kept(error: BaseException, who: str = "It") -> str:
    """What's kept as a source's error, shown in Settings and the banner: in words (`plain`), except an expired
    sign-in and no internet, kept as Google and the system said them, which "Connect again" and the offline line look
    for. The exception itself goes to the log, without its links."""
    raw = f"{type(error).__name__}: {error}"
    log.warning("%s: %s", who, without_links(raw)[:500])
    if SIGN_IN_GONE.search(raw) or OFFLINE.search(raw):
        return without_links(raw)[:300]
    return plain(error, who)[:300]
