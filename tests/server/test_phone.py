"""Friday on your phone over Tailscale (C61). Glass box: the address a request was sent to, which requests are refused,
this Mac's Tailscale address and name read from the system's words, the listener opening and closing with the
switch. Black box through the commands: switching it on, a pairing code good once for ten minutes, a phone removed.
The whole server: a phone that isn't paired is told how to pair, the code pairs it, and it then opens Friday; a page
from a borrowed name (DNS rebinding) is refused even from this Mac."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from friday.commands import phones
from friday.core.items import FieldError
from friday.server.phone import Tailnet, TailnetListener, host_of, own_address, refusal
from friday.sync import tailnet
from tests.commands.helpers import App, new_app

NAME = "mac.example.ts.net"
ADDRESS = "100.101.1.2"
PHONE = ("100.101.9.9", 50000)
IFCONFIG = """lo0: flags=8049<UP,LOOPBACK> mtu 16384
\tinet 127.0.0.1 netmask 0xff000000
en0: flags=8863<UP,BROADCAST> mtu 1500
\tinet 192.168.1.20 netmask 0xffffff00 broadcast 192.168.1.255
utun4: flags=8051<UP,POINTOPOINT> mtu 1280
\tinet 100.101.1.2 --> 100.101.1.2 netmask 0xffffffff
"""


class TestGlassBox:
    @pytest.mark.parametrize(
        ("header", "host"),
        [("127.0.0.1:8765", "127.0.0.1"), ("[::1]:8765", "::1"), (f"{NAME}:8765", NAME), ("LOCALHOST", "localhost")],
    )
    def test_the_name_a_request_was_sent_to(self, header: str, host: str) -> None:
        assert host_of(header) == host

    def test_own_addresses_and_borrowed_ones(self) -> None:
        names = {NAME, ADDRESS}
        assert own_address("127.0.0.1:8765", "127.0.0.1", set())
        assert own_address(f"{NAME}:8765", PHONE[0], names)
        assert not own_address("evil.example:8765", "127.0.0.1", names)  # a borrowed name, even from this Mac
        assert not own_address(f"{NAME}:8765", PHONE[0], set())  # Phone off: the tailnet name isn't Friday's
        assert own_address("testserver", "testclient", set()) and not own_address("testserver", "127.0.0.1", set())

    def test_who_is_refused(self) -> None:
        names = {NAME}
        never = lambda: pytest.fail("this Mac is never asked to be paired")  # noqa: E731
        assert refusal("/api/q/status", "127.0.0.1:8765", "127.0.0.1", names, never) is None
        assert refusal("/api/q/status", f"{NAME}:8765", PHONE[0], names, lambda: True) is None
        status, words = refusal("/api/q/status", f"{NAME}:8765", PHONE[0], names, lambda: False) or (0, "")
        assert status == 401 and "Settings → Phone" in words and "scan the code" in words
        assert refusal("/pair", f"{NAME}:8765", PHONE[0], names, lambda: False) is None  # how a phone gets paired
        assert (refusal("/", "evil.example", "127.0.0.1", names, never) or (0, ""))[0] == 421

    def test_this_macs_tailscale_address_and_name(self) -> None:
        assert tailnet.address(IFCONFIG) == ADDRESS
        assert tailnet.address("inet 192.168.1.20 netmask") is None
        assert tailnet.name('{"Self": {"DNSName": "mac.example.ts.net."}}') == NAME
        assert tailnet.name("not json") is None and tailnet.name("{}") is None

    def test_the_listener_follows_the_switch_and_tailscale(self) -> None:
        on, read = [True], [(ADDRESS, NAME)]
        net = Tailnet()
        listener = TailnetListener(object(), 8765, lambda: on[0], net, lambda: read[0])
        opened: list[str] = []
        listener.open = lambda address: (opened.append(address), setattr(listener, "serving", address))  # type: ignore[method-assign]
        listener.step()
        assert opened == [ADDRESS] and net.names() == {ADDRESS, NAME}
        listener.step()
        assert opened == [ADDRESS]  # already serving there
        read[0] = ("100.101.7.7", NAME)
        listener.step()
        assert opened == [ADDRESS, "100.101.7.7"]  # a new address: closed and opened again
        on[0] = False
        listener.step()
        assert listener.serving is None and net.names() == set()


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> App:
    monkeypatch.setattr(tailnet, "address", lambda *_: ADDRESS)
    monkeypatch.setattr(tailnet, "name", lambda *_: NAME)
    return new_app(tmp_path)


class TestBlackBox:
    def test_a_code_needs_the_switch_on(self, app: App) -> None:
        with pytest.raises(FieldError, match="Switch on"):
            app.do("phone_pair")

    def test_a_code_pairs_once_within_ten_minutes(self, app: App) -> None:
        app.do("phone_set", on=True)
        made = app.do("phone_pair")
        assert made["url"].startswith(f"http://{NAME}:8765/pair#") and "<svg" in made["svg"] and made["minutes"] == 10
        code = made["url"].split("#", 1)[1]
        session = phones.pair(app.conn, 1, code, "iPhone", app.now_utc)
        assert session and phones.known(app.conn, 1, session, app.now_utc)
        assert phones.pair(app.conn, 1, code, "iPhone", app.now_utc) is None  # once
        late = app.do("phone_pair")["url"].split("#", 1)[1]
        assert phones.pair(app.conn, 1, late, "iPhone", app.now_utc + 11) is None  # ten minutes
        assert not phones.known(app.conn, 1, "ph_guess", app.now_utc)

    def test_a_removed_phone_cant_come_back_without_pairing(self, app: App) -> None:
        app.do("phone_set", on=True)
        code = app.do("phone_pair")["url"].split("#", 1)[1]
        session = phones.pair(app.conn, 1, code, "iPhone", app.now_utc) or ""
        (phone,) = app.do("phone_status")["phones"]
        assert phone["name"] == "iPhone" and app.do("phone_status")["name"] == NAME
        assert "can't open Friday" in app.do("phone_forget", id=phone["id"])["message"]
        assert not phones.known(app.conn, 1, session, app.now_utc)


@pytest.fixture
def server(app: App, tmp_path: Path) -> Iterator[tuple[App, TestClient, TestClient]]:
    from friday.server.app import create_app

    net = Tailnet(address=ADDRESS, name=NAME)
    served = create_app(tmp_path / "friday.db", clock=lambda: app.now_utc, background=False, plugin_dir=tmp_path,
                        tailnet=net)  # fmt: skip
    phone = TestClient(served, base_url=f"http://{NAME}:8765", client=PHONE)  # the app is started once, by the Mac's
    with TestClient(served, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 50000)) as mac:
        yield app, mac, phone


def test_a_phone_pairs_by_its_code_and_then_opens_friday(server: tuple[App, TestClient, TestClient]) -> None:
    app, mac, phone = server
    refused = phone.get("/api/q/status")
    assert refused.status_code == 401 and "Settings → Phone" in refused.json()["message"]
    assert phone.get("/").status_code == 401  # the page too, in words
    assert phone.get("/pair").status_code == 200
    mac.post("/api/c/phone_set", json={"on": True})
    code = mac.post("/api/c/phone_pair", json={}).json()["result"]["url"].split("#", 1)[1]
    paired = phone.post("/api/pair", json={"code": code, "device": "iPhone"})
    assert paired.status_code == 200 and "friday_phone" in paired.cookies
    assert phone.get("/api/q/status").status_code == 200
    again = phone.post("/api/pair", json={"code": code, "device": "iPhone"})
    assert again.status_code == 403 and "Settings → Phone" in again.json()["message"]


def test_a_borrowed_name_is_refused_even_from_this_mac(server: tuple[App, TestClient, TestClient]) -> None:
    """DNS rebinding: a page from evil.example whose name now points at this Mac reaches Friday as evil.example."""
    _, mac, _ = server
    answer = mac.get("/api/q/status", headers={"host": "evil.example:8765"})
    assert answer.status_code == 421 and "its own address" in answer.json()["message"]
    assert mac.get("/api/q/status").status_code == 200


class TestFoundInReview:
    """Review, 8 Nov: who may open Friday is yours alone to change, and the tailnet's listener is careful."""

    def test_an_assistant_never_reaches_the_phone_commands(self, app: App) -> None:
        from friday.server.mcp import HIDDEN

        assert {"phone_set", "phone_pair", "phone_forget"} <= HIDDEN
        app.actor = "mcp:claude"
        with pytest.raises(FieldError, match="Only you"):
            app.do("phone_set", on=True)

    def test_assistants_dont_connect_over_the_tailnet(self) -> None:
        refused = refusal("/mcp", f"{NAME}:8765", PHONE[0], {NAME}, lambda: True)
        assert refused is not None and refused[0] == 403

    def test_a_listener_that_couldnt_start_tries_again(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import uvicorn

        class Refused:
            started = False
            should_exit = False

            def __init__(self, config: object) -> None:
                pass

            def run(self) -> None:
                return  # as when the address is taken: it ends without having started

        monkeypatch.setattr(uvicorn, "Server", Refused)
        listener = TailnetListener(object(), 8765, lambda: True, Tailnet(), lambda: (ADDRESS, NAME))
        listener.step()
        assert listener.serving is None  # not marked as serving, so the next check tries again
