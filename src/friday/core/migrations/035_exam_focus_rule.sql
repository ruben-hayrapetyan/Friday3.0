-- Exam focus is a rule (14 Nov: "this kind of thing should always be a rule and shouldn't be stored in another way"):
-- a saved exam focus that's on becomes the rule "Focus on an exam's course N days before it" at the end of your
-- rules, with its days and exam words, and Friday's reading of it kept as for a rule you typed; one that's off goes.
-- Rules not saved yet are the built-in ones (core/settings.py REFERENCE_RULES as of this migration, kept in step by a
-- test), saved with it. The setting is removed either way.
CREATE TEMP TABLE focus AS
SELECT user_id,
       min(14, max(1, coalesce(json_extract(value, '$.days_before'), 3))) AS days,
       coalesce(json_extract(value, '$.words'), json('["exam", "prelim", "midterm", "final"]')) AS words
FROM settings
WHERE key = 'exam_focus' AND json_valid(value) AND json_extract(value, '$.on') = 1;

INSERT INTO settings (user_id, key, value, version, updated_utc)
SELECT f.user_id, 'rules', '[{"type": "late_work", "name": "late_work", "weight": 10.0, "stage": null, "scope": null, "reason": null, "params": {"overflow_extra_hours": 48}, "enabled": true}, {"type": "late_tasks", "name": "late_tasks", "weight": 10.0, "stage": null, "scope": null, "reason": null, "params": {"hours": 48, "square_hours": 96}, "enabled": true}, {"type": "quota", "name": "quota", "weight": 3.0, "stage": null, "scope": null, "reason": null, "params": {}, "enabled": true}, {"type": "late_night", "name": "late_night", "weight": 1.0, "stage": null, "scope": {"except_preset": ["Routine"]}, "reason": null, "params": {"gradient_start": "22:00", "a": 2, "b": 20, "debt_factor": 0.5}, "enabled": true}, {"type": "deep_run", "name": "deep_run", "weight": 4.0, "stage": null, "scope": {"energy": ["deep", "light"]}, "reason": null, "params": {"threshold": "3h"}, "enabled": true}, {"type": "reserve", "name": "weekday_evenings", "weight": 2.0, "stage": null, "scope": {"except_preset": ["Routine"]}, "reason": null, "params": {"days_except": ["sat", "sun"], "start": "18:00", "end": "23:00", "free": "2h"}, "enabled": true}, {"type": "reserve", "name": "weekends", "weight": 2.0, "stage": null, "scope": {"except_preset": ["Routine"]}, "reason": null, "params": {"days": ["sat", "sun"], "start": "10:00", "end": "23:00", "free": "4h"}, "enabled": true}, {"type": "daily_load", "name": "daily_load", "weight": 5.0, "stage": null, "scope": {"except_preset": ["Routine"]}, "reason": null, "params": {"threshold": "8h"}, "enabled": true}, {"type": "even_load", "name": "even_load", "weight": 1.0, "stage": "preferences", "scope": null, "reason": null, "params": {}, "enabled": true}, {"type": "energy", "name": "energy", "weight": 1.0, "stage": null, "scope": null, "reason": null, "params": {}, "enabled": true}, {"type": "soft_late", "name": "soft_late", "weight": 3.0, "stage": null, "scope": null, "reason": null, "params": {}, "enabled": true}, {"type": "unscheduled", "name": "unscheduled", "weight": 0.5, "stage": null, "scope": null, "reason": null, "params": {"base": 1}, "enabled": true}, {"type": "chunk_cost", "name": "chunk_cost", "weight": 10.0, "stage": null, "scope": null, "reason": null, "params": {}, "enabled": true}, {"type": "buffer", "name": "buffer", "weight": 3.0, "stage": null, "scope": null, "reason": null, "params": {"minutes": "0m", "by_area": {}, "by_preset": {}}, "enabled": true}, {"type": "same_course", "name": "same_course", "weight": 2.0, "stage": null, "scope": null, "reason": null, "params": {}, "enabled": true}, {"type": "target_shortfall", "name": "target_shortfall", "weight": 1.0, "stage": null, "scope": null, "reason": null, "params": {"curve": [[0.4, 8], [1.0, 3]]}, "enabled": true}, {"type": "elastic_shortfall", "name": "elastic_shortfall", "weight": 1.0, "stage": null, "scope": null, "reason": null, "params": {"steep": 20, "gentle": 2}, "enabled": true}, {"type": "elastic_shortfall", "name": "elastic_minimum", "weight": 1.0, "stage": "wellbeing", "scope": null, "reason": null, "params": {"steep": 20, "gentle": 0}, "enabled": true}, {"type": "open_value", "name": "open_value", "weight": 1.0, "stage": null, "scope": null, "reason": null, "params": {"curve": [[0.5, 1], [1.0, 0.5]]}, "enabled": true}, {"type": "finish_early", "name": "finish_early", "weight": 1.0, "stage": null, "scope": {"except_preset": ["Exam prep"]}, "reason": null, "params": {"days": 1}, "enabled": true}, {"type": "minimize_changes", "name": "minimize_changes", "weight": 1.0, "stage": "wellbeing", "scope": null, "reason": null, "params": {"preferred_multiplier": 10}, "enabled": true}]',
  (SELECT coalesce(max(version), 0) + 1 FROM settings AS v WHERE v.user_id = f.user_id), strftime('%Y-%m-%dT%H:%MZ', 'now')
FROM focus AS f
WHERE NOT EXISTS (SELECT 1 FROM settings AS s WHERE s.user_id = f.user_id AND s.key = 'rules');

UPDATE settings SET version = version + 1, value = json_insert(
  (SELECT json_group_array(json(r.value))
   FROM (SELECT key, value FROM json_each(settings.value) ORDER BY key) AS r
   WHERE json_extract(r.value, '$.type') IS NOT 'exam_focus'),
  '$[#]',
  json_object('type', 'exam_focus', 'name', 'you:exam-focus', 'weight', 0.0, 'stage', NULL, 'scope', NULL,
              'reason', CASE WHEN f.days = 1 THEN 'Focus on an exam''s course the day before it'
                             ELSE 'Focus on an exam''s course ' || f.days || ' days before it' END,
              'params', json_object('days_before', f.days, 'words', json(f.words)), 'enabled', json('true'))
)
FROM focus AS f
WHERE settings.key = 'rules' AND settings.user_id = f.user_id AND json_valid(settings.value);

INSERT INTO kv (user_id, key, value)
SELECT user_id, 'rule_readings', '{}' FROM focus AS f
WHERE NOT EXISTS (SELECT 1 FROM kv WHERE kv.user_id = f.user_id AND kv.key = 'rule_readings');

UPDATE kv SET value = json_set(value, '$."you:exam-focus"', json_object(
  'reading', json_object('kind', 'exam_focus', 'subject', 'work', 'rel', NULL, 'at', NULL, 'until', NULL,
                         'days', NULL, 'amount', f.days * 1.0, 'event', NULL, 'paces', NULL, 'events', NULL,
                         'before_min', NULL, 'after_min', NULL),
  'strength', 'Always',
  'text', CASE WHEN f.days = 1 THEN 'Focus on an exam''s course the day before it'
               ELSE 'Focus on an exam''s course ' || f.days || ' days before it' END))
FROM focus AS f
WHERE kv.key = 'rule_readings' AND kv.user_id = f.user_id AND json_valid(kv.value);

DELETE FROM settings WHERE key = 'exam_focus';
DROP TABLE focus;
