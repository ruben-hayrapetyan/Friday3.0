"""Seven Cornell students for sim/cornell.py, from a very light senior fall to a prelim week nobody could finish.
Courses, times and hours are plausible, not any real section; days count from this week's Monday (0), so -2 is
last Saturday and 9 is next Wednesday. Weekly meetings use Cornell's slots (MWF on the hour-and-a-bit, TR 75
minutes) and evening prelims at 19:30. The three heaviest are in sim/students_heavy.py.
"""

from friday.sim.cornell import BULK, Event, Letter, Meeting, Prelim, Project, Student, Work, course, each_week, meals
from friday.sim.students_heavy import DANIEL, PRIYA, RILEY

MAYA = Student(
    key="maya",
    name="Maya",
    about="Senior in Information Science with a job offer signed: three classes, a library shift, little due",
    load="very light",
    netid="mc2289",
    sleep=("00:30", "09:00"),
    meetings=(
        *course("INFO 4390", ("LEC 001", "TR", "10:10", "11:25")),
        *course("COMM 3200", ("LEC 001", "MW", "14:55", "16:10")),
        *course("HADM 4300", ("LEC 001", "W", "16:45", "18:40")),
        Meeting("Olin Library circulation desk", "MR", "18:00", "21:00", calendar="work", kind="Event", tag="Job"),
    ),  # fmt: skip
    work=(
        *each_week(
            "INFO 4390 Reading Response {n}",
            1,
            1,
            first=6,
            at="10:00",
            raw="Reading Response {n} [INFO4390]",
            tag="INFO 4390",
        ),
        Work("COMM 3200 Essay 2", 16, 6, via="homework", tag="COMM 3200"),
    ),  # fmt: skip
    events=(
        Event("Haircut", 2, "13:00", "13:45", kind="Appointment", was=("11:00", "11:45")),
        Event("Dad's Birthday", 12),
    ),
    letters=(
        Letter(
            "Prof. Lee <lee@cornell.edu>",
            "INFO 4390 final project proposals",
            "Hi all, project proposals (one page) are due {d11} at 11:59pm on Canvas.",
            finds=(Work("INFO 4390 project proposal", 11, 3, via="mail", tag="INFO 4390"),),
        ),
        Letter(
            "Prof. Lee <lee@cornell.edu>",
            "Peer review pairs",
            "You'll each review two proposals. Submit your peer reviews by {d13} at 5pm.",
            finds=(Work("INFO 4390 peer reviews", 13, 1.5, via="mail", at="17:00", tag="INFO 4390"),),
            unread=True,
        ),
        Letter(
            "Cornell Career Services <careers@cornell.edu>",
            "Handshake: 40 employers hiring now",
            "Apply before the deadline.",
            bulk=True,
        ),
        *BULK,
    ),  # fmt: skip
    typed=(
        "Return library books due {d4} 30m",
        "Read Project Hail Mary open",
        "Laundry every sun ~1h /chore",
        "yoga every tue thu ~1h /habit",
    ),
    rules=("keep friday evenings free", "no work before 10am", "no studying on sundays pls"),
    routines=meals(lunch=("12:00", "14:30"), dinner=("17:00", "21:00")),
    notes=(
        "Mostly empty: each reading response in one sitting before Tuesday's class, the essay done early in "
        "one or two sittings, nothing before 10:00 on weekdays (she wakes at 9), Friday evening empty.",
    ),
)

ALEX = Student(
    key="alex",
    name="Alex",
    about="First-year engineer: calculus, physics, chemistry with a lab, a writing seminar, rocketry club",
    load="light",
    netid="aj452",
    sleep=("23:30", "07:30"),
    meetings=(
        *course("MATH 1910", ("LEC 003", "MWF", "10:10", "11:00"), ("DIS 210", "T", "08:40", "09:30")),
        *course("CHEM 2090", ("LEC 001", "MWF", "12:20", "13:10"), ("LAB 220", "R", "13:25", "16:25")),
        *course("PHYS 1112", ("LEC 001", "TR", "10:10", "11:25"), ("DIS 204", "F", "13:25", "14:15")),
        Meeting("ENGL 1170 FWS: Short Stories", "MWF", "09:05", "09:55", plain="ENGL 1170 Seminar", tag="ENGL 1170"),
        Meeting(
            "Cornell Rocketry general meeting", "W", "19:00", "20:00", calendar="clubs", kind="Meeting", tag="Rocketry"
        ),
    ),  # fmt: skip
    prelims=(
        Prelim("CHEM 2090 Prelim 1", -12, prep_hours=4, where="Baker Lab 200"),  # before today (sim/history.py)
        Prelim("PHYS 1112 Prelim 2", 8, prep_hours=5, where="Baker Lab 200"),
        Prelim("MATH 1910 Prelim 2", 15, prep_hours=6, where="Statler Auditorium"),
    ),  # fmt: skip
    work=(
        *each_week("MATH 1910 WebWork {n}", 2, 1.5, first=8, raw="WebWork {n} [MATH1910]", tag="MATH 1910"),
        *each_week("MATH 1910 Written HW {n}", 4, 2, first=8, via="homework", tag="MATH 1910"),
        *each_week("PHYS 1112 Mastering Physics {n}", 7, 2, first=9, at="08:00", tag="PHYS 1112"),
    ),  # fmt: skip
    events=(
        Event("Advising appointment", 3, "11:40", "12:10", kind="Appointment", was=("16:40", "17:10")),
        Event("Fall Family Weekend", 26),
    ),  # fmt: skip
    letters=(
        Letter(
            "Hannah (CHEM 2090 TA) <hk527@cornell.edu>",
            "Lab 6 report",
            "Reports for Lab 6 are due {d10} at 11:59pm. Use the template on Canvas.",
            finds=(Work("CHEM 2090 lab report 6", 10, 4, via="mail", tag="CHEM 2090"),),
        ),
        Letter(
            "Engineering Advising <engr-advising@cornell.edu>",
            "Project team signups due Friday",
            "Submit the ENGRI team signup form by {d4} at 5pm.",
            bulk=True,
            finds=(Work("ENGRI team signup form", 4, 0.5, via="mail", kind="Errand", at="17:00"),),
        ),
        Letter(
            "Cornell Rocketry <rocketry-l@cornell.edu>",
            "Rocketry newsletter #7",
            "Launch photos inside. Dues are due soon!",
            bulk=True,
        ),
        Letter(
            "PHYS 1112 Staff <phys1112@cornell.edu>",
            "Practice prelim posted",
            "Do the practice prelim before the review session {d7} at 7pm and bring questions.",
            finds=(Work("PHYS 1112 practice prelim", 7, 2, via="mail", at="19:00", tag="PHYS 1112"),),
            unread=True,
        ),
        *BULK,
    ),  # fmt: skip
    typed=(
        "FWS essay draft due {d9} 11:59pm ~4h #engl1170",
        "gym every mon,wed,fri ~1h /habit",
        "Call home sun 7pm 30m",
        "Laundry every sat ~1h /chore",
    ),  # fmt: skip
    rules=("no work after 11pm", "gym in the morning", "nothing after 9pm on fridays"),
    routines=meals(lunch=("11:00", "13:30"), dinner=("17:30", "20:00"), breakfast=("07:45", "09:00")),
    notes=(
        "A light week: each WebWork and written HW in one sitting before its due, the lab report and essay draft "
        "next week, physics prep over two or more days before Tuesday's prelim; nothing after 23:30 or before "
        "08:30.",
    ),
)

JORDAN = Student(
    key="jordan",
    name="Jordan",
    about="CS sophomore: CS 2110's big assignments, CS 2800 problem sets, linear algebra, economics, two clubs",
    load="moderate",
    netid="jt673",
    sleep=("00:30", "08:30"),
    meetings=(
        *course("CS 2110", ("LEC 001", "TR", "11:40", "12:55"), ("DIS 205", "W", "12:20", "13:10")),
        *course("CS 2800", ("LEC 001", "MWF", "11:15", "12:05")),
        *course("MATH 2940", ("LEC 002", "MWF", "13:25", "14:15"), ("DIS 208", "R", "10:10", "11:00")),
        *course("ECON 1110", ("LEC 001", "TR", "14:55", "16:10"), ("DIS 211", "F", "10:10", "11:00")),
        Meeting(
            "Big Red Hacks committee", "M", "19:30", "20:30", calendar="clubs", kind="Meeting", tag="Big Red Hacks"
        ),
        Meeting("Intramural soccer", "U", "14:00", "15:30", calendar="clubs", kind="Event", tag="Soccer"),
    ),  # fmt: skip
    prelims=(
        Prelim("MATH 2940 Prelim 1", -13, prep_hours=4, where="Malott 251"),  # before today (sim/history.py)
        Prelim("ECON 1110 Prelim 2", 3, prep_hours=3, where="Bailey Hall"),
        Prelim("CS 2800 Prelim 2", 9, prep_hours=6, where="Statler Auditorium"),
    ),  # fmt: skip
    work=(
        Work("CS 2110 A5: Graphs", 10, 12, raw="A5: Graphs [CS2110]", tag="CS 2110"),
        Work("CS 2800 Problem Set 7", 3, 5, via="homework", tag="CS 2800"),
        Work("CS 2800 Problem Set 8", 17, 5, via="homework", tag="CS 2800"),
        *each_week("MATH 2940 HW {n}", 4, 3, first=8, raw="HW {n} [MATH2940]", tag="MATH 2940"),
        *each_week("ECON 1110 Aplia quiz {n}", 6, 1, first=7, raw="Aplia Quiz {n} [ECON1110]", tag="ECON 1110"),
    ),  # fmt: skip
    events=(Event("Info session: Jane Street", 1, "18:00", "19:00", calendar="clubs", was=("17:00", "18:00")),),
    letters=(
        Letter(
            "CS 2110 <cs2110-staff@cornell.edu>",
            "[CS 2110] A5 released",
            "A5 (Graphs) is out. It is due {d10} at 11:59pm. Start early: it is the longest assignment.",
            bulk=True,
        ),
        Letter(
            "Big Red Hacks <bigredhacks@cornell.edu>",
            "Sponsor outreach: emails due Saturday",
            "Please send your sponsor emails by {d5}. Template in the drive.",
            finds=(Work("Big Red Hacks sponsor emails", 5, 1.5, via="mail", kind="Errand"),),
        ),
        Letter(
            "CS 2800 <cs2800-staff@cornell.edu>",
            "Prelim 2 conflicts",
            "If you have a conflict with Prelim 2, fill out the conflict form by {d5} at noon.",
            finds=(Work("CS 2800 prelim conflict form", 5, 0.25, via="mail", kind="Errand", at="12:00"),),
            unread=True,
        ),
        *BULK,
    ),  # fmt: skip
    typed=(
        "Laundry /chore 1h",
        "Leetcode practice open",
        "Gym every tue,thu,sat ~1h /habit",
        "Groceries every sun ~45m /errand",
    ),
    rules=(
        "keep saturday mornings free",
        "at most 6 hours a day",
        "no more than 2h of leetcode a day",
        "groceries on sunday afternoons",
    ),
    routines=meals(lunch=("11:30", "14:30"), dinner=("18:00", "20:30")),
    project=Project(
        "Presentation",
        "Big Red Hacks sponsor pitch",
        6,
        due=12,
        made=-10,
        area="Big Red Hacks",
        waits_on=("Slides", "Big Red Hacks sponsor emails"),
    ),  # fmt: skip
    notes=(
        "A5 (12 h) spread over the days before next Wednesday in sittings of 2–3 hours, not all on Tuesday; "
        "PS 7 done before the ECON prelim evening or on Thursday afternoon; ECON prep before Thursday 19:30; CS "
        "2800 prep over several days; Saturday morning empty.",
    ),
)

ELENA = Student(
    key="elena",
    name="Elena",
    about="English and Government sophomore: daily Italian, reading-heavy seminars, papers, the Daily Sun",
    load="moderate",
    netid="eg445",
    sleep=("00:00", "08:00"),
    meetings=(
        *course("ITAL 1210", ("LEC 004", "MTWRF", "09:05", "09:55")),
        *course("ENGL 3640", ("SEM 101", "T", "13:25", "15:20")),
        *course("GOVT 3111", ("LEC 001", "MW", "10:10", "11:25"), ("DIS 207", "F", "12:20", "13:10")),
        *course("HIST 2650", ("LEC 001", "TR", "11:40", "12:55")),
        Meeting("Daily Sun news meeting", "U", "17:00", "18:00", calendar="clubs", kind="Meeting", tag="Daily Sun"),
    ),  # fmt: skip
    prelims=(
        Prelim("GOVT 3111 Midterm", -12, start="10:10", end="11:25", prep_hours=3, where="Goldwin Smith"),
        Prelim("HIST 2650 Midterm", 10, start="11:40", end="12:55", prep_hours=4, where="Goldwin Smith"),
    ),
    work=(
        *each_week(  # Book 4 she typed in; Books 2 and 3 were before today
            "ENGL 3640 reading: Middlemarch Book {n}",
            8,
            5,
            range(-3, -1),
            first=5,
            at="13:25",
            kind="Reading",
            raw="Middlemarch Book {n} [ENGL3640]",
            tag="ENGL 3640",
        ),
        *each_week(
            "ENGL 3640 reading: Middlemarch Book {n}",
            8,
            5,
            range(0, 3),
            first=5,
            at="13:25",
            kind="Reading",
            raw="Middlemarch Book {n} [ENGL3640]",
            tag="ENGL 3640",
        ),
        *each_week(
            "GOVT 3111 response paper {n}",
            4,
            2,
            first=7,
            at="12:00",
            raw="Response Paper {n} [GOVT3111]",
            tag="GOVT 3111",
        ),
        *each_week(
            "ITAL 1210 composizione {n}",
            3,
            1.5,
            first=5,
            at="09:00",
            raw="Composizione {n} [ITAL1210]",
            tag="ITAL 1210",
        ),
        Work("GOVT 3111 paper 2", 11, 8, via="homework", tag="GOVT 3111"),
    ),  # fmt: skip
    letters=(
        Letter(
            "Daily Sun News Desk <news@cornellsun.com>",
            "Your assignment: Collegetown housing story",
            "Draft due {d3} at 5pm to the desk. 800 words.",
            finds=(Work("Daily Sun housing story draft", 3, 3, via="mail", at="17:00", tag="Daily Sun"),),
        ),
        Letter(
            "Prof. Bensel <govt3111@cornell.edu>",
            "Paper 2: thesis statements",
            "Send me your thesis statement for Paper 2 by {d8} at noon.",
            finds=(Work("GOVT 3111 paper 2 thesis statement", 8, 0.5, via="mail", at="12:00", tag="GOVT 3111"),),
            unread=True,
        ),
        *BULK,
    ),  # fmt: skip
    events=(Event("Writing Center appointment", 2, "15:00", "15:45", kind="Appointment", was=("14:00", "14:45")),),
    typed=(
        "ENGL 3640 seminar paper due {d18} ~12h /project #engl3640",
        "Middlemarch Book 4 due {d1} 1:25pm ~4h /reading #engl3640",
        "Laundry every sun ~1h /chore",
        "run 3x a week ~45m /habit",
    ),  # fmt: skip
    rules=(
        "keep sunday mornings free",
        "finish essays 2 days before they're due",
        "no work after 11pm",
        "papers in the afternoon",
    ),
    routines=meals(lunch=("11:30", "14:00"), dinner=("18:00", "20:30"), breakfast=("08:00", "09:00")),
    project=Project("Essay", "HIST 2650 historiography essay", 10, due=25, made=-12, area="HIST 2650"),
    notes=(
        "Reading a book a week: Middlemarch read in two or three sittings before each Tuesday seminar, the "
        "seminar paper paced over the next weeks rather than left for its last days, the Sun draft before "
        "Thursday 17:00.",
    ),
)

STUDENTS = {s.key: s for s in (MAYA, ALEX, JORDAN, ELENA, PRIYA, DANIEL, RILEY)}
