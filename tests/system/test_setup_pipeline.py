"""Setup and the tour (tests/features.toml: setup), the whole pipeline: a real `fridayd serve`; the tour opens by itself
once, after setup, and never again on its own (31 Oct), which the app learns by sending `tour_offered` and reading
`setup`'s `toured` back. The flag is the app's: it doesn't touch what setup asked or your plan."""

from collections.abc import Iterator

import pytest

from tests.system.test_beat_plan_system import Friday


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("setup"))
    yield server
    server.stop()


def test_a_new_friday_hasnt_offered_the_tour_or_finished_setup(friday: Friday) -> None:
    setup = friday.q("setup")
    assert setup["toured"] is False and setup["done"] is False


def test_tour_offered_is_remembered_and_leaves_setup_and_the_plan_as_they_were(friday: Friday) -> None:
    before = friday.q("setup")
    generation = friday.q("status")["generation"]
    assert friday.c("tour_offered")["message"] == "Offered"
    after = friday.q("setup")
    assert after["toured"] is True
    assert after["done"] is False and after["answers"] == before["answers"]  # setup itself still to do
    assert friday.q("status")["generation"] == generation  # not a change to plan around


def test_offered_again_it_stays_offered(friday: Friday) -> None:
    friday.c("tour_offered")
    friday.c("tour_offered")
    assert friday.q("setup")["toured"] is True


def test_finishing_setup_after_the_tour_keeps_both(friday: Friday) -> None:
    answers = friday.q("setup")["answers"]
    friday.c("setup_save", **answers)
    setup = friday.q("setup")
    assert setup["done"] is True and setup["toured"] is True


def test_it_takes_nothing_but_says_so_when_given_something(friday: Friday) -> None:
    answer = friday.http.post("/api/c/tour_offered", json={"page": "today"})
    assert answer.status_code == 422 and [e["loc"][-1] for e in answer.json()["detail"]] == ["page"]
    assert friday.q("setup")["toured"] is True
