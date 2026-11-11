"""Trello (C96, your choice: both ways; C102, then C117). Signed in on Atlassian's page (integrations/oauth.py) through
Friday's own Trello app, a public OAuth 2.0 client (11 Nov: Trello's apps are OAuth 2.0 now, PKCE required, so no key
and pasted token); its client id is kept out of the code (integrations/keys.py, trello_client_id). The access
token lasts an hour and is renewed by the refresh token (offline_access), which lasts ninety days of not being used.
Then Trello's REST API (https://trello.com/1) with the token as a Bearer.

Your answers (10 Nov): the cards that come in are the open cards you're on, on any board (GET members/me/cards); done
here ticks the card's due date complete (PUT cards/{id} dueComplete), and opened again unticks it. A card ticked
complete, or archived, in Trello is done here. Trello's due is always a moment (UTC); a card keeps no length."""

import os
from typing import Any, ClassVar, Literal

from friday.integrations import keys
from friday.integrations.base import Caps, ConnectorError, Http, Remote, Transport
from friday.integrations.oauth import Provider, Session

API = "https://trello.com/1"
CARD_FIELDS = "name,desc,due,dueComplete,url,idBoard,closed"


def client_id() -> str:
    return keys.get("trello_client_id")  # trello.com/power-ups/admin → Friday → OAuth 2.0 → Client ID


PROVIDER = Provider(
    kind="trello", name="Trello", authorize="https://auth.atlassian.com/authorize",
    token="https://auth.atlassian.com/oauth/token", client_id=client_id,
    scopes=("read:board:trello", "write:board:trello", "read:member:trello", "offline_access"),
    extra={"prompt": "consent"},
)  # fmt: skip


class Trello:
    kind: ClassVar[str] = "trello"
    name: ClassVar[str] = "Trello"
    caps: ClassVar[Caps] = Caps(two_way=True, lengths=False)
    provider: ClassVar[Provider] = PROVIDER

    def __init__(self, token: str, config: dict[str, Any] | None = None, transport: Transport = None):
        self.session = Session(PROVIDER, token, (config or {}).get("_keep"))
        base = os.environ.get("FRIDAY_API_TRELLO") or API  # another address: only a fake service, in system tests

        def bearer() -> dict[str, str]:
            return {"Authorization": f"Bearer {self.session.access()}"}

        self.http = Http(self.name, base, {}, transport, fresh=bearer)

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
