"""Settings → Repeating's list (8 Nov): an event made to repeat is listed as an event, not flexible work (its template
keeps the kind as `when`, which the list read as `when_kind` and missed); each row names its next open time, which
the row opens in its editor, and how it repeats, for the editor's Repeats."""

from pathlib import Path

from tests.commands.helpers import new_app


def test_an_event_made_to_repeat_is_an_event_with_its_next_time_and_rule(tmp_path: Path) -> None:
    app = new_app(tmp_path, now="2026-11-02T09:00")
    app.do("add", title="Gym with Sam", when="fixed", start="2026-11-09T17:00", end="2026-11-09T18:00", every="mon")
    app.do("series_add", title="Laundry", every="mon", duration_min=60)
    rows = {r["title"]: r for r in app.do("series_list")}
    gym, laundry = rows["Gym with Sam"], rows["Laundry"]
    assert gym["fixed"] is True and laundry["fixed"] is False
    first = min((i for i in app.table("items") if i["series_id"] == gym["id"]), key=lambda i: i["start_utc"])
    assert gym["next_id"] == first["id"]
    assert "FREQ=WEEKLY" in gym["rule"] and "BYDAY=MO" in gym["rule"]
