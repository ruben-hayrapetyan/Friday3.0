"""One course for a stretch of work (C64, 8 Nov: "i would wanna do math for the entire time not 3 different things"):
with nothing late either way, a week's coursework goes straight on within a course, not from one to another. Black
box through the commands and the planner; the rule off is the same week as before it."""

from pathlib import Path

import pytest

from friday.planner.service import replan
from friday.planner.store import load_settings
from tests.commands.helpers import App, new_app

WORK = {"MATH 1920 HW10": ("math", 90), "Math read 17.3": ("math", 60), "CHEM 2090 PS9": ("chem", 90),
        "CHEM 2090 PS11": ("chem", 60), "PSYCH 1130 essay": ("psych", 90), "Psych reading": ("psych", 60)}  # fmt: skip


def switches(app: App, on: bool) -> int:
    rules = [
        r.model_dump() | ({"enabled": on} if r.name == "same_course" else {}) for r in load_settings(app.conn)["rules"]
    ]
    app.do("settings_set", key="rules", value=rules)
    titles = {}
    for title, (_, minutes) in WORK.items():
        made = app.do("add", title=title, preset="Assignment", due="2026-10-23T23:00", duration_min=minutes)
        titles[made["item"]["id"]] = title
    replan(app.conn, app.now_utc, warm=False)
    blocks = sorted(
        (b["start"], b["end"], titles[b["item_id"]]) for b in app.do("plan")["blocks"] if b["item_id"] in titles
    )
    assert {title for *_, title in blocks} == set(WORK)  # all of it planned
    return sum(a[1] == b[0] and WORK[a[2]][0] != WORK[b[2]][0] for a, b in zip(blocks, blocks[1:], strict=False))


@pytest.mark.parametrize("on", [True, False])
def test_a_stretch_stays_on_one_course(tmp_path: Path, on: bool) -> None:
    found = switches(new_app(tmp_path), on)
    assert found == 0 if on else found > 0
