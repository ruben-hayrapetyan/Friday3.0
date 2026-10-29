"""Friday's AI, the whole system at once (28 Oct: "glass box/black box/full system tests are necessary"): a real
`fridayd serve` in a folder of its own, a stand-in Ollama as a real server on this Mac (tests/fake_ollama.py: models
"downloaded" over a streamed HTTP answer, removed, asked), and only HTTP between them, as the app sends it. A new
user: no setup answers, no keys. Nothing reaches the internet, nothing real is downloaded."""

import json
import os
import socket
import stat
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Ollama:
    """The stand-in Ollama, as its own process, told what to do on stdin."""

    def __init__(self, have: list[str]) -> None:
        self.port = free_port()
        self.process = subprocess.Popen(
            [sys.executable, "-m", "tests.fake_ollama", str(self.port), *have],
            cwd=REPO, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        )  # fmt: skip
        assert self.process.stdout is not None and self.process.stdout.readline().strip() == "ready"

    def tell(self, line: str) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()

    def state(self) -> dict[str, Any]:
        self.tell("state")
        assert self.process.stdout is not None
        return json.loads(self.process.stdout.readline())

    def stop(self) -> None:
        self.process.terminate()
        self.process.wait(10)


class Friday:
    """`fridayd serve` for a new user, its data and config in `folder`, its Ollama the stand-in."""

    def __init__(self, folder: Path, ollama: Ollama) -> None:
        self.port, self.folder = free_port(), folder
        env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY") and k not in ("FRIDAY_AI_KEY",)}
        env |= {"FRIDAY_DATA_DIR": str(folder / "data"), "FRIDAY_CONFIG": str(folder / "config" / "friday.toml"),
                "OLLAMA_HOST": f"127.0.0.1:{ollama.port}", "FRIDAY_CLAUDE": "none"}  # fmt: skip
        (folder / "config").mkdir(parents=True)
        fridayd = [sys.executable, "-m", "friday.server.main", "--data-dir", str(folder / "data")]
        subprocess.run([*fridayd, "init", "--timezone", "America/New_York"], cwd=REPO, env=env, check=True,
                       capture_output=True)  # fmt: skip
        self.log = (folder / "server.out").open("w")
        self.process = subprocess.Popen([*fridayd, "serve", "--port", str(self.port)], cwd=REPO, env=env,
                                        stdout=self.log, stderr=subprocess.STDOUT)  # fmt: skip
        self.http = httpx.Client(base_url=f"http://127.0.0.1:{self.port}", timeout=30)
        for _ in range(240):
            try:
                if self.http.get("/api/q/status").status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        raise RuntimeError("fridayd didn't start: " + (folder / "server.out").read_text()[-2000:])

    def q(self, verb: str, /, **params: Any) -> Any:
        answer = self.http.get(f"/api/q/{verb}", params=params)
        assert answer.status_code == 200, answer.text
        return answer.json()

    def c(self, verb: str, /, ok: bool = True, **body: Any) -> Any:
        answer = self.http.post(f"/api/c/{verb}", json=body)
        if ok:
            assert answer.status_code == 200, answer.text
            return answer.json()["result"]
        return answer

    def downloaded(self, timeout: float = 30) -> dict[str, Any]:
        """Until the download under way has ended: what it ended as."""
        end = time.time() + timeout
        while time.time() < end:
            download = self.q("local_models")["download"]
            if download and download["status"] != "downloading":
                return download
            time.sleep(0.2)
        raise TimeoutError("the download didn't end")

    def ai(self) -> dict[str, Any]:
        return self.q("settings")["llm"]

    def stop(self) -> None:
        self.process.terminate()
        self.process.wait(15)
        self.log.close()


@pytest.fixture(scope="module")
def system(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Friday, Ollama]]:
    ollama = Ollama(["llama3.2:3b"])  # llama3.2 was on this Mac before Friday
    friday = Friday(tmp_path_factory.mktemp("new-user"), ollama)
    yield friday, ollama
    friday.stop()
    ollama.stop()


def test_1_a_new_user_starts_with_claude_and_no_ai_ready(system: tuple[Friday, Ollama]) -> None:
    friday, _ = system
    state = friday.q("inbox")["llm"]
    assert (state["provider"], state["ready"]) == ("claude", False)  # no claude command, no key: said, not hidden
    assert "Anthropic API key" in state["why"]
    out = friday.q("local_models")
    assert out["running"] and "downloaded here" in out["warning"] and "slow" in out["warning"]
    assert next(m for m in out["catalog"] if m["name"] == "llama3.2:3b")["here"] is True


def test_2_a_model_already_here_is_used_at_once_and_stays_yours(system: tuple[Friday, Ollama]) -> None:
    friday, ollama = system
    assert "now" in friday.c("local_model_use", name="llama3.2:3b")["message"]
    assert friday.ai()["provider"] == "local" and friday.ai()["model"] == "llama3.2:3b"
    assert ollama.state()["pulled"] == []
    assert friday.q("inbox")["llm"]["ready"] is True


def test_3_a_new_model_downloads_then_friday_switches_and_keeps_yours(system: tuple[Friday, Ollama]) -> None:
    friday, ollama = system
    assert friday.c("local_model_use", name="qwen3:8b")["message"].startswith("Downloading qwen3:8b (about 5.2 GB)")
    assert friday.downloaded()["status"] == "done"
    assert friday.ai()["model"] == "qwen3:8b"
    state = ollama.state()
    assert state["pulled"] == ["qwen3:8b"] and state["deleted"] == [] and "llama3.2:3b" in state["models"]
    assert next(m for m in friday.q("local_models")["catalog"] if m["name"] == "qwen3:8b")["friday"] is True


def test_4_friday_reads_with_the_model_on_this_mac(system: tuple[Friday, Ollama]) -> None:
    friday, ollama = system
    before = ollama.state()["chats"]
    out = friday.c("ask_claude", text="i want mornings free", purpose="rule")
    assert out["actions"] == [] and ollama.state()["chats"] == before + 1


def test_5_while_a_model_downloads_the_one_you_had_stays_then_friday_s_old_one_goes(
    system: tuple[Friday, Ollama],
) -> None:
    friday, ollama = system
    ollama.tell("gate")
    friday.c("local_model_use", name="mistral:7b")
    time.sleep(0.5)
    download = friday.q("local_models")["download"]
    assert download["name"] == "mistral:7b" and download["status"] == "downloading"
    assert friday.ai()["model"] == "qwen3:8b" and "qwen3:8b" in ollama.state()["models"]
    second = friday.c("local_model_use", ok=False, name="gemma3:4b")
    assert second.status_code == 422 and "still downloading" in second.json()["message"]
    ollama.tell("release")
    assert friday.downloaded()["status"] == "done"
    state = ollama.state()
    assert friday.ai()["model"] == "mistral:7b" and state["deleted"] == ["qwen3:8b"]
    assert "llama3.2:3b" in state["models"]  # yours, never touched


def test_6_a_failed_download_keeps_the_ai_you_had(system: tuple[Friday, Ollama]) -> None:
    friday, ollama = system
    ollama.tell("fail no space left on device")
    friday.c("local_model_use", name="deepseek-r1:8b")
    ended = friday.downloaded()
    assert (ended["status"], ended["error"]) == ("failed", "no space left on device")
    assert friday.ai()["model"] == "mistral:7b" and "mistral:7b" in ollama.state()["models"]
    ollama.tell("ok")


def test_7_a_stopped_download_keeps_the_ai_you_had(system: tuple[Friday, Ollama]) -> None:
    friday, ollama = system
    ollama.tell("gate")
    friday.c("local_model_use", name="phi4-mini")
    time.sleep(0.3)
    assert friday.c("local_model_cancel")["message"] == "Stopped the download"
    ollama.tell("release")
    assert friday.downloaded()["status"] in ("cancelled", "done")
    assert friday.ai()["model"] in ("mistral:7b", "phi4-mini:latest")


def test_8_going_back_to_your_own_model_removes_friday_s(system: tuple[Friday, Ollama]) -> None:
    friday, ollama = system
    current = friday.ai()["model"]
    friday.c("local_model_use", name="llama3.2:3b")
    state = ollama.state()
    assert friday.ai()["model"] == "llama3.2:3b" and current in state["deleted"]
    assert "llama3.2:3b" in state["models"]


def test_9_another_service_with_a_key_lists_its_models_and_answers(system: tuple[Friday, Ollama]) -> None:
    friday, ollama = system
    address = f"http://127.0.0.1:{ollama.port}/v1"  # the stand-in speaks OpenAI's API too
    friday.c("ai_key_set", provider="compatible", key="sk-system-test")
    secrets = friday.folder / "config" / "secrets.toml"
    assert stat.S_IMODE(secrets.stat().st_mode) == 0o600 and "sk-system-test" in secrets.read_text()
    friday.c("settings_set", key="llm", value={"provider": "compatible", "base_url": address, "model": "llama3.2:3b"})
    listed = friday.q("ai_models", provider="compatible", base_url=address)
    assert "llama3.2:3b" in listed["models"] and listed["error"] is None
    assert friday.c("ask_claude", text="move nothing")["reply"] == ""
    assert friday.q("inbox")["llm"]["ready"] is True
    assert "sk-system-test" not in json.dumps(friday.q("inbox")) and "sk-system-test" not in json.dumps(
        friday.q("settings")
    )
    assert "llama3.2:3b" in ollama.state()["models"]  # leaving open models kept yours


def test_10_a_page_from_another_site_changes_nothing(system: tuple[Friday, Ollama]) -> None:
    friday, _ = system
    answer = friday.http.post("/api/c/settings_set", json={"key": "llm", "value": {"base_url": "https://evil.example/v1"}},
                              headers={"origin": "https://evil.example"})  # fmt: skip
    assert answer.status_code == 403 and friday.ai()["base_url"] != "https://evil.example/v1"


def test_11_the_server_stops_quickly_with_the_app_s_live_stream_open(system: tuple[Friday, Ollama]) -> None:
    friday, _ = system
    stream = httpx.Client(base_url=f"http://127.0.0.1:{friday.port}", timeout=None)
    with stream.stream("GET", "/events"):
        start = time.time()
        friday.process.terminate()
        friday.process.wait(15)
    assert time.time() - start < 2  # was three seconds before 28 Oct
