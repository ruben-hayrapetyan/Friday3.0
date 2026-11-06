# Browser QA pass

`tests/scenarios/test_sample_term.py` covers the same flows through the command registry on every
`scripts/check.sh`. This pass checks what those tests can't see: what the pages show and how they behave. Run it
after any change to the web app or to how inputs are read, and record what you find in PROGRESS.md.

## Setup

```sh
pnpm --dir web build
uv run fridayd --data-dir /tmp/friday-demo demo --port 8799   # a fresh folder each time: rm -rf it first
```

Open http://localhost:8799. The demo is a made-up student's term (`src/friday/sim/sample.py`) with stand-in Google,
Gmail and AI; it never reads your friday.toml, secrets or data. After a rebuild, unregister the service worker (or
hard-reload) or the old build is served. The app is desktop only, with a 1100 px minimum width.

## Checklist

**Every page**
- [ ] The sidebar says "Demo: made-up sample data".

**Settings**
- [ ] "Test the AI" in Integrations lists both models (mail and sorting) as working.
- [ ] Opening Settings from the gear goes to the section used last, highlighted.

**Settings → Integrations**
- [ ] "Calendars" is folded to one line saying how many are read; opened, every calendar is listed, alphabetized,
      with only "1. Projects" (the primary one) switched on.
- [ ] "Read events as" is the app's dropdown: "Per event" and the kinds by name; it closes on a pick, Escape or a
      click elsewhere.
- [ ] Switching on 4. School, 3. Personal, 5. Homework and the Canvas calendar: rows keep their height, names
      aren't cut short, and their events reach the Inbox within a minute without "Sync now".
- [ ] 5. Homework read as "Assignment": its all-day entries arrive as assignments due 23:59, titles without
      "Due".
- [ ] Gmail has its own "Sync now"; "Recent mail" shows 7 read and 5 skipped; every skipped one says why on its
      own line; "Read it anyway" on "Lunch?" reads it on the next sync. Words and "Always read mail from" are
      editable and save when you leave the field.

**Inbox**
- [ ] No repeating event is in the Inbox; a line at the top says how many wait in Repeating and links there.
- [ ] Kinds: lectures, labs, discussions and seminars are classes; the CHEM prelim is an Exam with "Prep: CHEM
      Prelim 2" due at its start; the dentist is an Appointment; Canvas titles are plain ("PHYS 1110 Light Intensity
      Lab"); "Prep: MATH Quiz 2" is due the evening before the all-day quiz; Canvas items
      are due at their time; the Expo is an Event; the declined club social, career fair and holiday are absent.
- [ ] Mail suggestions show the quoted words highlighted in the email.
- [ ] Accept all of a source; Undo brings the rows back.

**Settings → Repeating**
- [ ] The Google card lists each repeating event once: "Every Mon, Wed and Fri, 12:20–13:10 · 4. School", a tag,
      a kind (fixed kinds for events, others for due work) and how many times; unticking one leaves it waiting.
- [ ] Importing with a tag: the repeats appear under "From your calendars and feeds" with the tag's colour and their
      times; Undo takes them back out. "Not now" hides the card until another repeating event turns up.
- [ ] Switching an imported repeat off removes its future occurrences and keeps it in the list with its times;
      on again, they return within a minute, as one series.
- [ ] "CHEM Reading Response" (5. Homework as Assignment), imported, is one row in To-do at its next due.
- [ ] "Sam's Birthday" (3. Personal; switch on all-day events in Integrations first) reads "Yearly, all day", not
      weekly; switching all-day events on brings it in within a minute.

**Meals**
- [ ] With meal tracking on, a day with its dinner logged has "Another…" → "+ Second dinner"; logging it shows
      "Second dinner" in the row and on the calendar, and the Now bar offers "Another dinner" after a meal today.

**Plan**
- [ ] Classes sit at their real times all week, the moved CHEM lecture next Wednesday at 14:00, no MATH lecture
      next Friday; exam prep is planned before each exam.
- [ ] An unknown address (`#/plan`) lands on the plan.
- [ ] Buttons you press again and again stay put (5 Nov): ‹ and › ten times in Day, 3 days, Week and Month, then
      −/+ on a to-do's length and +30m on a block's estimate several times; none moves as the text beside it
      changes (measure `getBoundingClientRect().left` before and after).
- [ ] Accept the whole Inbox, then read the week as a student would: each assignment of 3 hours or less in one
      sitting (none cut into half-hours), all before its due, none in class, after bedtime or in the hour after
      waking; exam prep before its exam.
- [ ] All-day events (the birthday, Halloween) are chips at the top of their day, not column-high blocks.
- [ ] With nothing on, the dock names the day when the next block isn't today ("Free until Thu 15:00").

**Settings → Tags/Kinds**
- [ ] Assignment, Exam prep, Class and Event have no delete button; the others do.
- [ ] Deleting Errand asks where its items go; suggestions waiting in the Inbox move too and still accept.
- [ ] "Add kind" makes a copy of the kind picked.

**Now bar and timer (M16)**
- [ ] At a minute that isn't a quarter hour (08:07), inside a planned block, the bar shows that block with its real
      start and end and a Start button. In a class it shows the class, no buttons. Free, it says until when, how
      long and what's next, a class included, with up to three Start buttons showing each task's own length.
- [ ] Start: the counter ticks every second from 0:00; the calendar draws the session under the now line; no
      dashed ghosts appear and no block moves or splits (the plan generation in Status is unchanged). Pause after
      20 seconds says "too short to count"; after 2 minutes it says "2 min" and the To-do row's done time grows.
- [ ] Start something 20 minutes before a class: the bar shows it with "left" until the class; the plan is whole.
- [ ] Day headers: at most two deadline chips a day on one line, titles cut with an ellipsis, "+N" shows the rest.

**Deleting from the calendar (M16)**
- [ ] Every block's popover has Delete, and Delete or Backspace on a selected block does the same. A work block, a
      fixed event and a due marker each leave the calendar at once (before "Replanning…" ends), with Undo.
- [ ] A repeating block asks "Just this one / Every one" (also from the key); Just this one leaves the others.

**Settings → About you, repeats, lengths (M16)**
- [ ] Add a note; it lists at once and an example fills the box. Reject an inbox suggestion: "Why not?" appears,
      and Remember adds the note there.
- [ ] A repeating to-do's Delete asks "Just this one / Every one"; Every one empties it from To-do and Repeating.
      Settings → Repeating has a trash per repeat you made; an imported one has only its switch.
- [ ] Length in the to-do detail and the Inbox's Edit takes "5m", "45", "1h30", "1.5h"; under 15 minutes says it
      takes a 15-minute slot.
- [ ] Insights' comparison shows the day's classes in grey in both versions.
- [ ] Other ways (on a busy profile, `--case grace --ready`): each slot counts its seconds with a bar and the
      first card shows before the second; past 8 s it says you can close it; closed, a toast "Two other ways … are
      ready" with See them; opened again within ten minutes the ways show at once; Stop leaves "Stopped."

**Rules**
- [ ] Every rule but "Deadlines come first" and "Keep pace with long work" can be deleted, and leaves the list at
      once; Undo brings it back.

## Cornell students

Seven students (`src/friday/sim/students.py`, `students_heavy.py`) from very light to impossible, for trying the
app on a realistic week. Each has lunch and dinner (some breakfast) as routines in a window, habits and chores, 2–5
rules in their own words, unread mail and a moved appointment. `--ready` has them three weeks into using Friday
(`sim/history.py`): work done and timed, days reviewed, comparisons answered, a project from a template.
`tests/scenarios/test_cornell.py` judges their plans and `test_cornell_lived.py` the three weeks; this pass is for
what a person sees.

```sh
python -m friday.sim.agenda all                           # every student's week and meals as text (PYTHONPATH=src:.)
uv run fridayd demo --case jordan --port 8802             # fresh: set it up yourself, as on the first evening
uv run fridayd demo --case priya --ready --port 8801      # three weeks in (the first start lives them: ~1 min)
```

Cases: `maya` (very light), `alex` (light), `jordan` and `elena` (moderate), `priya` and `daniel` (heavy), `riley`
(overloaded). Each run uses its own folder (`friday-demo-<case>[-lived]` next to your data); delete it to start again
(and after pulling changes to the students).

**Fresh (jordan)**
- [ ] Settings opens on Integrations; switching on every calendar fills the Inbox within a minute: problem sets,
      the A5 and both prelims with their prep, nothing already past due; Repeating lists the classes once each.
- [ ] Repeating suggests each class's course code as its tag ("CS 2110"), new until imported; after importing,
      accepting "MATH 2940 HW 8" puts it under MATH 2940 without picking a tag.
- [ ] Each Inbox suggestion for work shows its length ("Friday's guess" until set); Edit takes hours and a date
      picker.

**Three weeks in (jordan, daniel, elena, then any)**
- [ ] Review opens on yesterday: its blocks to settle (done, partly, not done); earlier days show as reviewed, with
      timer sessions and logged time.
- [ ] Insights: about 40–60 things done over the weeks; assignments take ~1.3× what was planned, Elena's readings
      ~0.7×, exam prep from the first prelims; when you work has a best two hours; what Friday learned shows the
      answered comparisons and a suggestion; a comparison question waits for Daniel and Priya.
- [ ] Weekly review of last week: planned against done by tag, what finished, what carried over, how it felt.
- [ ] Inbox: three left — unread mail with a deadline (Jordan's prelim conflict form), a moved appointment as a
      change ("Info session: Jane Street", an hour later), and a likely duplicate of something typed in already.
- [ ] Projects: Jordan's sponsor pitch (Research done, Slides waits on the sponsor emails), Elena's and Priya's
      essays with the outline done, Daniel's poster (its Slides wait on the abstract), Riley's report.
- [ ] Rules: each student's own 2–5 rules on top, in their words; one reads wrong (Maya's "no studying on sundays
      pls" matches nothing, Jordan's "groceries on sunday afternoons" loses the afternoons).
- [ ] To-do: a skipped habit each Friday and one dropped assignment show in their filters.
- [ ] Lunch and dinner every day inside their windows (known to fail: whole meals are dropped, Priya and Riley get
      almost none; `test_meals_…` is marked xfail with the reason).

**Ready (priya, riley, maya)**
- [ ] Priya: a notice says ENGRD 2700 Lecture and ECE 3150 Lab overlap on Thursday; every lab report, HW and
      problem set is before its due, in sittings of an hour or more (a 45-minute piece or two in a full week);
      ECE 3150 prep over several days.
- [ ] Riley: "N things will be late · See options" at the top opens the options; late work sits in real sittings,
      not alternating half hours; tonight's 4820 prep and Wednesday's PS 7 are on time.
- [ ] Maya: a near-empty week; the novel an hour a day, not every afternoon; nothing on Friday evening; Laundry has
      no red deadline flag and its row reads "Due Sun, end of day".
- [ ] Rules: the rules you'd tune on top, "How Friday fills in the rest (10)" folded below.
- [ ] To-do rows show each length once; a block's popover says "it could all start N days later and still be on
      time" and closes when you change pages.

