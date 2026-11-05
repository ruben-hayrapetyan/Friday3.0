"""Glass box: how sim/people.py makes its people and sim/profiles.py lists them (HOSTED.md H73–H76)."""

from collections import Counter
from dataclasses import replace

from friday.sim import people
from friday.sim.cornell import CALENDARS, LETTERS, Meeting, address, calendar_ids
from friday.sim.people import HOW_MANY, KINDS, LOADS, PEOPLE, hours, later, minutes, person, roster, without_clashes
from friday.sim.profiles import LIVED, PROFILES, kind_of
from friday.sim.students import STUDENTS


def test_a_person_is_the_same_every_time_they_are_made() -> None:
    for key, name, kind, load, freelance, n in roster()[::7]:
        assert person(key, name, kind, load, freelance, n) == PEOPLE[key]


def test_the_roster_has_each_kind_in_its_number_with_keys_apart_from_the_cornell_students() -> None:
    assert Counter(KINDS.values()) == HOW_MANY
    assert len(PEOPLE) == sum(HOW_MANY.values()) == 43
    assert not set(PEOPLE) & set(STUDENTS)
    for kind in HOW_MANY:
        assert len({p.load for k, p in PEOPLE.items() if KINDS[k] == kind}) >= 4, kind


def test_every_load_appears_and_a_heavier_load_means_longer_work() -> None:
    assert {p.load for p in PEOPLE.values()} == set(LOADS)
    rng = people.random.Random(1)
    light = sum(hours(rng, 3, "very light") for _ in range(50))
    rng = people.random.Random(1)
    heavy = sum(hours(rng, 3, "overloaded") for _ in range(50))
    assert heavy > 3 * light


def test_lengths_are_whole_quarter_hours_and_never_zero() -> None:
    for p in PEOPLE.values():
        for w in p.work:
            assert w.hours >= 0.25 and (w.hours * 4).is_integer(), (p.key, w.title)


def test_clock_arithmetic_wraps_past_midnight() -> None:
    assert later("23:30", 60) == "00:30" and later("06:00", -510) == "21:30" and minutes("14:15") == 855


def test_a_persons_meetings_never_overlap_on_any_day() -> None:
    for p in PEOPLE.values():
        for day in LETTERS:
            spans = sorted((minutes(m.start), minutes(m.end), m.title) for m in p.meetings if day in m.days)
            for (_, end, a), (start, _, b) in zip(spans, spans[1:], strict=False):
                assert end <= start, f"{p.key} {day}: {a} overlaps {b}"


def test_a_shift_workers_meals_and_sleep_sit_outside_their_shift() -> None:
    for key, p in PEOPLE.items():
        shifts = [m for m in p.meetings if m.title.endswith(" shift")]
        if KINDS[key] != "shift" or not shifts:
            continue
        start, end = minutes(shifts[0].start), minutes(shifts[0].end)
        for meal in p.routines:
            a, b = map(minutes, meal.window or ("00:00", "00:00"))
            assert b <= start or a >= end, (key, meal.title)
        assert minutes(p.sleep[1]) <= start, key  # awake before the shift starts


def test_each_persons_mail_subjects_are_their_own() -> None:
    # the AI's answers are keyed by subject, so two letters with one subject would answer for each other
    for p in PEOPLE.values():
        subjects = [letter.subject for letter in p.letters]
        assert len(subjects) == len(set(subjects)), p.key


def test_a_persons_calendars_carry_their_own_names_each_once_and_their_address() -> None:
    worker = next(p for k, p in PEOPLE.items() if KINDS[k] == "worker")
    names = calendar_ids(worker)
    assert names["classes@g"] == "Work" and names["canvas@g"] == "Asana"
    assert names["primary@g"] == address(worker) == worker.email and worker.email.endswith("@example.com")
    assert len(set(names.values())) == len(names) == len(CALENDARS)  # each named once, so none becomes "Work 2"


def test_a_cornell_student_keeps_their_netid_address() -> None:
    maya = STUDENTS["maya"]
    assert address(maya) == "mc2289@cornell.edu" == calendar_ids(maya)["primary@g"]
    assert address(replace(maya, email="m@example.com")) == "m@example.com"


def test_profiles_are_the_cornell_students_and_the_people_with_half_lived_in_each_kind() -> None:
    assert list(PROFILES) == [*STUDENTS, *PEOPLE] and len(PROFILES) == 50
    assert 23 <= len(LIVED) <= 27
    for kind in ("student", *HOW_MANY):
        keys = {k for k in PROFILES if kind_of(k) == kind}
        assert keys & LIVED and keys - LIVED, kind


def test_a_meeting_that_clashes_with_an_earlier_one_is_left_out_and_others_kept() -> None:
    a = Meeting("Shift", "TR", "09:00", "13:00")
    clash = Meeting("Physio", "T", "10:00", "11:00")
    other_day = Meeting("Swim", "W", "10:00", "11:00")
    back_to_back = Meeting("Lunch talk", "R", "13:00", "14:00")
    assert without_clashes([a, clash, other_day, back_to_back]) == (a, other_day, back_to_back)
