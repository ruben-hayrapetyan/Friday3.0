"""The heavy end of sim/students.py: an ECE junior with a project team and a TA job, a pre-med with two prelims a
day apart, and a double major in a week nobody could finish."""

from friday.sim.cornell import BULK, Event, Letter, Meeting, Prelim, Project, Student, Work, course, each_week, meals

PRIYA = Student(
    key="priya",
    name="Priya",
    about="ECE junior: four technical courses with labs, a TA job, and 10 hours a week on the CUAir project team",
    load="heavy",
    netid="pr384",
    sleep=("00:30", "08:00"),
    meetings=(
        *course("ECE 3140", ("LEC 001", "TR", "10:10", "11:25"), ("LAB 402", "M", "19:30", "22:25")),
        # Her Thursday lab starts ten minutes before ENGRD 2700 ends: a clash Friday should point out.
        *course("ECE 3150", ("LEC 001", "MWF", "11:15", "12:05"), ("LAB 403", "R", "14:30", "17:25")),
        *course("ECE 3250", ("LEC 001", "MWF", "09:05", "09:55"), ("DIS 201", "T", "14:55", "15:45")),
        *course("ENGRD 2700", ("LEC 001", "TR", "13:25", "14:40")),
        Meeting("CUAir subteam meeting", "TR", "19:00", "21:00", calendar="clubs", kind="Meeting", tag="CUAir"),
        Meeting("CUAir build session", "S", "10:00", "16:00", calendar="clubs", kind="Event", tag="CUAir"),
        Meeting("ECE 2100 TA office hours", "W", "16:00", "18:00", calendar="work", kind="Event", tag="TA"),
    ),  # fmt: skip
    prelims=(
        Prelim("ECE 3140 Prelim 1", -13, prep_hours=5, where="Phillips 203"),  # before today (sim/history.py)
        Prelim("ECE 3150 Prelim 2", 8, prep_hours=8, where="Phillips 101"),
        Prelim("ENGRD 2700 Prelim 2", 10, prep_hours=6, where="Kennedy Hall 116"),
        Prelim("ECE 3250 Prelim", 15, prep_hours=6, where="Upson 116"),
    ),  # fmt: skip
    work=(
        *each_week(
            "ECE 3140 Lab {n} prelab", 0, 2, first=5, at="19:30", raw="Lab {n} Prelab [ECE3140]", tag="ECE 3140"
        ),
        *each_week(
            "ECE 3140 Lab {n} report", 7, 5, range(0, 3), first=5, raw="Lab {n} Report [ECE3140]", tag="ECE 3140"
        ),
        *each_week("ECE 3150 HW {n}", 2, 5, first=7, raw="HW{n} [ECE3150]", tag="ECE 3150"),
        *each_week("ECE 3250 Problem Set {n}", 4, 4, first=6, via="homework", tag="ECE 3250"),
        *each_week("ENGRD 2700 HW {n}", 3, 3, first=8, raw="Homework {n} [ENGRD2700]", tag="ENGRD 2700"),
    ),  # fmt: skip
    letters=(
        Letter(
            "Prof. Skovira <ece3140@cornell.edu>",
            "Final project proposals",
            "Groups: submit a two-page proposal by {d12} at 11:59pm.",
            finds=(Work("ECE 3140 final project proposal", 12, 3, via="mail", tag="ECE 3140"),),
        ),
        Letter(
            "CUAir <cuair-leads@cornell.edu>",
            "Design review Saturday: slides due Friday",
            "Each subteam submits slides by {d4} at 9pm for the design review.",
            finds=(Work("CUAir design review slides", 4, 3, via="mail", at="21:00", tag="CUAir"),),
        ),
        Letter(
            "CUAir <cuair-leads@cornell.edu>",
            "Flight test signups",
            "Sign up for a flight test slot by {d6} at 6pm.",
            finds=(Work("CUAir flight test signup", 6, 0.25, via="mail", kind="Errand", at="18:00", tag="CUAir"),),
            unread=True,
        ),
        *BULK,
    ),  # fmt: skip
    events=(Event("Dentist", 9, "08:30", "09:00", kind="Appointment", was=("09:30", "10:00")),),
    typed=(
        "ECE 2100 grading every week due sun ~3h #TA",
        "Groceries at Wegmans ~1.5h /errand",
    ),
    rules=(
        "deep work in the morning",
        "at most 9 hours a day",
        "keep weekend evenings free",
        "no problem sets after 11pm",
    ),
    routines=meals(lunch=("12:00", "14:00"), dinner=("17:30", "20:00")),
    project=Project("Essay", "ENGRD 2700 data analysis report", 10, due=20, made=-12, area="ENGRD 2700"),
    notes=(
        "Full but feasible: every lab report, HW and problem set on time; ECE 3150 prep (8 h) over several days "
        "before next Tuesday; no day over about 9 hours of work; nothing in CUAir meetings or labs; some "
        "evenings left.",
    ),
)

DANIEL = Student(
    key="daniel",
    name="Daniel",
    about="Pre-med junior: organic chemistry and its lab, biochemistry, psychology, research, volunteering, MCAT",
    load="heavy",
    netid="dk731",
    sleep=("23:00", "07:00"),
    meetings=(
        *course("CHEM 3570", ("LEC 001", "MWF", "10:10", "11:00"), ("DIS 202", "R", "08:40", "09:30")),
        *course("CHEM 2510", ("LAB 205", "W", "13:25", "17:25")),
        *course("BIOMG 3300", ("LEC 001", "TR", "10:10", "11:25")),
        *course("PSYCH 1101", ("LEC 001", "MWF", "12:20", "13:10")),
        Meeting("Research: Lin Lab", "TR", "13:00", "17:00", calendar="work", kind="Event", tag="Research"),
        Meeting(
            "Cayuga Medical Center volunteering",
            "S",
            "08:00",
            "12:00",
            calendar="clubs",
            kind="Event",
            tag="Volunteering",
        ),
    ),  # fmt: skip
    prelims=(
        Prelim("PSYCH 1101 Prelim 1", -11, prep_hours=3, where="Bailey Hall"),  # before today
        Prelim("CHEM 3570 Prelim 2", 7, prep_hours=8, where="Baker Lab 200"),
        Prelim("BIOMG 3300 Prelim 2", 9, prep_hours=7, where="Kennedy Auditorium"),
        Prelim("PSYCH 1101 Prelim 2", 16, prep_hours=4, where="Bailey Hall"),
    ),  # fmt: skip
    work=(
        *each_week("CHEM 3570 Problem Set {n}", 4, 3, first=7, raw="Problem Set {n} [CHEM3570]", tag="CHEM 3570"),
        *each_week("CHEM 2510 Prelab {n}", 2, 1, first=8, at="13:00", raw="Prelab {n} [CHEM2510]", tag="CHEM 2510"),
        *each_week("CHEM 2510 Lab report {n}", 6, 5, range(-3, 3), first=7, via="homework", tag="CHEM 2510"),
        *each_week(
            "PSYCH 1101 reading response {n}",
            0,
            1,
            range(1, 4),
            first=8,
            at="14:00",
            raw="Reading Response {n} [PSYCH1101]",
            tag="PSYCH 1101",
        ),
    ),  # fmt: skip
    letters=(
        Letter(
            "Dr. Lin <lin-lab@cornell.edu>",
            "Abstracts for the fall research forum",
            "Please send me your poster abstract by {d12}. 250 words.",
            finds=(Work("Research poster abstract", 12, 4, via="mail", tag="Research"),),
        ),
        Letter(
            "Health Careers Advising <hcac@cornell.edu>",
            "Committee letter deadline",
            "Pre-med juniors: the intent-to-apply form is due {d18}.",
            bulk=True,
        ),
        Letter(
            "Cayuga Medical Center Volunteers <volunteer@cayugamed.org>",
            "Flu shot record needed",
            "Please upload your flu shot record by {d11} to keep volunteering.",
            finds=(Work("Upload flu shot record", 11, 0.25, via="mail", kind="Errand"),),
            unread=True,
        ),
        *BULK,
    ),  # fmt: skip
    events=(Event("Pre-health advising", 4, "15:00", "15:30", kind="Appointment", was=("14:00", "14:30")),),
    typed=(
        "MCAT practice /goal ~6h",
        "BIOMG 3300 reading ch 12 due {d1} 10am ~2h #biomg3300",
        "BIOMG 3300 reading ch 13 due {d3} 10am ~2h #biomg3300",
        "Gym every mon,wed,fri ~1h /habit",
        "Groceries every sun ~1h /errand",
    ),  # fmt: skip
    rules=("no work after 10pm", "at most 8 hours a day", "keep sunday mornings free", "no orgo after 9pm"),
    routines=meals(lunch=("11:00", "13:00"), dinner=("17:30", "20:00"), breakfast=("07:00", "08:30")),
    project=Project(
        "Presentation",
        "Research forum poster",
        12,
        due=19,
        made=-14,
        area="Research",
        waits_on=("Slides", "Research poster abstract"),
    ),  # fmt: skip
    notes=(
        "Two prelims a day apart next week: orgo prep (8 h) and biochem prep (7 h) each over several days, "
        "starting this week; nothing after 22:00; the Wednesday lab and the research afternoons untouched.",
    ),
)

RILEY = Student(
    key="riley",
    name="Riley",
    about="CS and Math double major in the worst week of the term: three prelims, a 3110 assignment and a TA job",
    load="overloaded",
    netid="rs958",
    sleep=("01:00", "08:30"),
    meetings=(
        *course("CS 3110", ("LEC 001", "TR", "10:10", "11:25"), ("DIS 203", "W", "14:30", "15:20")),
        *course("CS 4820", ("LEC 001", "MWF", "11:15", "12:05")),
        *course("CS 4780", ("LEC 001", "TR", "14:55", "16:10")),
        *course("MATH 4130", ("LEC 001", "MWF", "13:25", "14:15")),
        Meeting("CS 1110 TA section", "T", "12:20", "13:10", calendar="work", kind="Event", tag="TA"),
        Meeting("CS 1110 consulting hours", "U", "19:00", "21:00", calendar="work", kind="Event", tag="TA"),
    ),  # fmt: skip
    prelims=(
        Prelim("CS 3110 Prelim 1", -13, prep_hours=5, where="Statler Auditorium"),  # before today
        Prelim("CS 4820 Prelim 2", 1, prep_hours=6, where="Statler Auditorium"),
        Prelim("MATH 4130 Prelim 2", 3, prep_hours=6, where="Malott 251"),
        Prelim("CS 4780 Exam 2", 8, start="19:00", end="21:00", prep_hours=6, where="Bailey Hall"),
    ),  # fmt: skip
    work=(
        Work("CS 3110 A4: Search", 3, 18, raw="A4: Search [CS3110]", tag="CS 3110"),
        Work("CS 4820 Problem Set 7", 2, 8, via="homework", tag="CS 4820"),
        Work("CS 4780 project milestone 2", 4, 10, raw="Project Milestone 2 [CS4780]", tag="CS 4780"),
        Work("MATH 4130 HW 8", 4, 5, via="homework", tag="MATH 4130"),
        Work("CS 4820 Problem Set 8", 16, 8, via="homework", tag="CS 4820"),
        Work("CS 3110 A5: Bugs", 17, 15, raw="A5: Bugs [CS3110]", tag="CS 3110"),
        # Before this week: done in the weeks lived before today (sim/history.py).
        Work("CS 3110 A3: Interpreter", -11, 15, raw="A3: Interpreter [CS3110]", tag="CS 3110"),
        Work("CS 4820 Problem Set 6", -12, 8, via="homework", tag="CS 4820"),
        *each_week("CS 4780 homework {n}", 1, 4, range(-3, 0), first=5, raw="Homework {n} [CS4780]", tag="CS 4780"),
        *each_week("MATH 4130 HW {n}", 4, 5, range(-3, 0), first=8, via="homework", tag="MATH 4130"),
    ),  # fmt: skip
    letters=(
        Letter(
            "CS 1110 course staff <cs1110-staff@cornell.edu>",
            "A3 grading assignments",
            "Graders: please finish your A3 batch by {d5} at noon.",
            finds=(Work("CS 1110 A3 grading", 5, 6, via="mail", at="12:00", tag="TA"),),
        ),
        Letter(
            "CS 3110 <cs3110-staff@cornell.edu>",
            "[CS 3110] A4 is out",
            "A4 is due {d3} at 11:59pm. It is long; start now.",
            bulk=True,
        ),
        Letter(
            "CS 4780 <cs4780-staff@cornell.edu>",
            "Exam 2 practice problems",
            "Practice problems are posted. Work through them before {d7}.",
            finds=(Work("CS 4780 Exam 2 practice problems", 7, 3, via="mail", tag="CS 4780"),),
            unread=True,
        ),
        *BULK,
    ),  # fmt: skip
    events=(Event("TA meeting", 2, "17:00", "17:30", calendar="work", kind="Meeting", was=("16:30", "17:00")),),
    typed=("Email Prof. Hopcroft about the regrade 15m", "Laundry every sun ~1h /chore"),
    rules=("at most 10 hours a day", "keep sunday mornings free", "sleep before 1am"),
    routines=meals(lunch=("12:00", "14:30"), dinner=("18:00", "21:00")),
    project=Project("Essay", "CS 4780 project report", 14, due=24, made=-7, area="CS 4780"),
    notes=(
        "Impossible as asked: about 60 hours due in four days around three prelims. Friday should say so, plan "
        "the earliest things first (4820 prep before tonight, PS 7 by Wednesday), never cut into sleep or "
        "class, and show what will be late.",
    ),
)
