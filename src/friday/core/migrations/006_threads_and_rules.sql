-- Mail is read a thread at a time: its newest message quotes the rest, and earlier ones aren't read again.
ALTER TABLE raw_inputs ADD COLUMN thread_id TEXT;

-- Calendar events still waiting for you are read again: a repeating one gets its own rule (a yearly birthday was
-- shown as weekly), and the small model sorts the rest with the kinds described more clearly (a proposal is an
-- Assignment, not a 10-hour Project).
UPDATE raw_inputs SET content_hash = ''
WHERE id IN (SELECT raw_input_id FROM suggestions WHERE status = 'pending')
  AND source_id IN (SELECT id FROM sources WHERE kind = 'gcal');
UPDATE sources SET last_sync_utc = NULL WHERE kind = 'gcal';

-- Suggestions already past due when they were read (an assignment due last week) are withdrawn.
UPDATE suggestions SET status = 'superseded'
WHERE status = 'pending' AND command = 'add'
  AND coalesce(json_extract(input, '$.due'), json_extract(input, '$.end')) < strftime('%Y-%m-%dT%H:%M', 'now', 'localtime');

-- The plan ahead is made again from scratch: even_load cut work into half-hour pieces, and keeping the plan
-- (minimize_changes) would have kept them. Past blocks stay, as the record of what was planned.
DELETE FROM blocks WHERE end_utc > strftime('%Y-%m-%dT%H:%MZ', 'now')
  AND plan_id IN (SELECT id FROM plans WHERE status = 'current');

-- Suggestions that failed when accepted: a meeting with no time is a to-do to arrange it, and deadline work with no
-- due date is soft.
UPDATE suggestions SET input = json_set(json_remove(input, '$.end', '$.blocks_time'), '$.preset', 'Errand')
WHERE status = 'pending' AND command = 'add' AND json_extract(input, '$.start') IS NULL
  AND json_extract(input, '$.preset') IN ('Class', 'Exam', 'Meeting', 'Appointment', 'Event');
UPDATE suggestions SET input = json_set(input, '$.firmness', 'none')
WHERE status = 'pending' AND command = 'add' AND json_extract(input, '$.due') IS NULL
  AND json_extract(input, '$.firmness') IS NULL
  AND json_extract(input, '$.preset') IN ('Assignment', 'Project', 'Exam prep');
