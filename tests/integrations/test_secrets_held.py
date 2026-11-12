"""secrets.toml changed by two at once (audit, 12 Nov): the sync's token renewals, the Sender and a save in Settings
each read the file, changed their part and wrote it whole, so the later write lost the earlier one's change."""

import threading
import time
from pathlib import Path

import pytest

from friday.integrations import sync


def test_tokens_kept_at_the_same_moment_are_all_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRIDAY_CONFIG", str(tmp_path / "friday.toml"))
    read = sync.secrets

    def slow_read() -> dict:
        found = read()
        time.sleep(0.02)  # the moment another writer used to slip into
        return found

    monkeypatch.setattr(sync, "secrets", slow_read)
    threads = [threading.Thread(target=sync.keep_token, args=(n, "todoist", f"token-{n}")) for n in range(1, 9)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    monkeypatch.setattr(sync, "secrets", read)
    assert [sync.token_of(n) for n in range(1, 9)] == [f"token-{n}" for n in range(1, 9)]
    sync.forget_token(3)
    assert sync.token_of(3) == "" and sync.token_of(4) == "token-4"
