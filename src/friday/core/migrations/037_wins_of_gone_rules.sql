-- Your answers to "Which should win?" go when one of their two rules does (15 Nov: a client's Rules page said "Wins
-- over 'spread'", a built-in rule migration 034 took out, and rule_remove kept the answers of rules you delete). Each
-- remembered pair whose winner or loser isn't among your rules goes: your saved rules, or the built-in ones when you
-- never changed them (core/settings.py REFERENCE_RULES, as of this migration). The others stay, in their order.
CREATE TEMP TABLE built_in (name TEXT PRIMARY KEY);
INSERT INTO built_in (name) VALUES
  ('late_work'), ('late_tasks'), ('quota'), ('late_night'), ('deep_run'), ('weekday_evenings'), ('weekends'),
  ('daily_load'), ('even_load'), ('energy'), ('soft_late'), ('unscheduled'), ('chunk_cost'), ('buffer'),
  ('exam_prep_spread'), ('same_course'), ('target_shortfall'), ('elastic_shortfall'), ('elastic_minimum'),
  ('open_value'), ('finish_early'), ('minimize_changes');

CREATE TEMP TABLE rule_names AS
SELECT k.user_id, json_extract(r.value, '$.name') AS name
FROM kv AS k JOIN settings AS s ON s.user_id = k.user_id AND s.key = 'rules', json_each(s.value) AS r
WHERE k.key = 'rule_wins' AND json_valid(s.value) AND json_type(s.value) = 'array'
UNION
SELECT k.user_id, b.name
FROM kv AS k, built_in AS b
WHERE k.key = 'rule_wins'
  AND NOT EXISTS (SELECT 1 FROM settings AS s WHERE s.user_id = k.user_id AND s.key = 'rules');

UPDATE kv SET value = (
  SELECT json_group_array(json(w.value))
  FROM (SELECT key, value FROM json_each(kv.value) ORDER BY key) AS w
  WHERE json_extract(w.value, '$.winner') IN (SELECT name FROM rule_names AS n WHERE n.user_id = kv.user_id)
    AND json_extract(w.value, '$.loser') IN (SELECT name FROM rule_names AS n WHERE n.user_id = kv.user_id)
)
WHERE key = 'rule_wins' AND json_valid(value) AND json_type(value) = 'array'
  AND EXISTS (SELECT 1 FROM json_each(kv.value) AS w
              WHERE json_extract(w.value, '$.winner') NOT IN (SELECT name FROM rule_names AS n WHERE n.user_id = kv.user_id)
                 OR json_extract(w.value, '$.loser') NOT IN (SELECT name FROM rule_names AS n WHERE n.user_id = kv.user_id));

DROP TABLE rule_names;
DROP TABLE built_in;
