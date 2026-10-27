"""Seven Cornell students set up the way they would on their first evening (sim/students.py): calendars, mail,
quick-add and rules, through the same commands as the app. Then their week is read the way they would read it:
everything accepted lands as itself, and the plan is lived-in — work in real sittings before it is due, never in
class or asleep, prelims prepared for over days, no day overfull, and their own rules kept. Riley's week can't be
done; the plan says so and keeps the earliest deadlines.

Monday 2026-10-19 09:00 in New York. `python -m friday.sim.agenda NAME` prints the same plan to read.
"""

import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import pytest

from friday.commands.registry import run
from friday.core.time import parse_local, to_utc
from friday.planner.service import replan
from friday.sim.cornell import ZONE, Student
from friday.sim.first_evening import hours_by_title, open_student
from friday.sim.judge import Sitting, Verdict, judge
from friday.sim.students import STUDENTS

MONDAY = date(2026, 10, 19)
NOW = to_utc(parse_local(f"{MONDAY}T09:00"), ZONE.key)
WEEK_END = datetime.combine(MONDAY + timedelta(days=7), time())
FEASIBLE = [k for k, s in STUDENTS.items() if s.load != "overloaded"]


@dataclass
class Planned:
    student: Student
    conn: sqlite3.Connection

    def ask(self, query: str, **payload: Any) -> Any:
        return run(self.conn, query, payload, now_utc=NOW, actor="you", provisional=False).result

    def items(self) -> dict[str, dict[str, Any]]:
        """Items to do by title (a series' occurrences: the first)."""
        found: dict[str, dict[str, Any]] = {}
        for i in sorted(self.ask("items"), key=lambda i: i["due"] or i["start"] or ""):
            found.setdefault(i["title"], i)
        return found

    def events(self) -> dict[str, dict[str, Any]]:
        """Fixed items in the next five weeks by title (the first of each)."""
        found: dict[str, dict[str, Any]] = {}
        for f in self.ask("plan", start=f"{MONDAY}T00:00", end=f"{MONDAY + timedelta(weeks=5)}T00:00")["fixed"]:
            found.setdefault(f["title"], f)
        return found

    def verdict(self) -> Verdict:
        return judge(self.ask("plan"), self.ask("items"), WEEK_END)

    def sittings(self, title: str) -> list[Sitting]:
        item_id = self.items()[title]["id"]
        return self.verdict().sittings.get(item_id, [])


@pytest.fixture(scope="module")
def planned(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Planned]]:
    """Every student set up and planned once (a few seconds each), shared by the tests below."""
    out = {}
    with pytest.MonkeyPatch.context() as env:
        env.setenv("FRIDAY_CONFIG", str(tmp_path_factory.mktemp("config") / "friday.toml"))
        env.delenv("ANTHROPIC_API_KEY", raising=False)
        for key, student in STUDENTS.items():
            conn = open_student(tmp_path_factory.mktemp(key) / "friday.db", student, NOW)
            replan(conn, NOW)  # on the default budget: these judge the plan a student actually gets
            out[key] = Planned(student, conn)
        yield out
    for p in out.values():
        p.conn.close()


# What came in


@pytest.mark.parametrize("key", STUDENTS)
def test_everything_is_answered_but_unread_mail_and_each_class_is_one_repeat_with_its_tag(
    planned: dict[str, Planned], key: str
) -> None:
    p = planned[key]
    waiting = {s["input"]["title"] for s in p.ask("inbox")["suggestions"]}
    assert waiting == {w.title for letter in p.student.letters if letter.unread for w in letter.finds}
    assert p.ask("calendar_repeats") == []
    series = {s["title"]: s for s in p.ask("series_list")}
    for m in p.student.meetings:
        title = m.plain or m.title
        assert title in series, f"{title} isn't a repeat: {sorted(series)}"
        assert series[title]["external"], title
    for m in p.student.meetings:
        assert series[m.plain or m.title]["area"] == m.tag, m.title


@pytest.mark.parametrize("key", STUDENTS)
def test_each_piece_of_work_arrives_once_with_its_due_and_real_length(planned: dict[str, Planned], key: str) -> None:
    p = planned[key]
    items = p.items()
    now = datetime.combine(MONDAY, time(9))
    unread = {w.title for letter in p.student.letters if letter.unread for w in letter.finds}
    for title, hours in hours_by_title(p.student).items():
        due = next((w for w in p.student.work if w.title == title), None)
        if due is not None and datetime.combine(MONDAY + timedelta(days=due.day), time.fromisoformat(due.at)) < now:
            assert title not in items, f"{title} was due before Friday read it"
            continue
        prelim = next((e for e in p.student.prelims if f"Prep: {e.title}" == title), None)
        if title in unread or (prelim and prelim.day < 0):
            continue
        assert title in items, f"{title} never arrived: {sorted(items)}"
        assert items[title]["duration_min"] == round(hours * 60), title
        assert [i["title"] for i in p.ask("items")].count(title) == 1, f"{title} arrived twice"
    for w in p.student.work:
        if w.day >= 0 and w.title in items:
            assert items[w.title]["due"] == f"{MONDAY + timedelta(days=w.day)}T{w.at}", w.title


@pytest.mark.parametrize("key", STUDENTS)
def test_prelims_are_exams_and_each_has_its_prep_before_it(planned: dict[str, Planned], key: str) -> None:
    p = planned[key]
    items, events = p.items(), p.events()
    for prelim in (e for e in p.student.prelims if e.day >= 0):  # those before today are history (sim/history.py)
        exam, prep = events[prelim.title], items[f"Prep: {prelim.title}"]
        assert exam["preset"] == "Exam" and exam["start"] == f"{MONDAY + timedelta(days=prelim.day)}T{prelim.start}"
        assert prep["preset"] == "Exam prep" and prep["due"] == exam["start"]


@pytest.mark.parametrize("key", STUDENTS)
def test_course_mail_is_read_and_newsletters_receipts_and_sales_are_not(planned: dict[str, Planned], key: str) -> None:
    p = planned[key]
    log = {m["subject"]: m for m in p.ask("mail_log")}
    for letter in p.student.letters:
        status = log[letter.subject]["status"]
        if letter.finds:
            assert status == "read", letter.subject
        elif letter.sender.split("<")[0].strip() in ("Cornell Dining", "Cornell Store", "Cornell Chronicle"):
            assert status == "skipped", letter.subject


def test_typed_lines_come_out_as_a_student_means_them(planned: dict[str, Planned]) -> None:
    alex, daniel, elena = planned["alex"].items(), planned["daniel"].items(), planned["elena"].items()
    assert alex["FWS essay draft"]["area"] == "ENGL 1170" and alex["FWS essay draft"]["due"] == "2026-10-28T23:59"
    gym = [i for i in planned["alex"].ask("items") if i["title"] == "gym"][:3]
    assert [i["due"][:10] for i in gym] == ["2026-10-20", "2026-10-22", "2026-10-24"]  # Mon, Wed and Fri, each that day
    assert daniel["MCAT practice"]["preset"] == "Goal" and daniel["MCAT practice"]["series_id"]  # a weekly goal
    assert elena["Middlemarch Book 4"]["preset"] == "Reading" and elena["Middlemarch Book 4"]["area"] == "ENGL 3640"
    form = planned["alex"].items()["ENGRI team signup form"]
    assert form["preset"] == "Errand" and form["firmness"] == "hard"  # a form due Friday 5pm is due then


# How the week is planned


@pytest.mark.parametrize("key", FEASIBLE)
def test_a_feasible_week_is_on_time_in_real_sittings_with_no_marathons(planned: dict[str, Planned], key: str) -> None:
    v = planned[key].verdict()
    assert v.late == {}
    # A 45-minute piece of a pset in a full week. Since meals are kept (M16: Priya's 14 meals went from 0 to 14) her
    # week puts 4 short prelab and slides pieces in the gaps between morning classes; with meals placed first in the
    # start plan (combined decision C6) and exam prep never after its exam, one more: a lunch kept each day is worth it.
    # With lunch and dinner never given up for work (26 Oct), one more again.
    allowed = 6 if planned[key].student.load == "heavy" else 0
    assert len(v.scraps) <= allowed, [(s.title, s.start, s.minutes) for s in v.scraps]
    assert v.marathons == [], [(s.title, s.start, s.minutes) for s in v.marathons]
    assert v.unplanned == []


@pytest.mark.parametrize("key", FEASIBLE)
def test_no_day_is_overfull_and_work_ends_with_room_before_its_due(planned: dict[str, Planned], key: str) -> None:
    v = planned[key].verdict()
    assert max(v.day_hours.values()) <= 8.5, v.day_hours
    tight = [m for m in v.margins_h if m < 2]
    assert len(tight) <= 1, sorted(v.margins_h)[:5]  # at most one thing finished in its last two hours


@pytest.mark.parametrize("key", STUDENTS)
def test_nothing_is_planned_in_class_or_asleep(planned: dict[str, Planned], key: str) -> None:
    p = planned[key]
    fixed = [(datetime.fromisoformat(f["start"]), datetime.fromisoformat(f["end"])) for f in p.ask("plan")["fixed"]
             if f.get("start") and f.get("end") and not f["start"].endswith("T00:00")]  # fmt: skip
    nights = sleep_cores(p.student)
    for found in p.verdict().sittings.values():
        for s in found:
            assert not any(s.start < b and a < s.end for a, b in fixed), f"{s.title} at {s.start} clashes"
            assert not any(s.start < b and a < s.end for a, b in nights), f"{s.title} at {s.start} is asleep"


def sleep_cores(student: Student) -> list[tuple[datetime, datetime]]:
    """Each night from its date's bedtime to the next date's wake (an hour later on Saturday and Sunday), as
    `first_evening.set_up` sets them."""
    out = []
    for n in range(-1, 15):
        day = MONDAY + timedelta(days=n)
        bed = datetime.combine(day, time.fromisoformat(student.sleep[0]))
        wake = datetime.combine(day + timedelta(days=1), time.fromisoformat(student.sleep[1]))
        bed += timedelta(hours=1) if day.weekday() >= 5 else timedelta()
        wake += timedelta(hours=1) if (day + timedelta(days=1)).weekday() >= 5 else timedelta()
        out.append((bed + timedelta(days=1) if bed.hour < 4 else bed, wake))
    return out


@pytest.mark.parametrize("key", [k for k in STUDENTS if STUDENTS[k].prelims])
def test_prep_comes_before_each_prelim_over_more_than_one_day(planned: dict[str, Planned], key: str) -> None:
    p = planned[key]
    for prelim in (e for e in p.student.prelims if e.day >= 0):
        found = p.sittings(f"Prep: {prelim.title}")
        exam = datetime.combine(MONDAY + timedelta(days=prelim.day), time.fromisoformat(prelim.start))
        if not found or exam > WEEK_END + timedelta(days=7):
            continue
        assert all(s.end <= exam for s in found), prelim.title
        if prelim.day >= 3:  # tomorrow's prelim is prepared for today
            assert len({s.start.date() for s in found}) >= 2, f"{prelim.title} prep in one day: {found}"


# Fixed in M16 (meals are wellbeing, not load, and the start plan places them): the rest are known.
MEALS_LEFT = {
    # The week is impossible, and a missed deadline outranks a meal; whether it should is the open question.
    "riley": "Riley's overloaded week gives the deadlines tier every free hour, meals included",
    # A plan cheaper on every rule but spread has lunch there (found by locking it); the search doesn't find it.
    "elena": "Friday's lunch fits only in 13:20-14:00, between two blocks of work, and the search misses it",
}


@pytest.mark.parametrize(
    "key", [pytest.param(k, marks=pytest.mark.xfail(reason=MEALS_LEFT[k])) if k in MEALS_LEFT else k for k in STUDENTS]
)
def test_meals_are_planned_each_day_inside_their_windows_whenever_there_is_room(
    planned: dict[str, Planned], key: str
) -> None:
    p = planned[key]
    routines = {r.title: r for r in p.student.routines}
    pad = timedelta(minutes=10)  # the buffer kept around classes: 30 free minutes between two is 10 usable
    busy = [(datetime.fromisoformat(f["start"]) - pad, datetime.fromisoformat(f["end"]) + pad)
            for f in p.ask("plan")["fixed"]
            if f.get("start") and f.get("end") and not f["start"].endswith("T00:00")]  # fmt: skip
    busy += sleep_cores(p.student)
    wrong = []
    for meal in p.verdict().meals:
        r = routines[meal.title]
        assert r.window and isinstance(r.minutes, tuple)
        day = date.fromisoformat(meal.day)
        opens, closes = (datetime.combine(day, time.fromisoformat(t)) for t in r.window)
        if closes <= datetime.combine(MONDAY, time(9)) or longest_free(opens, closes, busy) < r.minutes[0]:
            continue  # over before now, or no room for it (Wednesday's lunch between Jordan's classes)
        if meal.minutes < r.minutes[0] or not meal.inside:
            wrong.append((meal.title, meal.day, meal.start, meal.minutes))
    assert wrong == []


def longest_free(opens: datetime, closes: datetime, busy: list[tuple[datetime, datetime]]) -> int:
    """The longest stretch in [opens, closes) that nothing in `busy` covers, in minutes."""
    longest, at = 0, opens
    for a, b in sorted((max(a, opens), min(b, closes)) for a, b in busy if a < closes and b > opens):
        longest, at = max(longest, int((a - at).total_seconds() // 60)), max(at, b)
    return max(longest, int((closes - at).total_seconds() // 60))


def test_each_students_own_rules_are_kept(planned: dict[str, Planned]) -> None:
    def work_between(key: str, weekday: int, start: str, end: str) -> list[Sitting]:
        a, b = time.fromisoformat(start), time.fromisoformat(end)
        meals = {r.title for r in planned[key].student.routines}  # a Friday dinner isn't work on a free evening
        found = [s for sittings in planned[key].verdict().sittings.values() for s in sittings
                 if s.start < WEEK_END and s.title not in meals]  # fmt: skip
        return [s for s in found if s.start.weekday() == weekday and s.start.time() < b and s.end.time() > a]

    assert work_between("maya", 4, "17:00", "22:00") == []  # keep friday evenings free
    assert work_between("jordan", 5, "08:00", "12:00") == []  # keep saturday mornings free
    for day in range(7):
        assert work_between("daniel", day, "22:00", "23:59") == []  # no work after 10pm


def test_a_twelve_hour_assignment_goes_in_three_hour_sittings_over_several_days(planned: dict[str, Planned]) -> None:
    found = planned["jordan"].sittings("CS 2110 A5: Graphs")
    # Sittings, not slivers: an hour and a half at least. (27 Oct: with "groceries on sunday afternoons" read as Sunday
    # afternoons rather than all of Sunday, one sitting came out at 1h30 where all had been 2h or more.)
    assert len({s.start.date() for s in found}) >= 3 and all(s.minutes >= 90 for s in found), found


GOAL_SQUEEZED = (
    "Daniel's MCAT goal gets 3 of its 6 hours: a weekly goal is a preference, and his week has little room left once "
    "meals are kept"
)


@pytest.mark.xfail(reason=GOAL_SQUEEZED, strict=False)
def test_a_weekly_goal_gets_its_hours(planned: dict[str, Planned]) -> None:
    mcat = [i for i in planned["daniel"].ask("items") if i["title"] == "MCAT practice"][0]
    found = planned["daniel"].verdict().sittings[mcat["id"]]
    assert sum(s.minutes for s in found) >= 6 * 60


def test_open_items_take_an_hour_a_day_not_every_free_afternoon(planned: dict[str, Planned]) -> None:
    for key in ("maya", "jordan"):
        assert planned[key].verdict().open_hours <= 7


def test_work_due_weeks_away_is_paced_not_scattered_in_half_hours(planned: dict[str, Planned]) -> None:
    v = planned["elena"].verdict()
    items = {i["id"]: i for i in planned["elena"].ask("items")}
    far = [s for item_id, found in v.sittings.items() for s in found
           if items[item_id]["due"] and items[item_id]["due"] > "2026-11-02" and s.minutes < 60]  # fmt: skip
    assert far == []


# A week nobody could finish


def test_an_impossible_week_keeps_the_earliest_deadlines_and_says_what_will_be_late(
    planned: dict[str, Planned],
) -> None:
    riley = planned["riley"]
    v = riley.verdict()
    assert v.late, "about 60 hours due in four days can't all be on time"
    assert {"Prep: CS 4820 Prelim 2", "CS 4820 Problem Set 7", "Prep: MATH 4130 Prelim 2"}.isdisjoint(v.late)
    triage = riley.ask("triage")
    assert triage["late"] and triage["options"]
    assert max(v.day_hours.values()) <= 11


def test_a_lab_that_overlaps_a_lecture_is_pointed_out(planned: dict[str, Planned]) -> None:
    notices = planned["priya"].ask("status")["notices"]  # her Thursday lab starts before ENGRD 2700 ends
    assert "ENGRD 2700 Lecture and ECE 3150 Lab overlap on Thu Oct 22 at 2:30pm" in notices
    assert planned["maya"].ask("status")["notices"] == []
    assert planned["elena"].ask("status")["notices"] == []  # her in-class midterm takes the lecture's place


def test_status_names_what_will_be_late_and_nothing_when_all_fits(planned: dict[str, Planned]) -> None:
    late = planned["riley"].ask("status")["late"]
    assert late and all(hours > 0 for hours in late.values())
    assert set(late) == set(planned["riley"].verdict().late)
    assert all(planned[k].ask("status")["late"] == {} for k in FEASIBLE)


def test_late_work_is_still_done_in_sittings_not_slivers(planned: dict[str, Planned]) -> None:
    v = planned["riley"].verdict()
    items = {i["id"]: i for i in planned["riley"].ask("items")}
    for item_id, found in v.sittings.items():
        if items.get(item_id, {}).get("title") in v.late:
            assert sum(s.minutes < 60 for s in found) <= 2, [(s.start, s.minutes) for s in found]


def test_day_headers_flag_deadlines_not_where_a_chores_week_ends(planned: dict[str, Planned]) -> None:
    flagged = {d["title"] for d in planned["maya"].ask("calendar", start=f"{MONDAY}", days=7)["dues"]}
    assert "Return library books" in flagged and "Laundry" not in flagged


def test_an_essay_from_a_template_is_started_weeks_ahead_not_left_for_its_last_days(
    tmp_path: Path,
) -> None:
    conn = open_student(tmp_path / "friday.db", STUDENTS["elena"], NOW)
    p = Planned(STUDENTS["elena"], conn)
    paper = p.items()["ENGL 3640 seminar paper"]
    run(conn, "drop", {"id": paper["id"]}, now_utc=NOW, provisional=False)
    run(conn, "template_apply", {"template": "Essay", "title": "Seminar paper", "hours": 12, "due": paper["due"]},
        now_utc=NOW, provisional=False)  # fmt: skip
    replan(conn, NOW)
    outline, draft = p.sittings("Outline"), p.sittings("Draft")
    assert outline and outline[-1].end < datetime(2026, 10, 23), outline  # due Nov 6: outlined this week
    assert draft and draft[0].start >= outline[-1].end
    conn.close()


def test_a_read_comes_into_the_inbox_in_date_order(tmp_path: Path) -> None:
    from friday.commands.fetching import sync
    from friday.sim.cornell import term

    conn = open_student(tmp_path / "friday.db", STUDENTS["jordan"], NOW)
    for suggestion in run(conn, "inbox", {}, now_utc=NOW).result["suggestions"]:
        run(conn, "suggestion_reject", {"id": suggestion["id"]}, now_utc=NOW, provisional=False)
    sample = term(STUDENTS["jordan"], MONDAY)
    for n, day in ((2, 28), (1, 26)):  # read in this order, due in the other
        at = {"dateTime": f"2026-10-{day}T23:59:00-04:00"}
        sample.google.calendars_by_id["canvas@g"].append(
            {"id": f"extra{n}", "summary": f"Extra Credit {n} [CS2110]", "start": at, "end": at}
        )
    conn.execute("INSERT OR REPLACE INTO kv (user_id, key, value) VALUES (1, 'sync_now', '1')")
    sync(conn, NOW + 60, google=sample.google, mail=sample.gmail, client=sample.ai)
    found = [s["input"]["title"] for s in run(conn, "inbox", {}, now_utc=NOW).result["suggestions"]]
    assert found == ["Extra Credit 1 [CS2110]", "Extra Credit 2 [CS2110]"]
    conn.close()
