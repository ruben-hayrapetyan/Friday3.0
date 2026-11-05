"""What sim/people.py draws its people from: names, courses, jobs, families' weeks, the things people type into
quick-add and the rules they write. All made up; `{dN}` is a date as in sim/cornell.py, `{area}` the person's main
tag. Every rule sentence here is one Friday's grammar reads (tests/scenarios/test_people.py sets each person up).
"""

FIRST = (
    "Ava", "Ben", "Chloe", "Dev", "Esme", "Felix", "Grace", "Hugo", "Iris", "Jonah", "Kira", "Leo", "Mila", "Nate",
    "Omar", "Pia", "Quinn", "Rosa", "Sami", "Tara", "Uma", "Vince", "Wren", "Xavi", "Yara", "Zane", "Ana", "Bruno",
    "Cora", "Dmitri", "Elif", "Farah", "Gus", "Hana", "Ivo", "June", "Kai", "Lena", "Marco", "Nia", "Owen", "Priya",
    "Rafa", "Sofia", "Theo", "Vera", "Will", "Zoe",
)  # fmt: skip
LAST = (
    "Abara", "Berg", "Castillo", "Duarte", "Engel", "Fischer", "Gallo", "Haddad", "Ito", "Jensen", "Kowalski",
    "Laine", "Moreau", "Novak", "Okafor", "Petrov", "Quist", "Rossi", "Sato", "Tan", "Ueda", "Vance", "Walsh", "Yilmaz",
)  # fmt: skip

# (code, what it is): a made-up university's courses.
COURSES = (
    ("BIO 1500", "Biology"), ("CHEM 2080", "Organic chemistry"), ("CS 2100", "Data structures"),
    ("CS 3400", "Operating systems"), ("ECON 1110", "Microeconomics"), ("ECON 3020", "Econometrics"),
    ("HIST 2240", "Modern Europe"), ("MATH 2210", "Linear algebra"), ("MATH 1920", "Multivariable calculus"),
    ("PHYS 2213", "Electricity and magnetism"), ("PSYC 1101", "Intro psychology"), ("ENGL 2030", "The novel"),
    ("STAT 2040", "Probability"), ("ARCH 1101", "Design studio"), ("SPAN 2090", "Spanish"), ("PHIL 1440", "Ethics"),
)  # fmt: skip
MWF_SLOTS = (("09:05", "09:55"), ("10:10", "11:00"), ("11:15", "12:05"), ("13:25", "14:15"), ("14:30", "15:20"))
TR_SLOTS = (("08:40", "09:55"), ("10:10", "11:25"), ("13:00", "14:15"), ("14:45", "16:00"))
SECTION_SLOTS = (("M", "16:15", "17:05"), ("T", "16:30", "17:20"), ("W", "16:15", "17:05"), ("R", "16:30", "17:20"),
                 ("F", "15:35", "16:25"))  # fmt: skip
WEEKLY_WORK = (("Problem Set", "Assignment", 3), ("Reading", "Reading", 1.5), ("Lab Report", "Assignment", 2.5),
               ("Response", "Assignment", 1))  # fmt: skip

JOBS = (
    ("Product designer", "Northwind"), ("Data analyst", "Lumen Health"), ("Software engineer", "Brightline"),
    ("Marketing manager", "Fernway"), ("Accountant", "Oakridge & Co"), ("Teacher", "Riverside Middle School"),
    ("Project manager", "Halcyon Build"), ("Recruiter", "Tallis"), ("Paralegal", "Moss & Dunn"),
    ("Research scientist", "Cobalt Labs"), ("Grant writer", "Open Field Trust"), ("Sales lead", "Quarry Supply"),
)  # fmt: skip
JOB_TASKS = (
    ("Quarterly report", 4), ("Budget draft", 3), ("Slide deck for the client", 3), ("Code review backlog", 2),
    ("Write the spec", 5), ("Performance reviews", 4), ("Hiring loop feedback", 1.5), ("Board memo", 2.5),
    ("Grade the quizzes", 2), ("Update the roadmap", 2), ("Expense report", 1), ("Vendor contract review", 3),
)  # fmt: skip

SHIFT_JOBS = (
    ("Nurse", "St. Anne's Hospital", ("07:00", "15:00")), ("Barista", "Fern Café", ("06:00", "14:00")),
    ("Line cook", "The Copper Pot", ("14:00", "22:00")), ("Pharmacy tech", "Main St Pharmacy", ("09:00", "17:00")),
    ("Warehouse lead", "Quarry Supply", ("14:00", "22:00")), ("Front desk", "Harbor Inn", ("08:00", "16:00")),
)  # fmt: skip
FREELANCE = (
    ("Illustrator", ("Book cover sketches", 6), ("Invoice the studio", 0.5)),
    ("Web developer", ("Client site launch", 8), ("Bug fixes for the shop", 3)),
    ("Translator", ("Contract translation", 5), ("Proofread the brochure", 2)),
    ("Photographer", ("Edit the wedding photos", 7), ("Send the gallery", 1)),
    ("Copywriter", ("Landing page copy", 3), ("Newsletter draft", 2)),
)  # fmt: skip
CLIENTS = ("Alder Studio", "Beacon Press", "Cinder Coffee", "Delta Dental", "Elm & Oak", "Foxglove Books")

KIDS = ("Maya", "Sam", "Lily", "Noah", "Ella", "Theo", "Ruby", "Max")
KID_ACTIVITIES = (("Soccer practice", "TR", "17:00", "18:15"), ("Swim lessons", "W", "16:30", "17:15"),
                  ("Piano lesson", "M", "16:00", "16:45"), ("Scouts", "R", "18:30", "19:30"),
                  ("Dance class", "T", "17:30", "18:30"), ("Art club", "F", "15:45", "16:45"))  # fmt: skip
PARENT_TASKS = (
    ("Permission slip for the field trip", 0.25, "Errand"), ("Fill in the camp forms", 1, "Errand"),
    ("Pay the water bill", 0.25, "Errand"), ("Book the car service", 0.5, "Errand"),
    ("Plan the birthday party", 3, "Project"), ("Sort out the insurance claim", 1.5, "Errand"),
    ("Tax documents for the accountant", 2, "Errand"), ("Sew the costume", 2.5, "Chore"),
)  # fmt: skip
CARE = (("Mum's physio", "T", "10:00", "11:00"), ("Visit Dad", "U", "14:00", "16:00"),
        ("Grandma's shopping", "S", "10:00", "11:30"))  # fmt: skip

APPOINTMENTS = (
    ("Dentist", "Appointment", 45), ("Haircut", "Appointment", 45), ("Doctor's appointment", "Appointment", 30),
    ("Car service drop-off", "Appointment", 30), ("Parent-teacher conference", "Appointment", 30),
    ("Coffee with Jo", "Event", 60), ("Book club", "Event", 90), ("Concert", "Event", 150),
    ("Vet appointment", "Appointment", 30), ("Bank appointment", "Appointment", 45),
)  # fmt: skip
ALL_DAY = ("Mum's birthday", "Wedding anniversary", "Dad's birthday", "Office closed", "School holiday",
           "Friend's wedding")  # fmt: skip

TYPED = {
    "any": (
        "Laundry every sun ~1h /chore", "Groceries every sat ~1h /errand", "Gym every mon,wed,fri ~1h /habit",
        "Read a novel open", "Call home sun 7pm 30m", "Return library books due {d4} 30m",
        "run 3x a week ~45m /habit", "Clean the kitchen every thu ~45m /chore", "Renew passport due {d12} 1h /errand",
        "yoga every tue thu ~1h /habit", "Meal prep every sun ~1.5h /chore", "Learn Spanish open",
    ),
    "student": ("Email my advisor 15m", "Print the poster due {d6} 30m /errand", "Study group notes ~1h"),
    "worker": ("Update my CV ~2h", "Book flights for the conference due {d9} 30m /errand", "Expense receipts 30m"),
    "parent": ("School lunches every sun ~1h /chore", "Buy a present for the party due {d5} 1h /errand",
               "Book the babysitter 15m /errand"),  # fmt: skip
    "shift": ("Renew my certification due {d16} ~3h", "Swap shift with Lee 15m", "Portfolio update ~2h"),
}  # fmt: skip
RULES = {
    "any": (
        "keep sunday mornings free", "at most 8 hours a day", "no work after 10pm", "keep saturday afternoons free",
        "no errands on sundays", "errands in the afternoon", "chores on sundays", "keep weekday evenings free",
        "deep work in the morning", "no work before 9am", "keep friday evenings free", "no work after 9pm",
    ),
    "student": ("no assignments after 10pm", "finish assignments 1 day before they're due", "reading in the evening"),
    "worker": ("no work on weekends", "keep weekends free", "at most 4 hours a day on weekdays"),
    "parent": ("no errands before 5pm", "no chores after 8pm", "keep sunday free"),
    "shift": ("at most 4 hours a day", "no work after 7pm on fridays", "errands on saturday mornings"),
}  # fmt: skip
