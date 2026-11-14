"""Where what Friday learned disagrees with what you said, a decision in the Inbox with the side Friday would change
(29 Oct: "make sure that there is guards against any of friday's learned behaviors and the rules contradicting (and
whether the rules need to be updated or the behaviors)"). Weekdays 23:30–07:30 (the helpers' sleep)."""

import json
from pathlib import Path

import pytest

from friday.commands import conflicts
from friday.core.items import FieldError
from friday.learn.meals import Learned
from friday.planner.snapshot import learned as learned_weights
from friday.planner.store import load_settings
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def learned(app: App) -> list[dict]:
    return [d for d in app.do("status")["decisions"] if d["kind"] == "learned"]


def weigh(app: App, **theta: float) -> None:
    """A learned profile with these multipliers, as nightly learning saves one."""
    app.do("learn_reset", module="weights")
    row = app.conn.execute("SELECT version, theta FROM learned_profile ORDER BY version DESC LIMIT 1").fetchone()
    now = json.loads(row["theta"]) | {k.replace("__", ":").replace("_", "-"): v for k, v in theta.items()}
    app.conn.execute("UPDATE learned_profile SET theta = ? WHERE version = ?", [json.dumps(now), row["version"]])


def answer(app: App, decision: dict, option: str) -> str:
    return app.do("conflict_resolve", key=decision["key"].removeprefix("learned:"), option=option)["message"]


class TestLearnedWeights:
    def rule(self, app: App) -> str:
        app.do("rule_add", text="keep friday evenings free", strength="Strongly")
        return next(r["name"] for r in app.do("rules") if r["name"].startswith("you:"))

    def test_a_rule_you_wrote_learned_down_is_asked_about_and_held_at_half_meanwhile(self, app: App) -> None:
        name = self.rule(app)
        weigh(app, **{name.replace(":", "__").replace("-", "_"): 0.033})
        (d,) = learned(app)
        assert d["title"].startswith("Your moves go against") and d["update"] == "learned"
        assert [(o["id"], o["recommended"]) for o in d["options"]] == [
            ("keep", True),
            ("free", False),
            ("prefer", False),
        ]
        settings = load_settings(app.conn, 1)
        assert learned_weights(app.conn, app.now_utc, settings, 1)["multipliers"][name] == 0.5

    def test_kept_as_written_it_is_weighed_as_set_and_not_asked_again(self, app: App) -> None:
        name = self.rule(app)
        weigh(app, **{name.replace(":", "__").replace("-", "_"): 0.033})
        assert answer(app, learned(app)[0], "keep") == "Kept as written"
        assert learned(app) == []
        settings = load_settings(app.conn, 1)
        assert learned_weights(app.conn, app.now_utc, settings, 1)["multipliers"][name] == 1.0

    def test_let_go_it_is_weighed_as_learned(self, app: App) -> None:
        name = self.rule(app)
        weigh(app, **{name.replace(":", "__").replace("-", "_"): 0.033})
        answer(app, learned(app)[0], "free")
        settings = load_settings(app.conn, 1)
        assert learned_weights(app.conn, app.now_utc, settings, 1)["multipliers"][name] == 0.033

    def test_made_a_preference_it_is_one(self, app: App) -> None:
        name = self.rule(app)
        weigh(app, **{name.replace(":", "__").replace("-", "_"): 0.033})
        answer(app, learned(app)[0], "prefer")
        assert next(r for r in app.do("rules") if r["name"] == name)["strength"] == "Prefer"

    def test_friday_s_own_rules_learn_freely_and_ask_nothing(self, app: App) -> None:
        weigh(app, chunk_cost=0.033)
        assert learned(app) == []


class TestSleep:
    def test_sleep_times_short_of_your_rule_are_asked_about_and_bedtime_is_friday_s_answer(self, app: App) -> None:
        app.do("rule_add", text="at least 9 hours of sleep", strength="Strongly")  # 23:30–07:30 is 8
        found = {d["detail"].split(":")[0]: d for d in learned(app)}
        assert sorted(found) == ["Mondays, Tuesdays, Wednesdays and Thursdays", "Saturdays", "Sundays"]
        weeknights = found["Mondays, Tuesdays, Wednesdays and Thursdays"]
        assert "leave 8 h 00 m asleep" in weeknights["title"] and weeknights["update"] == "learned"
        assert [o["label"] for o in weeknights["options"]] == ["Go to bed at 10:30pm", "Lower the rule to 8 h"]
        assert "leave 7 h 00 m asleep" in found["Sundays"]["title"]  # the weekend's 12:30am before Monday's 7:30am
        answer(app, weeknights, "bedtime")
        assert app.do("settings")["sleep"]["mon"]["bedtime"] == "22:30"
        assert weeknights["key"] not in [d["key"] for d in learned(app)]  # the others still to decide

    def test_or_the_rule_comes_down(self, app: App) -> None:
        app.do("rule_add", text="at least 9 hours of sleep", strength="Strongly")
        weeknights = next(d for d in learned(app) if d["detail"].startswith("Mondays"))
        answer(app, weeknights, "rule")
        rule = next(r for r in app.do("settings")["rules"] if r["type"] == "sleep_min")
        assert rule["params"]["hours"] == 8.0 and app.do("settings")["sleep"]["mon"]["bedtime"] == "23:30"
        (sunday,) = learned(app)  # 8 h on other nights meets it now; Sunday's 7 still doesn't
        assert "leave 7 h 00 m asleep; your rule asks for 8 h" in sunday["title"]

    def test_short_nights_counts_winding_down_before_the_hours(self) -> None:
        sleep = {d: {"bedtime": "00:45", "wake": "08:00"} for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
        rule = type("R", (), {"type": "sleep_min", "enabled": True, "params": {"hours": 7.0}, "name": "you:seven"})()
        assert conflicts.short_nights(sleep, [rule], {}) == {}  # 7 h 15 m in bed
        found = conflicts.short_nights(sleep, [rule], {"mon": 30})
        assert list(found.values()) == [["mon"]]  # 6 h 45 m asleep after half an hour winding down


class TestWindDown:
    def test_a_wind_down_far_from_when_you_wind_down_is_asked_and_the_rule_is_friday_s_answer(
        self, app: App, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            conflicts, "nights_learned", lambda ctx: (dict.fromkeys(("sun", "mon", "tue", "wed", "thu"), 15), {})
        )
        (d,) = learned(app)  # winds down from 11:15pm; the rule starts at 10pm
        assert d["title"] == "“Wind down before bed” starts at 10pm, but you wind down from about 11:15pm"
        assert d["update"] == "rule" and d["options"][0]["recommended"]
        answer(app, d, "rule")
        rule = next(r for r in app.do("settings")["rules"] if r["type"] == "late_night")
        assert rule["params"]["gradient_start"] == "23:15" and learned(app) == []

    def test_kept_it_stays_quiet_until_your_bedtime_moves(self, app: App, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            conflicts, "nights_learned", lambda ctx: (dict.fromkeys(("sun", "mon", "tue", "wed", "thu"), 15), {})
        )
        answer(app, learned(app)[0], "keep")
        assert learned(app) == []
        app.do(
            "settings_set", key="sleep", value={d: {"bedtime": "00:30"} for d in ("sun", "mon", "tue", "wed", "thu")}
        )
        assert learned(app)[0]["title"].endswith("from about 12:15am")  # something new to decide


class TestMeals:
    def test_a_meal_you_mostly_skip_against_a_never_skipped_rule(
        self, app: App, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        app.do("settings_set", key="meal_tracking", value={"on": True})
        rules = app.do("settings")["rules"] + [{
            "type": "elastic_shortfall", "name": "you:lunch-and-dinner-are-never-skipped", "weight": 1.0,
            "stage": "deadlines", "scope": {"preset": "Routine", "title_regex": ["(?i)\\b(lunch|dinner)s?\\b"]},
            "reason": "Lunch and dinner are never skipped for work", "params": {"steep": 10000.0, "gentle": 0.0},
        }]  # fmt: skip
        app.do("settings_set", key="rules", value=rules)
        lunch = Learned("lunch", "weekdays", 8, "12:30", 30, None, 0.75)
        import friday.commands.eating as eating  # noqa: PLC0415

        monkeypatch.setattr(eating, "learned", lambda ctx: [lunch])
        (d,) = learned(app)
        assert d["title"] == "You skip lunch on most weekdays, but your rule says it's never skipped"
        assert [o["id"] for o in d["options"]] == ["keep", "off"]
        answer(app, d, "off")
        rule = next(r for r in app.do("settings")["rules"] if r["name"] == "you:lunch-and-dinner-are-never-skipped")
        assert rule["enabled"] is False


def test_an_answer_to_something_settled_is_refused(app: App) -> None:
    with pytest.raises(FieldError, match="settled"):
        app.do("conflict_resolve", key="wind_down", option="rule")


def test_a_rule_learned_far_up_is_said_in_times_and_counts_double_meanwhile(app: App) -> None:
    app.do("rule_add", text="keep friday evenings free", strength="Strongly")
    name = next(r["name"] for r in app.do("rules") if r["name"].startswith("you:"))
    weigh(app, **{name.replace(":", "__").replace("-", "_"): 3.2})
    (d,) = learned(app)
    assert d["title"].startswith("Your moves go far beyond") and "about 3.2 times what you set" in d["detail"]
    assert [o["id"] for o in d["options"]] == ["keep", "free"]  # making it a preference only brings one down
    with pytest.raises(FieldError, match="no answer 'prefer' to that"):
        answer(app, d, "prefer")


def test_with_sleep_tracking_on_and_no_nights_yet_nothing_is_asked_about_winding_down(app: App) -> None:
    app.do("settings_set", key="sleep_tracking", value={"on": True})
    assert learned(app) == []


def test_meals_are_asked_about_only_when_mostly_skipped_and_kept_by_a_rule_of_yours(
    app: App, monkeypatch: pytest.MonkeyPatch
) -> None:
    import friday.commands.eating as eating  # noqa: PLC0415

    app.do("settings_set", key="meal_tracking", value={"on": True})
    monkeypatch.setattr(eating, "learned", lambda ctx: [Learned("lunch", "weekdays", 8, "12:30", 30, None, 0.75)])
    assert learned(app) == []  # no rule of yours keeps a meal
    rules = app.do("settings")["rules"] + [{
        "type": "elastic_shortfall", "name": "you:lunch-is-never-skipped", "weight": 1.0,
        "stage": "deadlines", "scope": {"preset": "Routine", "title_regex": ["(?i)\\blunch\\b"]},
        "reason": "Lunch is never skipped", "params": {"steep": 10000.0, "gentle": 0.0},
    }]  # fmt: skip
    app.do("settings_set", key="rules", value=rules)
    monkeypatch.setattr(
        eating,
        "learned",
        lambda ctx: [
            Learned("lunch", "weekdays", 8, "12:30", 30, None, 0.75),
            Learned("lunch", "weekends", 4, "13:00", 30, None, 0.25),  # mostly had
            Learned("breakfast", "weekdays", 8, "08:00", 15, None, 0.9),  # no rule keeps it
        ],
    )
    (d,) = learned(app)
    assert d["title"] == "You skip lunch on most weekdays, but your rule says it's never skipped"
    assert answer(app, d, "keep") == "Kept the rule"
    assert next(r for r in app.do("settings")["rules"] if r["name"] == "you:lunch-is-never-skipped")["enabled"]
