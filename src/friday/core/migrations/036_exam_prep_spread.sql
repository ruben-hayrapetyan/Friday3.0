-- Exam prep is spread over the days before its exam again (14 Nov: "bring spread back in but its just very confusing
-- when you tell users about spread as a backend feature"), as a built-in rule said as what it does: "Exam prep is
-- spread over the days before the exam, not crammed into one". Saved rules get it where the old built-in "spread"
-- stood, right after the breathing-room rule (at the end when that one's gone), once. It's off for anyone whose last
-- logged rules from before migration 034 had the old one off. Rules not saved get it from the defaults.
CREATE TEMP TABLE was_off AS
SELECT c.user_id
FROM command_log AS c, json_each(c.undo) AS ch, json_each(json_extract(ch.value, '$.after.value')) AS r
WHERE json_valid(c.undo) AND json_extract(ch.value, '$.table') = 'settings'
  AND json_extract(ch.value, '$.key.key') = 'rules' AND json_valid(json_extract(ch.value, '$.after.value'))
  AND json_extract(r.value, '$.name') = 'spread' AND json_extract(r.value, '$.type') = 'spread'
  AND json_extract(r.value, '$.enabled') = 0
  AND c.id = (
    SELECT max(c2.id) FROM command_log AS c2, json_each(c2.undo) AS ch2,
                           json_each(json_extract(ch2.value, '$.after.value')) AS r2
    WHERE c2.user_id = c.user_id AND json_valid(c2.undo) AND json_extract(ch2.value, '$.table') = 'settings'
      AND json_extract(ch2.value, '$.key.key') = 'rules' AND json_valid(json_extract(ch2.value, '$.after.value'))
      AND json_extract(r2.value, '$.name') = 'spread' AND json_extract(r2.value, '$.type') = 'spread'
  );

UPDATE settings SET version = version + 1, value = (
  SELECT json_group_array(json(x.value)) FROM (
    SELECT r.key * 2 AS at, r.value FROM json_each(settings.value) AS r
    UNION ALL
    SELECT coalesce((SELECT b.key * 2 + 1 FROM json_each(settings.value) AS b
                     WHERE json_extract(b.value, '$.name') = 'buffer'), 1000000),
           json_object('type', 'spread', 'name', 'exam_prep_spread', 'weight', 3.0, 'stage', NULL,
                       'scope', json('{"preset": ["Exam prep"]}'), 'reason', NULL, 'params', json('{}'),
                       'enabled', json(CASE WHEN settings.user_id IN (SELECT user_id FROM was_off)
                                            THEN 'false' ELSE 'true' END))
    ORDER BY at
  ) AS x
)
WHERE key = 'rules' AND json_valid(value) AND json_type(value) = 'array'
  AND NOT EXISTS (SELECT 1 FROM json_each(settings.value) AS r WHERE json_extract(r.value, '$.name') = 'exam_prep_spread');

DROP TABLE was_off;
