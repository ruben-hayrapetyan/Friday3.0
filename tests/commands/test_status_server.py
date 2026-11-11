"""The status says which server is answering (10 Nov): its process, the Mac app build that started it (none when
started by hand) and whether that app is gone, so a Mac app can stop a server left over from another build."""

import os
from pathlib import Path

import pytest

from tests.commands.helpers import new_app


def test_the_status_names_its_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = new_app(tmp_path)
    out = app.do("status")
    assert out["server_pid"] == os.getpid() and out["server_build"] is None and out["server_orphan"] is False
    monkeypatch.setenv("FRIDAY_APP_BUILD", "20261111T020000Z-123")
    assert app.do("status")["server_build"] == "20261111T020000Z-123"
