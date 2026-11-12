import pytest

from friday.core.items import FieldError, Item, apply_preset, validate, with_defaults, would_create_cycle
from friday.core.presets import DEFAULT_PRESETS

DUE = "2026-10-20T21:59Z"
RELEASE = "2026-10-19T08:00Z"


def preset(name: str, **given: object) -> Item:
    fields = apply_preset(given, DEFAULT_PRESETS[name].model_dump(exclude_none=True))
    return with_defaults(Item(preset=name, **fields))


@pytest.mark.parametrize(
    "item",
    [
        preset("Assignment", title="PS5", due_utc=DUE),
        preset("Class", title="CS 1110", start_utc=RELEASE, end_utc="2026-10-19T09:15Z"),
        preset("Routine", title="Lunch", release_utc=RELEASE, due_utc=DUE),
        preset("Goal", title="Run", release_utc=RELEASE, due_utc=DUE),
        preset("Side project", title="Book"),
        preset("Maybe", title="Store run", release_utc=RELEASE, due_utc=DUE),
        preset("Chore", title="Laundry", duration_units=1),
    ],
)
def test_presets_make_valid_items(item: Item) -> None:
    validate(item)


@pytest.mark.parametrize(
    ("item", "field"),
    [
        (Item("x", when="fixed", start_utc=DUE, end_utc=RELEASE), "end_utc"),
        (Item("x", when="fixed"), "start_utc"),
        (Item("x", firmness="hard", duration_units=4), "due_utc"),
        (Item("x", amount="target", target_units=4, due_utc=DUE), "release_utc"),
        (Item("x", amount="open", due_utc=DUE), "due_utc"),
        (Item("x", amount="open", firmness="soft"), "firmness"),
        (Item("x", amount="open", shape="one_sitting"), "shape"),
        (Item("x", amount="elastic", min_units=3, ideal_units=2, max_units=4), "ideal_units"),
        (Item("x", amount="elastic", min_units=3), "min_units"),
        (Item("x", duration_units=4, min_chunk_units=6), "min_chunk_units"),
        (Item("x", shape="one_sitting", duration_units=4, max_chunk_units=4), "max_chunk_units"),
        (Item("x", when="anytime", certainty="tentative"), "certainty"),
        (Item("x", importance=6), "importance"),
        (Item(" "), "title"),
        (Item("x", release_utc=DUE, due_utc=RELEASE), "due_utc"),
        (Item("x", chunk_cost=1.5), "chunk_cost"),
        (Item("x", neglect_carry=-0.1), "neglect_carry"),
        (Item("x", duration_units=-1), "duration_units"),
        (Item("x", amount="target", release_utc=RELEASE, due_utc=DUE), "target_units"),
        (Item("x", duration_units=8, min_chunk_units=4, max_chunk_units=2), "max_chunk_units"),
    ],
)
def test_validation_names_the_field(item: Item, field: str) -> None:
    with pytest.raises(FieldError) as error:
        validate(item)
    assert error.value.field == field


def test_target_cap_defaults_to_one_and_a_half_targets() -> None:
    assert preset("Goal", title="Run", target_units=5, release_utc=RELEASE, due_utc=DUE).cap_units == 8


def test_open_items_get_a_daily_ceiling() -> None:
    assert with_defaults(Item("Book", amount="open", when="anytime")).daily_ceiling_units == 4


def test_given_fields_win_over_the_preset() -> None:
    item = preset("Assignment", title="PS5", due_utc=DUE, firmness="soft", duration_units=3)
    assert (item.firmness, item.duration_units, item.energy) == ("soft", 3, "deep")


def test_a_cycle_is_detected() -> None:
    edges = {1: [2], 2: [3]}
    assert would_create_cycle(edges, 3, 1)
    assert not would_create_cycle(edges, 1, 3)
