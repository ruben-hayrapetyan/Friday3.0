-- No categories, and every event was grey (8 Nov, from users). Anyone whose list is empty gets the starter set
-- (core/calendars.py STARTER_CATEGORIES), once: deleting them all afterwards keeps none. Kept in step with it.
UPDATE settings SET version = version + 1, value = json_set(value, '$.categories', json('[
  {"name": "Exam", "slug": "exam", "color": "red", "pattern": "\\b(exam|prelim|midterm|quiz|final|deadline|due)\\b", "note": null},
  {"name": "Class", "slug": "class", "color": "sapgreen", "pattern": "\\b(lecture|lec|class|seminar|discussion|disc|recitation|lab|section|tutorial)\\b|\\b[a-z]{2,5} ?\\d{4}\\b", "note": null},
  {"name": "Exercise", "slug": "exercise", "color": "orange", "pattern": "\\b(gym|workout|work out|run|running|yoga|swim|swimming|lift|lifting|practice|training|hike|climbing|tennis|soccer|basketball|pilates|spin)\\b", "note": null},
  {"name": "Work", "slug": "work", "color": "purple", "pattern": "\\b(shift|work|job|internship)\\b", "note": null},
  {"name": "Meeting", "slug": "meeting", "color": "blue", "pattern": "\\b(meeting|meet with|one-on-one|1:1|sync|standup|stand-up|interview|call with|office hours|advising|appointment|appt|doctor|dentist|therapy|check-?up|haircut)\\b", "note": null},
  {"name": "Travel", "slug": "travel", "color": "violet", "pattern": "\\b(flight|fly|train|bus|drive to|travel|trip|airport|depart|departure)\\b", "note": null},
  {"name": "Social", "slug": "social", "color": "pink", "pattern": "\\b(birthday|bday|party|dinner with|lunch with|coffee with|hangout|hang out|drinks|game night|movie|concert|wedding|date night)\\b", "note": null}
]'))
WHERE key = 'categories' AND json_array_length(COALESCE(json_extract(value, '$.categories'), '[]')) = 0;
