"""The write lock, timed (12 Nov: clicks took seconds while something else held the database, and the log couldn't
say what): a long wait for it, or a long hold of it, is said, naming who."""

import logging
import time
from pathlib import Path

import pytest

from friday.core import db


def test_a_wait_behind_another_write_is_kept_and_a_long_one_said(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db, "SLOW_MS", 50)
    one, two = db.connect(tmp_path / "f.db"), db.connect(tmp_path / "f.db")
    one.execute("BEGIN IMMEDIATE")
    import threading

    threading.Timer(0.2, lambda: one.execute("COMMIT")).start()
    with caplog.at_level(logging.WARNING, logger="friday.db"):
        db.begin_write(two, "a click")
    two.execute("COMMIT")
    assert db.waited(two) >= 150
    assert db.waited(two) == 0  # read once
    assert "a click waited" in caplog.text


def test_a_long_hold_is_said(caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "SLOW_MS", 10)
    with caplog.at_level(logging.WARNING, logger="friday.db"):
        db.held("saving a plan", time.perf_counter() - 0.05)
        db.held("a quick one", time.perf_counter())
    assert "saving a plan held the database for" in caplog.text
    assert "a quick one" not in caplog.text
