"""Spreading said as a rule, the whole system (14 Nov: tasks aren't marked spread; a rule names the work): a real
`fridayd serve` on the real clock reads "spread my essays over several days", and the essay's plan is spread over
days while the problem set, kept together by its own rule, takes one day."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("spread_rule"))
    try:  # stopped even when setting it up fails, so no server is left running
        server.c("settings_set", key="sleep", value=SLEEP)
        due = (datetime.now(ZoneInfo(TZ)) + timedelta(days=5)).strftime("%Y-%m-%dT17:00")
        server.c("add", title="History essay", duration_min=360, due=due, preset="Assignment")
        server.c("add", title="Physics problem set", duration_min=240, due=due, preset="Assignment")
        server.c("rule_add", text="spread my essays over several days", strength="Strongly")
        server.c("rule_add", text="keep problem sets on as few days as possible", strength="Strongly")
        yield server
    finally:
        server.stop()


def days_of(friday: Friday, title: str) -> set[str]:
    return {b["start"][:10] for b in friday.q("plan")["blocks"] if b["title"] == title}


def test_the_rules_read_and_show_as_said(friday: Friday) -> None:
    said = {r["sentence"]: r for r in friday.q("rules")}
    assert said["Spread essays over several days"]["type"] == "spread"
    assert said["Keep problem sets on as few days as possible"]["type"] == "cluster"
    assert not {"spread", "cluster"} & {r["name"] for r in friday.q("rules")}  # the built-in ones are gone


def test_the_essay_is_spread_and_the_problem_set_kept_together(friday: Friday) -> None:
    assert friday.until(lambda: len(days_of(friday, "History essay")) >= 3)
    assert len(days_of(friday, "Physics problem set")) == 1
