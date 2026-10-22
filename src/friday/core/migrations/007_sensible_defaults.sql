-- Rules kept from the old defaults get the new ones (M15, from planning seven students' weeks): spreading work
-- evenly is a preference, so it no longer cuts a reading into scraps to hold every day at 3 hours; no more than
-- 3 hours in a row of reading as well as deep work; and work finishes a day before it's due (exam prep excepted).
UPDATE settings SET version = version + 1, value = (
  SELECT json_group_array(json(rule)) FROM (
    SELECT CASE
      WHEN json_extract(value, '$.name') = 'even_load' AND json_extract(value, '$.stage') IS NULL
        THEN json_set(value, '$.stage', 'preferences')
      WHEN json_extract(value, '$.name') = 'deep_run' AND json_extract(value, '$.scope') IS NULL
        THEN json_set(value, '$.scope', json('{"energy": ["deep", "light"]}'))
      ELSE value END AS rule
    FROM json_each(settings.value) ORDER BY key
  )
)
WHERE key = 'rules';

UPDATE settings SET value = json_insert(value, '$[#]', json(
  '{"type": "finish_early", "name": "finish_early", "weight": 1, "stage": null, "scope": {"except_preset": ["Exam prep"]}, "reason": null, "params": {"days": 1}, "enabled": true}'
))
WHERE key = 'rules'
  AND NOT EXISTS (SELECT 1 FROM json_each(settings.value) WHERE json_extract(value, '$.name') = 'finish_early');

-- Mail kept on the old keywords gets the new ones: prelims, homework and forms were skipped.
UPDATE settings SET version = version + 1, value = json_set(value, '$.keywords', json(
  '["due", "deadline", "exam", "quiz", "assignment", "submit", "meeting", "invite", "reschedule", "cancelled", "prelim", "midterm", "homework", "problem set", "lab report", "rsvp", "form", "application"]'
))
WHERE key = 'gmail'
  AND json_extract(value, '$.keywords') = json('["due", "deadline", "exam", "quiz", "assignment", "submit", "meeting", "invite", "reschedule", "cancelled"]');

-- Calendars are read again, now as far ahead as the allocator plans (12 weeks, not 2).
UPDATE sources SET last_sync_utc = NULL WHERE kind = 'gcal';

-- The plan ahead is made again with the new rules; keeping it (minimize_changes) would keep the old layout.
DELETE FROM blocks WHERE end_utc > strftime('%Y-%m-%dT%H:%MZ', 'now')
  AND plan_id IN (SELECT id FROM plans WHERE status = 'current');
