"""Learning's answers at the edges (commands/learning.py): a comparison, a proposal or a profile version that isn't
there says so; a kind order you turn down isn't offered again; and the review offers learned lengths that would do
better than your estimates."""

from pathlib import Path

import pytest

from friday.commands.learned import learn_nightly
from friday.core.items import FieldError
from friday.planner.store import kv_get, kv_set
from tests.commands.helpers import App, new_app
from tests.commands.test_learned import finish


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def test_answers_to_what_wasnt_asked_say_so(app: App) -> None:
    with pytest.raises(FieldError, match="no comparison 5"):
        app.do("compare_answer", id=5, answer="a")
    with pytest.raises(FieldError, match="nothing was proposed"):
        app.do("proposal_answer", kind="rule", name="fri_sat:late:any", yes=True)
    with pytest.raises(FieldError, match="no suggested profile version 3"):
        app.do("learn_apply", version=3)


def test_a_proposal_friday_never_made_is_refused(app: App) -> None:
    app.conn.execute(
        "INSERT INTO learned_profile (version, created_utc, theta, proposals, wall_decisions, evidence, status) "
        "VALUES (1, 'x', '{}', '{\"pending\": null}', '{\"pending\": null, \"decided\": {}}', '{}', 'suggested')"
    )
    with pytest.raises(FieldError, match="no proposal made_up"):
        app.do("proposal_answer", kind="rule", name="made_up", yes=True)


def test_a_kind_order_turned_down_is_kept_as_refused(app: App) -> None:
    before = app.do("settings")["kind_order"]
    out = app.do("learn_order", first="Reading", then="Assignment", use=False)
    assert out["message"] == "Friday won't suggest Reading before Assignment again"
    assert kv_get(app.conn, "order_refused") == [["Reading", "Assignment"]]
    assert app.do("settings")["kind_order"] == before
    app.do("learn_order", first="Chore", then="Errand", use=False)
    assert kv_get(app.conn, "order_refused") == [["Reading", "Assignment"], ["Chore", "Errand"]]


def test_the_review_offers_learned_lengths_that_would_do_better(tmp_path: Path) -> None:
    app = new_app(tmp_path, now="2026-10-01T09:00", horizon_days=3)
    app.do("area_add", name="CS")
    for n in range(8):
        finish(app, f"problem set {n + 1}", 180, n + 1)
    app.at("2026-10-12T09:00")
    learn_nightly(app.conn, app.now_utc)
    scored = {"better": True, "error": 0.12, "error_before": 0.4}  # as the held-out check scores them
    kv_set(app.conn, "learned_durations", kv_get(app.conn, "learned_durations") | scored)
    (said,) = [line for line in app.do("learning")["digest"] if line.startswith("Learned lengths")]
    assert said == "Learned lengths are typically 12% off, against 40% now. Use them?"
