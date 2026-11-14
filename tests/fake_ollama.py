"""A stand-in for Ollama, the app that runs open models on a Mac: what it has, a download streamed as Ollama streams
it (in layers, with progress), removals, its model list and its OpenAI-style chat. One core, served two ways: as an
httpx transport inside a test, and as a real HTTP server on this Mac for the system tests (`python -m
tests.fake_ollama PORT`). Nothing is downloaded and no model runs."""

import json
import sys
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx

GB = 1_000_000_000


class FakeOllama:
    def __init__(self, models: dict[str, int] | None = None, answer: Any = None) -> None:
        self.models: dict[str, int] = dict(models or {})  # full name → bytes
        self.pulled: list[str] = []
        self.deleted: list[str] = []
        self.chats: list[dict[str, Any]] = []
        self.fail_pull: str | None = None  # an error said mid-download
        self.gate: threading.Event | None = None  # when set: the download waits on it after its first layer
        self.thinking: threading.Event | None = None  # when set: a chat waits on it, as a slow model does
        self.layers = 3
        self.answer = answer if answer is not None else {"reply": "", "actions": []}
        self.lock = threading.Lock()

    # The core: (status, body) or (status, lines to stream).

    def handle(self, method: str, path: str, body: dict[str, Any]) -> tuple[int, Any]:
        if method == "GET" and path == "/api/tags":
            with self.lock:
                return 200, {"models": [{"name": n, "model": n, "size": s} for n, s in sorted(self.models.items())]}
        if method == "GET" and path == "/v1/models":
            with self.lock:
                return 200, {"object": "list", "data": [{"id": n, "object": "model"} for n in sorted(self.models)]}
        if method == "DELETE" and path == "/api/delete":
            name = body.get("model", "")
            with self.lock:
                self.deleted.append(name)
                found = self.models.pop(name, None)
            return (200, {}) if found is not None else (404, {"error": f"model '{name}' not found"})
        if method == "POST" and path == "/api/pull":
            return 200, self.pull(body.get("model", ""))
        if method == "POST" and path == "/v1/chat/completions":
            with self.lock:
                self.chats.append(body)
                here = body.get("model") in self.models
            if not here:
                return 404, {"error": {"message": f'model "{body.get("model")}" not found, try pulling it first'}}
            if self.thinking is not None:
                self.thinking.wait(60)
            answer = self.answer(body) if callable(self.answer) else self.answer
            return 200, {"choices": [{"message": {"role": "assistant", "content": json.dumps(answer)},
                                      "finish_reason": "stop"}],
                         "usage": {"prompt_tokens": 400, "completion_tokens": 40}}  # fmt: skip
        return 404, {"error": "not found"}

    def pull(self, name: str) -> Iterator[dict[str, Any]]:
        self.pulled.append(name)
        yield {"status": "pulling manifest"}
        size = 2 * GB
        for n in range(self.layers):
            digest = f"sha256:{n:064d}"
            total = size // self.layers
            yield {"status": f"pulling {digest[:19]}", "digest": digest, "total": total, "completed": total // 2}
            if n == 0 and self.gate is not None:
                self.gate.wait(10)
            if self.fail_pull:
                yield {"error": self.fail_pull}
                return
            yield {"status": f"pulling {digest[:19]}", "digest": digest, "total": total, "completed": total}
        yield {"status": "verifying sha256 digest"}
        yield {"status": "writing manifest"}
        with self.lock:
            self.models[name] = size
        yield {"status": "success"}

    # Inside a test.

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content) if request.content else {}
            status, out = self.handle(request.method, request.url.path, body)
            if isinstance(out, dict):
                return httpx.Response(status, json=out)
            return httpx.Response(status, content=b"".join(json.dumps(line).encode() + b"\n" for line in out))

        return httpx.MockTransport(handle)

    # As a server on this Mac.

    def serve(self, port: int) -> ThreadingHTTPServer:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def answer(self, method: str) -> None:
                length = int(self.headers.get("content-length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}") if length else {}
                status, out = fake.handle(method, self.path.split("?")[0], body)
                if isinstance(out, dict):
                    data = json.dumps(out).encode()
                    self.send_response(status)
                    self.send_header("content-type", "application/json")
                    self.send_header("content-length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                self.send_response(status)
                self.send_header("content-type", "application/x-ndjson")
                self.end_headers()
                for line in out:
                    self.wfile.write(json.dumps(line).encode() + b"\n")
                    self.wfile.flush()

            def do_GET(self) -> None:  # noqa: N802
                self.answer("GET")

            def do_POST(self) -> None:  # noqa: N802
                self.answer("POST")

            def do_DELETE(self) -> None:  # noqa: N802
                self.answer("DELETE")

        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server


def control(fake: FakeOllama) -> Callable[[str], None]:
    """For the system tests: commands on stdin ("have NAME", "gate", "release", "fail TEXT", "answer JSON", "think",
    "answered", "state", which says what the last chat was told and, in `all_told`, what every chat was: a background
    job's chat can come after the one a test made)."""

    def run(line: str) -> None:
        word, _, rest = line.strip().partition(" ")
        if word == "have":
            fake.models[rest] = 3 * GB
        elif word == "gate":
            fake.gate = threading.Event()
        elif word == "release" and fake.gate is not None:
            fake.gate.set()
        elif word == "fail":
            fake.fail_pull = rest or "disk full"
        elif word == "ok":
            fake.fail_pull = None
        elif word == "answer":  # what the model says to every chat from now
            fake.answer = json.loads(rest)
        elif word == "think":  # chats wait until "answered"
            fake.thinking = threading.Event()
        elif word == "answered" and fake.thinking is not None:
            fake.thinking.set()
            fake.thinking = None
        elif word == "state":
            every = [[m.get("content") for m in chat["messages"]] for chat in fake.chats]
            told = every[-1] if every else []
            print(json.dumps({"models": sorted(fake.models), "pulled": fake.pulled, "deleted": fake.deleted,
                              "chats": len(fake.chats), "told": json.dumps(told),
                              "all_told": json.dumps(every)}), flush=True)  # fmt: skip

    return run


if __name__ == "__main__":
    port = int(sys.argv[1])
    have = sys.argv[2:]
    fake = FakeOllama({name: 3 * GB for name in have})
    fake.serve(port)
    print("ready", flush=True)
    command = control(fake)
    for line in sys.stdin:
        command(line)
