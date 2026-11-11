"""Trello (C96, your choice: both ways; C102). Its REST API at https://api.trello.com/1, with Friday's own app key
(public by Trello's design: it names the app; the Power-Up's secret is never used) and your token, sent as
`Authorization: OAuth oauth_consumer_key="…", oauth_token="…"` so the token is never in an address.

Your answers (10 Nov): Friday's own key, so connecting is Allow on Trello's page and paste the token it shows; the
cards that come in are the open cards you're on, on any board (GET members/me/cards); done here ticks the card's due
date complete (PUT cards/{id} dueComplete), and opened again unticks it. A card ticked complete, or archived, in Trello
is done here. Trello's due is always a moment (UTC); a card keeps no length."""

import os
from typing import Any, ClassVar, Literal
from urllib.parse import urlencode

from friday.integrations.base import Caps, ConnectorError, Http, Remote, Transport

API = "https://api.trello.com/1"
# Friday's Power-Up's API key (trello.com/power-ups/admin → Friday → API key): set once by Friday's developer
APP_KEY = ""
CARD_FIELDS = "name,desc,due,dueComplete,url,idBoard,closed"


def app_key() -> str:
    return (os.environ.get("FRIDAY_TRELLO_KEY") or APP_KEY).strip()


def token_page() -> str | None:
    """Trello's page that asks you to Allow Friday and then shows your token; None while Friday has no key."""
    key = app_key()
    if not key:
        return None
    asked = {"key": key, "name": "Friday", "expiration": "never", "scope": "read,write", "response_type": "token"}
    return f"https://trello.com/1/authorize?{urlencode(asked)}"


class Trello:
    kind: ClassVar[str] = "trello"
    name: ClassVar[str] = "Trello"
    caps: ClassVar[Caps] = Caps(two_way=True, lengths=False)
    token_page = staticmethod(token_page)

    def __init__(self, token: str, config: dict[str, Any] | None = None, transport: Transport = None):
        key = app_key()
        if not key:
            raise ConnectorError("token", "Trello isn't ready in this copy of Friday yet: it has no Trello app key")
        if not token.strip():
            raise ConnectorError("token", "No Trello token: press Allow on Trello's page and paste the token it shows")
        base = os.environ.get("FRIDAY_API_TRELLO") or API  # another address: only a fake service, in system tests
        said = f'OAuth oauth_consumer_key="{key}", oauth_token="{token.strip()}"'
        self.http = Http(self.name, base, {"Authorization": said}, transport)

    def check(self) -> str:
        me = self.http.json("GET", "/members/me", params={"fields": "username,fullName"})
        if not isinstance(me, dict):
            raise ConnectorError("answer", "Trello's answer about you came back in a shape Friday doesn't know")
        return str(me.get("fullName") or me.get("username") or "your Trello")

    def read(self) -> list[Remote]:
        cards = self.http.json("GET", "/members/me/cards", params={"filter": "open", "fields": CARD_FIELDS})
        boards = self.http.json("GET", "/members/me/boards", params={"filter": "all", "fields": "name"})
        if not isinstance(cards, list) or not isinstance(boards, list):
            raise ConnectorError("answer", "Trello's list of cards came back in a shape Friday doesn't know")
        names = {b["id"]: str(b.get("name") or "") for b in boards if isinstance(b, dict)}
        return [remote(c, names.get(c.get("idBoard"), "")) for c in cards
                if not c.get("closed") and not c.get("dueComplete")]  # fmt: skip

    def write(self, external_id: str, op: Literal["done", "reopen"]) -> None:
        self.http.call("PUT", f"/cards/{external_id}", json={"dueComplete": op == "done"})


def remote(card: dict[str, Any], board: str) -> Remote:
    notes = str(card.get("desc") or "").strip()
    where = f"On Trello: {board}" if board else ""
    return Remote(
        external_id=str(card["id"]),
        title=str(card.get("name") or "Untitled card").strip(),
        due=str(card["due"]) if card.get("due") else None,  # UTC: the sync puts it on your clock
        notes="\n\n".join(x for x in (notes, where) if x),
        url=card.get("url"),
        done=bool(card.get("dueComplete")),
        firm=True,
    )
