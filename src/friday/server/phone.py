"""Friday on your phone over Tailscale (C61), the server's side: a second listener on this Mac's Tailscale address
while Settings → Phone is on, the pairing page a phone's camera opens, and one rule for every request.

The rule: a request must be sent to one of Friday's own addresses (this Mac's loopback, or its Tailscale address and
name), and one from anywhere but this Mac must come from a paired phone. The first closes a hole a web page could use:
a site whose name was made to point at this Mac (DNS rebinding) reached Friday as if it were Friday's own page, as
the Origin check compares a page with the address it was sent to. The second is the pairing you chose: nobody else on
your tailnet opens your Friday."""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("friday.phone")

THIS_MAC = {"127.0.0.1", "::1", "localhost"}
TEST_CLIENT = "testclient"  # Starlette's test client: its requests come from here, to "testserver"


@dataclass
class Tailnet:
    """Where Friday answers on your tailnet right now: nothing while Settings → Phone is off or Tailscale isn't up."""

    address: str | None = None
    name: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def names(self) -> set[str]:
        with self.lock:
            return {n for n in (self.address, self.name) if n}


def host_of(header: str | None) -> str:
    """The name a request was sent to, without its port: "laptop.example.ts.net:8765" → "laptop.example.ts.net"."""
    host = (header or "").strip().lower()
    if host.startswith("["):  # [::1]:8765
        return host[1 : host.find("]")] if "]" in host else host
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def own_address(host_header: str | None, client: str | None, tailnet: set[str]) -> bool:
    """Whether a request was sent to one of Friday's own addresses."""
    host = host_of(host_header)
    return host in THIS_MAC or host in tailnet or (client == TEST_CLIENT and host == "testserver")


def from_this_mac(client: str | None) -> bool:
    return client in ("127.0.0.1", "::1", TEST_CLIENT)


def refusal(path: str, host_header: str | None, client: str | None, tailnet: set[str],
            paired: Callable[[], bool]) -> tuple[int, str] | None:  # fmt: skip
    """Why a request is refused (its status and words), or None to let it through. `paired` says whether it carries a
    paired phone's sign-in; it's asked only of a request from another device."""
    if not own_address(host_header, client, tailnet):
        return 421, "Friday only answers at its own address. Open it from the Friday app or Settings → Phone."
    if from_this_mac(client) or path in ("/pair", "/api/pair", "/manifest.webmanifest"):
        return None
    if path.startswith("/mcp"):  # assistants run on this Mac; the tailnet's listener has no MCP session of its own
        return 403, "Assistants connect to Friday on this Mac, not over the tailnet."
    if paired():
        return None
    return 401, (
        "This device isn't paired with your Friday. On your Mac, open Friday → Settings → Phone and scan the code "
        "shown there with this phone's camera."
    )


PAIR_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pair with Friday</title>
<style>body{font:16px/1.5 -apple-system,system-ui,sans-serif;margin:0;display:grid;place-items:center;min-height:100vh;
background:#17181c;color:#e8e6e1}main{max-width:22rem;padding:2rem}h1{font-size:1.4rem}</style></head>
<body><main><h1>Pairing with Friday…</h1><p id="said">One moment.</p></main>
<script>
// The code is after the #, which the browser never sends in the address, so it's in no log on the way.
const code = location.hash.slice(1)
const said = document.getElementById("said")
const device = /iPhone/.test(navigator.userAgent) ? "iPhone" : /iPad/.test(navigator.userAgent) ? "iPad"
  : /Android/.test(navigator.userAgent) ? "Android phone" : "Phone"
fetch("/api/pair", {method: "POST", headers: {"content-type": "application/json"},
  body: JSON.stringify({code, device}), credentials: "same-origin"})
  .then(r => r.json().then(b => [r.ok, b]))
  .then(([ok, b]) => { if (ok) location.replace("/"); else said.textContent = b.message })
  .catch(() => {
    said.textContent = "Friday didn't answer. Check that your Mac is awake and on Tailscale, then scan again."
  })
</script></body></html>"""


class TailnetListener(threading.Thread):
    """Friday answering on this Mac's Tailscale address too, while Settings → Phone is on and Tailscale is up:
    checked every few seconds, so switching it on or Tailscale coming up needs no restart."""

    def __init__(self, app: Any, port: int, is_on: Callable[[], bool], tailnet: Tailnet,
                 read: Callable[[], tuple[str | None, str | None]], every_s: float = 5.0,
                 bind: bool = True) -> None:  # fmt: skip
        super().__init__(name="tailnet-listener", daemon=True)
        self.app, self.port, self.is_on, self.tailnet = app, port, is_on, tailnet
        self.read, self.every_s, self.bind = read, every_s, bind
        self.server: Any = None
        self.serving: str | None = None
        self.stopping = threading.Event()

    def run(self) -> None:
        while not self.stopping.is_set():
            try:
                self.step()
            except Exception:  # a bad check mustn't stop the next one
                log.exception("checking the tailnet failed")
            self.stopping.wait(self.every_s)
        self.close()

    def step(self) -> None:
        address, name = self.read() if self.is_on() else (None, None)
        with self.tailnet.lock:
            self.tailnet.address, self.tailnet.name = address, name
        if self.bind and address != self.serving:
            self.close()
            if address:
                self.open(address)

    def open(self, address: str) -> None:
        import uvicorn

        config = uvicorn.Config(self.app, host=address, port=self.port, log_level="warning", lifespan="off",
                                proxy_headers=False, timeout_graceful_shutdown=2)  # fmt: skip
        server = uvicorn.Server(config)
        running = threading.Thread(target=server.run, name="tailnet-server", daemon=True)
        running.start()
        for _ in range(50):  # up to five seconds to start listening
            if server.started or not running.is_alive():
                break
            time.sleep(0.1)
        if not server.started:  # the address taken, say: tried again at the next check, said in the log
            server.should_exit = True
            log.warning("couldn't answer on the tailnet at %s:%s; trying again shortly", address, self.port)
            return
        self.server, self.serving = server, address
        log.info("Friday answers on the tailnet at %s:%s", address, self.port)

    def close(self) -> None:
        if self.server is not None:
            self.server.should_exit = True
            log.info("Friday stopped answering on the tailnet")
        self.server, self.serving = None, None

    def stop(self) -> None:
        self.stopping.set()
