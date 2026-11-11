"""A stand-in for Trello's REST API (https://trello.com/1), the parts Friday uses, as Trello's reference has them:
GET members/me, GET members/me/cards (`filter=open`: the open cards you're a member of), GET members/me/boards (their
names), PUT cards/{id} (`dueComplete`). The OAuth 2.0 access token comes as a Bearer (C117). Cards look as Trello
sends them: `name`, `desc`, `due` (a UTC moment, or null), `dueComplete`, `idBoard`, `idMembers`, `closed`, `url`. A
due picked as a day in Trello is noon that day, your time."""

import itertools
import json
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from tests.integrations.kit import FakeService, Harness

PREFIX = "/1"
ACCESS = "trello-access-1"
ME = "5f1e0000000000000000aaaa"
ZONE = ZoneInfo("America/New_York")  # new_app's


def trello_due(when: str | None) -> str | None:
    if not when:
        return None
    local = datetime.fromisoformat(when) if "T" in when else datetime.combine(datetime.fromisoformat(when), time(12))
    return local.replace(tzinfo=ZONE).astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class FakeTrello(FakeService):
    host = "trello.com"

    def __init__(self, token: str):
        super().__init__(ACCESS)
        self.cards: dict[str, dict[str, Any]] = {}
        self.boards = {"b1": {"id": "b1", "name": "Personal"}, "b2": {"id": "b2", "name": "Team sprint"}}
        self.ids = itertools.count(1)

    def add(self, title: str, due: str | None = None, board: str = "b1", members: tuple[str, ...] = (ME,),
            **extra: Any) -> str:  # fmt: skip
        card_id = f"6720{next(self.ids):020x}"
        self.cards[card_id] = {
            "id": card_id, "name": title, "desc": extra.get("desc", ""), "due": trello_due(due), "start": None,
            "dueComplete": False, "idBoard": board, "idList": f"{board}-todo", "idMembers": list(members),
            "closed": False, "url": f"https://trello.com/c/{card_id[:8]}/{title.lower().replace(' ', '-')}",
        }  # fmt: skip
        return card_id

    def path(self, request: httpx.Request) -> str:
        return request.url.path.removeprefix(PREFIX)

    def respond(self, request: httpx.Request) -> httpx.Response:
        path, method, params = self.path(request), request.method, request.url.params
        if method == "GET" and path == "/members/me":
            return httpx.Response(200, json={"id": ME, "username": "maria", "fullName": "Maria Lopez"})
        if method == "GET" and path == "/members/me/cards":
            assert params.get("filter") == "open", params
            mine = [c for c in self.cards.values() if ME in c["idMembers"] and not c["closed"]]
            return httpx.Response(200, json=[{k: c[k] for k in ("id", *params["fields"].split(","))} for c in mine])
        if method == "GET" and path == "/members/me/boards":
            return httpx.Response(200, json=list(self.boards.values()))
        parts = path.strip("/").split("/")
        if method == "PUT" and len(parts) == 2 and parts[0] == "cards":
            card = self.cards.get(parts[1])
            if card is None:
                return httpx.Response(404, text="The requested resource was not found.")
            card.update({k: v for k, v in self.body(request).items() if k in ("dueComplete", "closed")})
            return httpx.Response(200, json=card)
        return httpx.Response(404, text=f"Cannot {method} {path}")


HARNESS = Harness(
    kind="trello",
    token=json.dumps({"access_token": ACCESS, "refresh_token": "trello-refresh-1", "expires_at": 4_102_444_800}),
    fake=FakeTrello,
    add=lambda fake, title, due=None, minutes=None: fake.add(title, due),
    move=lambda fake, card, due: fake.cards[card].update(due=trello_due(due)),
    rename=lambda fake, card, title: fake.cards[card].update(name=title),
    finish=lambda fake, card: fake.cards[card].update(dueComplete=True),
    is_done=lambda fake, card: fake.cards[card]["dueComplete"],
    two_way=True,
    lengths=False,
)
