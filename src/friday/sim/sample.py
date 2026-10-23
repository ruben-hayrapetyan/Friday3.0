"""A sample student's term as Google and Gmail would give it (M12c), for tests and `fridayd demo`: numbered
calendars, repeating lectures, labs and discussions (one moved, one cancelled), exams, all-day homework, a Canvas
calendar of zero-length due times, personal and club events, a declined invite and holidays; and a mailbox of
course mail, receipts, newsletters and notes from people, with what the AI would read in each.

Everything is made up and dated from the Monday of the week given, so the sample is always current.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from friday.sim.fakes import FakeGmail, FakeGoogle, ScriptedClient, mail

# key: (title, weekdays (Mon = 0), start, end, calendar)
COURSES = {
    "chem": ("CHEM 2090, Lecture", (0, 2, 4), "12:20", "13:10"),
    "chemlab": ("CHEM 2091, Laboratory", (0,), "13:25", "16:25"),
    "math": ("MATH 1920, Lecture", (0, 2, 4), "11:15", "12:05"),
    "mathdis": ("MATH 1920, Discussion", (1,), "14:30", "15:20"),
    "cs": ("CS 1110, Lecture", (1, 3), "11:15", "12:05"),
    "csdis": ("CS 1110, Discussion", (2,), "13:25", "14:15"),
    "phys": ("PHYS 1110, Lecture", (4,), "14:30", "15:20"),
    "physlab": ("PHYS 1110, Laboratory", (1,), "12:20", "14:15"),
    "engrg": ("ENGRG 1050, Seminar", (3,), "13:25", "14:15"),
}
ROUTINES = {
    "gym": ("Gym", (0, 2, 4), "07:00", "08:00", "personal@g"),
    "home": ("Call home", (6,), "19:00", "19:30", "personal@g"),
    "robotics": ("Robotics team meeting", (3,), "18:00", "20:00", "extra@g"),
}
CALENDARS = {
    "projects@g": "1. Projects",
    "todo@g": "2. To-Do",
    "personal@g": "3. Personal",
    "school@g": "4. School",
    "homework@g": "5. Homework",
    "extra@g": "6. Extracurricular",
    "events@g": "7. Events",
    "canvas@g": "Student Calendar (Canvas)",
    "holidays@g": "Holidays in United States",
    "friday@g": "Friday",
}
# How the small model would sort the sample's events: its kind and a plain title.
SORTS = {title: ("Class", title) for title, *_ in COURSES.values()} | {
    "Gym": ("Event", "Gym"),
    "Call home": ("Event", "Call home"),
    "Robotics team meeting": ("Meeting", "Robotics team meeting"),
    "CHEM Prelim 2": ("Exam", "CHEM Prelim 2"),
    "MATH Quiz 2": ("Exam", "MATH Quiz 2"),
    "Math HW8 Due": ("Assignment", "Math HW8"),
    "Math HW9 Due": ("Assignment", "Math HW9"),
    "PHYS Project Proposal (TWR)": ("Assignment", "PHYS project proposal"),
    "CHEM Reading Response": ("Assignment", "CHEM reading response"),
    "Light Intensity Lab [PHYS1110]": ("Assignment", "PHYS 1110 Light Intensity Lab"),
    "Ethics Exit Ticket Reflection [ENGRG1050]": ("Assignment", "ENGRG 1050 exit ticket reflection"),
    "Startup Recruitment Expo [Toolkit]": ("Event", "Startup Recruitment Expo"),
    "Dentist": ("Appointment", "Dentist"),
    "Club social": ("Event", "Club social"),
    "Career fair": ("Event", "Career fair"),
    "Halloween": ("Event", "Halloween"),
}
WEEKS = range(-1, 4)  # last week (for yesterday) to three weeks ahead
ZONE = ZoneInfo("America/New_York")  # the calendars' own timezone; Google gives times in its offset


@dataclass
class Sample:
    google: FakeGoogle
    gmail: FakeGmail
    ai: ScriptedClient
    monday: date


def term(today: date) -> Sample:
    monday = today - timedelta(days=today.weekday())
    google = FakeGoogle({cid: [] for cid in CALENDARS}, primary="projects@g", names=CALENDARS)
    add = google.calendars_by_id
    for key, (title, days, start, end) in COURSES.items():
        add["school@g"] += weekly(monday, key, title, days, start, end)
    for key, (title, days, start, end, calendar) in ROUTINES.items():
        add[calendar] += weekly(monday, key, title, days, start, end)
    move_and_cancel(add["school@g"], monday)
    add["school@g"] += [
        timed("prelim", "CHEM Prelim 2", monday + timedelta(days=3), "19:30", "21:00"),
        all_day("quiz", "MATH Quiz 2", monday + timedelta(days=8)),
    ]
    add["homework@g"] += [
        e | {"recurringEventId": "reading"}
        for e in (all_day(f"reading_{w}", "CHEM Reading Response", monday + timedelta(days=7 * w + 4)) for w in WEEKS)
    ]
    add["homework@g"] += [
        all_day("hw8", "Math HW8 Due", monday + timedelta(days=3)),
        all_day("hw9", "Math HW9 Due", monday + timedelta(days=10)),
        all_day("proposal", "PHYS Project Proposal (TWR)", monday + timedelta(days=11)),
    ]
    add["canvas@g"] += [
        timed("lab1", "Light Intensity Lab [PHYS1110]", monday + timedelta(days=8), "23:30", "23:30"),
        timed("exit", "Ethics Exit Ticket Reflection [ENGRG1050]", monday + timedelta(days=14), "18:00", "18:00"),
        timed("expo", "Startup Recruitment Expo [Toolkit]", monday + timedelta(days=1), "15:00", "19:00"),
    ]
    add["personal@g"].append(timed("dentist", "Dentist", monday + timedelta(days=4), "09:00", "10:00"))
    birthday = all_day("bday", "Sam's Birthday", monday + timedelta(days=6))
    add["personal@g"].append(birthday | {"recurringEventId": "bday"})
    google.rules = {"bday": "FREQ=YEARLY", "reading": "FREQ=WEEKLY;BYDAY=FR"} | {
        key: "FREQ=WEEKLY;BYDAY=" + ",".join(("MO", "TU", "WE", "TH", "FR", "SA", "SU")[d] for d in days)
        for key, (_, days, *_rest) in (COURSES | ROUTINES).items()
    }
    declined = {"attendees": [{"self": True, "responseStatus": "declined"}]}
    add["extra@g"].append(timed("social", "Club social", monday + timedelta(days=2), "18:00", "19:00") | declined)
    add["events@g"].append(all_day("fair", "Career fair", monday + timedelta(days=9)))
    add["holidays@g"].append(all_day("halloween", "Halloween", monday + timedelta(days=5)))
    gmail, ai = mailbox(monday)
    return Sample(google, gmail, ai, monday)


def weekly(monday: date, key: str, title: str, days: tuple[int, ...], start: str, end: str) -> list[dict[str, Any]]:
    """Instances of a repeating event, as Google gives them with `singleEvents`."""
    out = []
    for week in WEEKS:
        for day in days:
            on = monday + timedelta(days=7 * week + day)
            out.append(timed(f"{key}_{on:%Y%m%d}", title, on, start, end) | {"recurringEventId": key})
    return out


def move_and_cancel(school: list[dict[str, Any]], monday: date) -> None:
    """Next Wednesday's chemistry lecture moves to 14:00; next Friday's math lecture is cancelled."""
    wednesday, friday = monday + timedelta(days=9), monday + timedelta(days=11)
    moved_id = f"chem_{wednesday:%Y%m%d}"
    for i, e in enumerate(school):
        if e["id"] == moved_id:
            school[i] = timed(moved_id, e["summary"], wednesday, "14:00", "14:50") | {
                "recurringEventId": "chem",
                "originalStartTime": e["start"],
            }
    school[:] = [e for e in school if e["id"] != f"math_{friday:%Y%m%d}"]


def timed(eid: str, summary: str, on: date, start: str, end: str) -> dict[str, Any]:
    return {
        "id": eid,
        "summary": summary,
        "start": {"dateTime": datetime.combine(on, time.fromisoformat(start), ZONE).isoformat()},
        "end": {"dateTime": datetime.combine(on, time.fromisoformat(end), ZONE).isoformat()},
    }


def all_day(eid: str, summary: str, on: date) -> dict[str, Any]:
    return {"id": eid, "summary": summary, "start": {"date": f"{on}"}, "end": {"date": f"{on + timedelta(days=1)}"}}


def mailbox(monday: date) -> tuple[FakeGmail, ScriptedClient]:
    def day(n: int) -> str:
        return f"{monday + timedelta(days=n)}"

    thursday, friday, next_tuesday = day(3), day(4), day(8)
    messages = [
        mail("m1", "Ed Discussion <noreply@edstem.org>", "[CS 1110] New Assignment Released",
             f"<p>A5 has been released. It is due Thursday {thursday} at 11:59pm.</p>", bulk=True),
        mail("m2", "Ed Discussion <noreply@edstem.org>", "[CS 1110] Prelim 1, Support Sessions, and A4",
             "<p>Prelim grades are out. Office hours are listed on the course page.</p>", bulk=True),
        mail("m3", "Gradescope <no-reply@gradescope.com>", "[MATH1920 on Gradescope] Successfully submitted to HW7",
             "<p>Your submission was received.</p>", bulk=True),
        mail("m4", "Admissions <hello@college.edu>", "Your future is waiting",
             "<p>Apply by the priority deadline and save!</p>", bulk=True),
        mail("m5", "Residential Life <housing@school.edu>", "RA APPLICATION REMINDER: Priority Due Date",
             f"<p>The RA application is due {next_tuesday} at 5pm.</p>", bulk=True),
        mail("m6", "Prof. Rivera <rivera@chem.school.edu>", "Re: Makeup Lab Report",
             f"<p>Please submit the makeup lab report by Friday {friday} at 5pm.</p>"),
        mail("m7", "Sam <sam@gmail.com>", "Lunch?", "<p>Want to grab lunch tomorrow?</p>"),
        mail("m8", "Math Department <math@school.edu>", "Prelim 2 Conflict Form",
             f"<p>If you have an exam conflict, fill in the form by {thursday}.</p>"),
        mail("m9", "Bursar <bursar@school.edu>", "Your eBill has not been viewed",
             "<p>Your payment is due soon. View your eBill online.</p>", bulk=True),
        mail("m10", "Jo <jo@robotics.club>", "Robotics meeting moved",
             "<p>This week's meeting is moved to Friday, same time.</p>"),
        mail("m11", "Trends Weekly <news@trends.example>", "Gen Alpha will soon dominate culture",
             "<p>Read before the deadline to subscribe at half price.</p>", bulk=True),
        mail("m12", "Financial Aid <finaid@school.edu>", "Action needed: submit your verification documents",
             f"<p>Please submit your verification documents by {day(10)}.</p>"),
    ]  # fmt: skip
    answers = {
        "A5 has been released": items(("CS 1110 A5", "Assignment", f"{thursday}T23:59", f"due Thursday {thursday}")),
        "RA application is due": items(("RA application", "Errand", f"{next_tuesday}T17:00", f"due {next_tuesday}")),
        "makeup lab report": items(("Makeup lab report", "Assignment", f"{friday}T17:00", f"by Friday {friday}")),
        "exam conflict": items(("Prelim 2 conflict form", "Errand", f"{thursday}T23:59", f"by {thursday}")),
        "verification documents": items(("Financial aid verification", "Errand", f"{day(10)}T23:59", f"by {day(10)}")),
    }
    return FakeGmail(messages), ScriptedClient(answers, SORTS)


def items(*found: tuple[str, str, str, str]) -> dict[str, Any]:
    """The AI's answer: each item's title, kind, due and the words the due came from."""
    return {
        "is_syllabus": False,
        "items": [
            {"title": t, "preset": k, "due": d, "confidence": 0.9, "quotes": {"title": t, "due": q}}
            for t, k, d, q in found
        ],
    }
