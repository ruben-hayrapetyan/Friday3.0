"""Which category an event is, from what it shares with events whose category is known (31 Oct: "the way you
classified was just based on string? this seems like a very fragile way to do this"): sure only when two judges
agree, and never its own evidence."""

from friday.core.clues import Clues, Known, clues_of, known_from


def known(
    title: str, category: str, calendar: str | None = None, place: str | None = None, by: str = "claude"
) -> Known:
    return Known(title.lower(), title, clues_of(title, calendar, place), category, by)


EVENTS = [
    known("CUAI meeting", "Club meetings"),
    known("CUAI zoom", "Club meetings"),
    known("CUAI general body", "Club meetings"),
    known("Salsa", "Social", place="Willard Straight Hall"),
    known("Salsa Halloween Social", "Social", place="Willard Straight Hall"),
    known("Poker night", "Social"),
    known("Jane Street info session", "Professional"),
    known("Citadel info session", "Professional"),
    known("Two Sigma coffee chat", "Professional"),
    known("CS 2112 Lecture", "Classes"),
    known("Math 1920 Lecture", "Classes"),
    known("Chem 2090 Lecture", "Classes"),
    known("CS 2112 Office Hours — Vivien", "Office hours"),
    known("Math 1920 Office Hours — Ana", "Office hours"),
    known("Chem 2090 Office Hours — Raj", "Office hours"),
]


def test_an_event_like_ones_you_know_is_placed_and_says_which() -> None:
    verdict = Clues(EVENTS).judge(clues_of("CUAI subteam meeting"))
    assert (verdict.category, verdict.sure) == ("Club meetings", True)
    assert verdict.like and verdict.like.startswith("CUAI")


def test_lectures_and_office_hours_of_one_course_are_told_apart_by_their_words() -> None:
    clues = Clues(EVENTS)
    assert clues.judge(clues_of("Phys 2213 Lecture")).category == "Classes"
    assert clues.judge(clues_of("Phys 2213 Office Hours — Sam")).category == "Office hours"


def test_a_new_firm_s_info_session_needs_no_list_of_firms() -> None:
    verdict = Clues(EVENTS).judge(clues_of("Optiver info session"))
    assert verdict.category == "Professional"


def test_nothing_like_it_is_no_category_and_not_sure() -> None:
    verdict = Clues(EVENTS).judge(clues_of("Dentist"))
    assert verdict.category is None and not verdict.sure
    assert Clues([]).judge(clues_of("CUAI meeting")).category is None


def test_an_event_is_never_its_own_evidence() -> None:
    # "Keratin treatment" alone in its category: hidden, nothing else says what it is
    clues = Clues([*EVENTS, known("Keratin treatment", "Self-care")])
    verdict = clues.judge(clues_of("Keratin treatment"), skip="keratin treatment")
    assert verdict.category != "Self-care"


def test_a_place_or_a_calendar_counts_less_than_the_title() -> None:
    title_words = clues_of("Poker night", location="Willard Straight Hall")
    assert {c for c in title_words if c.startswith("w:")} == {"w:poker", "w:night"}
    assert "loc:willard" in title_words and "loc:hall" in title_words


def test_who_said_the_nearest_one_s_category_comes_along() -> None:
    clues = Clues([*EVENTS[:2], known("CUAI general body", "Club meetings", by="you")])
    verdict = clues.judge(clues_of("CUAI general body meeting"))
    assert verdict.like == "CUAI general body" and verdict.like_by == "you"


def test_one_title_however_often_it_repeats_and_examples_for_claude() -> None:
    rows = [
        ("salsa", "Salsa", clues_of("Salsa", "Mac", "Willard"), "Social", "always"),
        ("salsa", "Salsa", clues_of("Salsa", "Mac", "Barton"), "Social", "always"),
        ("gym", "Gym", clues_of("Gym"), None, "claude"),
    ]
    found = known_from(rows)
    assert [k.title for k in found] == ["Salsa"]
    assert {"loc:willard", "loc:barton"} <= found[0].clues
    assert Clues(EVENTS).examples(per=2)["Social"] == ["Poker night", "Salsa"]
