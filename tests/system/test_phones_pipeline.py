"""Phone pairing, the whole pipeline (tests/features.toml: phones; 24 Nov, the user: "build an extensive test suite ...
i want to make sure that absolutely nothing can break without our tests flagging it"): a real `fridayd serve`; Settings
→ Phone's switch, its pairing code, a phone trading the code for a sign-in, and Remove, each over HTTP as the page and
the phone send them, read back through `phone_status` and, on the tailnet, by what the phone can then open. What
needs this Mac on Tailscale is skipped where it isn't (GitHub's machines); test_phone_system.py has the rest of the
tailnet's side."""

import time
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest

from friday.sync.tailnet import address, name
from tests.system.test_beat_plan_system import SLEEP, Friday

HERE = address()
on_tailscale = pytest.mark.skipif(HERE is None, reason="Tailscale isn't up on this machine")


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("phones"))
    try:
        server.c("settings_set", key="sleep", value=SLEEP)
        yield server
    finally:
        server.stop()


def refused(friday: Friday, verb: str, **body: Any) -> str:
    """A command Friday turns down: the 422 and the words it gives ("field: words")."""
    answer = friday.http.post(f"/api/c/{verb}", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()["message"]


def pair(friday: Friday, code: str, device: str) -> httpx.Response:
    """The phone's camera opened the code: its page posts it (server/phone.py's pairing page)."""
    return friday.http.post("/api/pair", json={"code": code, "device": device})


def code_of(friday: Friday) -> str:
    return friday.c("phone_pair")["url"].split("#", 1)[1]


def paired(friday: Friday) -> dict[str, dict]:
    return {p["name"]: p for p in friday.q("phone_status")["phones"]}


def waited(check: Callable[[], Any], seconds: float = 20) -> Any:
    end = time.time() + seconds
    while time.time() < end:
        found = check()
        if found:
            return found
        time.sleep(0.5)
    raise TimeoutError("waited too long")


def test_1_off_at_first_and_no_code_is_given_until_switched_on(friday: Friday) -> None:
    status = friday.q("phone_status")
    assert (status["on"], status["phones"]) == (False, [])
    assert (status["address"], status["name"]) == (address(), name())  # what this Mac's Tailscale says
    assert friday.q("settings")["phone"] == {"on": False}
    assert refused(friday, "phone_pair") == "phone: Switch on Use Friday on my phone first"


def test_2_switched_on_friday_says_so_and_keeps_it(friday: Friday) -> None:
    out = friday.c("phone_set", on=True)
    assert out["message"] == "Friday answers on your tailnet now: pair your phone with the code in Settings → Phone"
    assert friday.q("phone_status")["on"] is True and friday.q("settings")["phone"] == {"on": True}


@on_tailscale
def test_3_a_code_pairs_one_phone_once(friday: Friday) -> None:
    made = friday.c("phone_pair")
    where = name() or address()
    url, code = made["url"].split("#", 1)
    assert url.startswith(f"http://{where}:") and url.endswith("/pair")  # its port: the BUG test below
    assert made["minutes"] == 10 and made["svg"].lstrip().startswith("<svg") and len(code) >= 20
    answer = pair(friday, code, "iPhone")
    assert answer.status_code == 200 and answer.json() == {"paired": True}
    assert answer.cookies.get("friday_phone", "").startswith("ph_")  # its own sign-in, kept by the phone
    phone = paired(friday)["iPhone"]
    assert phone["paired"] and phone["last_used"] is None
    again = pair(friday, code, "iPad")  # the same code: used
    assert again.status_code == 403 and again.json()["message"].startswith("That pairing code has expired or was used")
    assert set(paired(friday)) == {"iPhone"}
    assert pair(friday, "made-up", "iPad").status_code == 403


@on_tailscale
# 24 Nov: found by this test (the link named Settings' port, not --port's); fixed
def test_3b_the_pairing_link_names_the_port_friday_answers_on(friday: Friday) -> None:
    url = friday.c("phone_pair")["url"].split("#", 1)[0]
    assert url.endswith(f":{friday.port}/pair")


@on_tailscale
def test_4_two_phones_of_one_name_are_told_apart_and_each_code_is_new(friday: Friday) -> None:
    first, second = code_of(friday), code_of(friday)
    assert first != second  # two codes waiting: both good
    assert pair(friday, second, "iPhone").status_code == 200
    assert pair(friday, first, "iPhone").status_code == 200
    assert set(paired(friday)) == {"iPhone", "iPhone 2", "iPhone 3"}


@on_tailscale
def test_5_a_phone_removed_is_gone_and_cant_be_removed_twice(friday: Friday) -> None:
    phone = paired(friday)["iPhone 2"]
    out = friday.c("phone_forget", id=phone["id"])
    assert out["message"] == "Removed iPhone 2: it can't open Friday until it's paired again"
    assert set(paired(friday)) == {"iPhone", "iPhone 3"}
    assert refused(friday, "phone_forget", id=phone["id"]) == "id: That phone isn't paired any more"


def test_6_removing_a_phone_never_paired_is_refused(friday: Friday) -> None:
    before = friday.q("phone_status")["phones"]
    assert refused(friday, "phone_forget", id="nope") == "id: That phone isn't paired any more"
    assert friday.q("phone_status")["phones"] == before


@on_tailscale
def test_7_on_the_tailnet_a_removed_phone_is_turned_away(friday: Friday) -> None:
    there = f"http://{HERE}:{friday.port}"

    def reach(phone: httpx.Client) -> httpx.Response | None:
        try:
            return phone.get(f"{there}/api/q/status")
        except httpx.HTTPError:
            return None

    answer = pair(friday, code_of(friday), "Pixel")
    phone = httpx.Client(timeout=5, cookies={"friday_phone": answer.cookies["friday_phone"]})
    assert waited(lambda: reach(phone)).status_code == 200  # paired: it opens Friday
    assert paired(friday)["Pixel"]["last_used"] is not None  # and when it last did is noted
    friday.c("phone_forget", id=paired(friday)["Pixel"]["id"])
    refused_now = reach(phone)
    assert refused_now is not None and refused_now.status_code == 401
    assert "isn't paired with your Friday" in refused_now.json()["message"]


def test_8_switched_off_friday_says_so_and_paired_phones_stay(friday: Friday) -> None:
    before = friday.q("phone_status")["phones"]
    out = friday.c("phone_set", on=False)
    assert out["message"] == ("Friday answers on this Mac alone now; paired phones stay paired for when it's back on")
    status = friday.q("phone_status")
    assert status["on"] is False and status["phones"] == before
    assert refused(friday, "phone_pair") == "phone: Switch on Use Friday on my phone first"
