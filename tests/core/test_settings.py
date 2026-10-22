import pytest

from friday.core.settings import DEFAULTS, SETTINGS_TYPES, export_toml, import_toml, validate_value


def test_every_key_has_a_default() -> None:
    assert set(DEFAULTS) == set(SETTINGS_TYPES)


def test_defaults_validate_as_their_own_values() -> None:
    from friday.core.settings import to_json

    for key, value in DEFAULTS.items():
        assert validate_value(key, to_json(key, value)) == value


def test_toml_round_trip_keeps_every_key() -> None:
    assert import_toml(export_toml(DEFAULTS)) == DEFAULTS


def test_toml_round_trip_with_personal_values() -> None:
    values = DEFAULTS | {
        "time": validate_value("time", {"timezone": "America/New_York"}),
        "sleep": validate_value(
            "sleep",
            {
                day: {"bedtime": "23:30", "wake": "07:30", "margin_min": 60}
                for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
            },
        ),
    }
    assert import_toml(export_toml(values)) == values


def test_nothing_personal_is_shipped() -> None:
    assert DEFAULTS["time"].timezone is None
    assert DEFAULTS["sleep"] is None
    assert not any(r.type == "time_preference" for r in DEFAULTS["rules"])


def test_reference_rules_match_the_design() -> None:
    names = [r.name for r in DEFAULTS["rules"]]
    assert len(names) == 21 and names[0] == "late_work" and names[-1] == "minimize_changes"


@pytest.mark.parametrize(
    ("key", "value", "field"),
    [
        ("time", {"day_start": "4am"}, "time.day_start"),
        ("time", {"timezone": "Mars/Olympus"}, "time.timezone"),
        ("time", {"horizon": 14}, "time.horizon"),
        ("engine", {"stage_policy": "fastest"}, "engine.stage_policy"),
        ("engine", {"move_weights": {"shift": 1}}, "engine.move_weights"),
        ("daily_cap", {"mon": 10}, "daily_cap"),
        ("energy_map", [[0] * 48] * 6, "energy_map"),
        ("rules", [{"type": "quota", "name": "q", "weight": -1}], "rules.0.weight"),
        ("rules", [{"type": "quota", "name": "q"}, {"type": "quota", "name": "q"}], "rules"),
        ("paces", {"Easy": {"capacity": 9}}, "paces.Easy.capacity"),
        ("sleep", {"mon": {"bedtime": "23:30", "wake": "07:30", "margin_min": 60}}, "sleep"),
        ("nonsense", {}, "nonsense"),
    ],
)
def test_invalid_values_name_their_field(key: str, value: object, field: str) -> None:
    with pytest.raises(ValueError, match=f"^{field.replace('.', '[.]')}:"):
        validate_value(key, value)


def test_import_validates_everything_before_returning() -> None:
    with pytest.raises(ValueError, match="engine.seed"):
        import_toml('[time]\ntimezone = "UTC"\n[engine]\nseed = "zero"\n')
    with pytest.raises(ValueError, match="nosuchkey"):
        import_toml("[nosuchkey]\na = 1\n")


def test_grid_spec_needs_a_timezone() -> None:
    with pytest.raises(ValueError, match="timezone"):
        DEFAULTS["time"].grid_spec()
    spec = validate_value("time", {"timezone": "UTC", "day_start": "05:00"}).grid_spec()
    assert spec.day_start == 300 and spec.fine_slot_units == 1 and spec.coarse_slot_units == 2


def test_notes_are_short_lines_in_your_own_words() -> None:
    assert validate_value("notes", ["PHYS labs are done in the lab session"]) == (
        "PHYS labs are done in the lab session",
    )
    for bad in (["x" * 301], [" "], ["n"] * 41):
        with pytest.raises(ValueError, match="notes"):
            validate_value("notes", bad)


def test_notes_reach_the_reader_only_when_there_are_some() -> None:
    from datetime import date

    from friday.ingest.extract import system

    told = system(date(2026, 10, 21), "America/New_York", [], ["Assignment"], ["Quizzes are in class"])
    assert "- Quizzes are in class" in told
    assert "told Friday" not in system(date(2026, 10, 21), "America/New_York", [], ["Assignment"])
