from __future__ import annotations

import pytest

from fr.core.settings import Settings

MON = 0  # epoch date 0 is a Monday


def at(date: int, hhmm: str) -> int:
    h, m = hhmm.split(":")
    return date * 1440 + int(h) * 60 + int(m)


@pytest.fixture
def settings() -> Settings:
    return Settings()
