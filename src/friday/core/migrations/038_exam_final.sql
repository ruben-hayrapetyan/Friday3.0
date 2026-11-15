-- "Final" is an exam ("math final", "MATH 1920 Final"), except a final project, paper, draft, presentation, round or
-- review, or a name ("Final Fantasy movie night") (15 Nov, the user: "final, with exceptions"; the starter pattern
-- knew only "finals" and "final exam"). The Exam category's pattern changes where it's still the starter one exactly
-- (migration 028, core/calendars.py STARTER_CATEGORIES); a pattern you edited stays as you wrote it.
UPDATE settings SET version = version + 1, value = json_set(value, '$.categories', (
  SELECT json_group_array(json(CASE WHEN json_extract(c.value, '$.pattern') = '\b(exams?|prelims?|midterms?|quiz(?:zes)?|final exams?|finals|deadline|due)\b'
                                    THEN json_set(c.value, '$.pattern', '\b(exams?|prelims?|midterms?|quiz(?:zes)?|finals?(?!\s+(?:(?:project|paper|draft|presentation|round|review)s?\b|(?-i:(?!Exam)[A-Z][a-z])))|deadline|due)\b')
                                    ELSE c.value END))
  FROM (SELECT key, value FROM json_each(json_extract(settings.value, '$.categories')) ORDER BY key) AS c
))
WHERE key = 'categories' AND json_valid(value) AND json_type(value, '$.categories') = 'array'
  AND EXISTS (SELECT 1 FROM json_each(json_extract(settings.value, '$.categories')) AS c
              WHERE json_extract(c.value, '$.pattern') = '\b(exams?|prelims?|midterms?|quiz(?:zes)?|final exams?|finals|deadline|due)\b');
