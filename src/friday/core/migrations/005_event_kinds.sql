-- "Commitment" meant nothing; fixed-time things are an Event, or one of the new Exam, Meeting and Appointment.

UPDATE items SET preset = 'Event' WHERE preset = 'Commitment';
UPDATE series SET template = json_set(template, '$.preset', 'Event')
WHERE json_extract(template, '$.preset') = 'Commitment';
UPDATE suggestions SET input = json_set(input, '$.preset', 'Event')
WHERE json_extract(input, '$.preset') = 'Commitment';
UPDATE sources SET config = json_set(config, '$.kind', 'Event') WHERE json_extract(config, '$.kind') = 'Commitment';

-- Kinds you changed are stored whole: Commitment becomes Event there, and the new kinds join it.
UPDATE settings SET value = replace(value, '"Commitment"', '"Event"') WHERE key IN ('presets', 'kind_order', 'rules');
UPDATE settings SET value = json_set(value,
    '$.Exam', json(coalesce(json_extract(value, '$.Exam'), '{"when": "fixed", "event_kind": "exam"}')),
    '$.Meeting', json(coalesce(json_extract(value, '$.Meeting'), '{"when": "fixed", "event_kind": "meeting"}')),
    '$.Appointment', json(coalesce(json_extract(value, '$.Appointment'), '{"when": "fixed", "event_kind": "other"}')))
WHERE key = 'presets';

-- Calendar events waiting in the inbox (or Repeating) were sorted by the fixed rules alone; they are read again, so
-- the small model sorts them. Ones you accepted or rejected stay.
DELETE FROM suggestions
WHERE status IN ('pending', 'superseded')
  AND raw_input_id IN (SELECT r.id FROM raw_inputs r JOIN sources s ON s.id = r.source_id WHERE s.kind IN ('gcal', 'ics'))
  AND raw_input_id NOT IN (SELECT raw_input_id FROM suggestions WHERE status IN ('accepted', 'rejected')
                           AND raw_input_id IS NOT NULL);
UPDATE raw_inputs SET content_hash = ''
WHERE source_id IN (SELECT id FROM sources WHERE kind IN ('gcal', 'ics'))
  AND id NOT IN (SELECT raw_input_id FROM suggestions WHERE raw_input_id IS NOT NULL);
UPDATE sources SET last_sync_utc = NULL WHERE kind IN ('gcal', 'ics');

-- Mail that failed only because Friday asked in a way the model no longer takes (a forced tool) is read again.
UPDATE raw_inputs SET status = 'new', error = NULL WHERE status = 'failed' AND error LIKE '%not supported for this model%';
