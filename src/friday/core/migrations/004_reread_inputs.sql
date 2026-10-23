-- M12 reads calendars and mail differently, so what the old reading left behind is cleared for the next sync.

-- Google events still waiting in the inbox from before repeating events were grouped (no batch): they and their
-- inputs go, so they are read again. Inputs you accepted or rejected anything from stay.
DELETE FROM suggestions
WHERE status IN ('pending', 'superseded') AND batch IS NULL
  AND raw_input_id IN (SELECT r.id FROM raw_inputs r JOIN sources s ON s.id = r.source_id WHERE s.kind = 'gcal')
  AND raw_input_id NOT IN (SELECT raw_input_id FROM suggestions WHERE status IN ('accepted', 'rejected')
                           AND raw_input_id IS NOT NULL);
DELETE FROM raw_inputs
WHERE source_id IN (SELECT id FROM sources WHERE kind = 'gcal')
  AND id NOT IN (SELECT raw_input_id FROM suggestions WHERE raw_input_id IS NOT NULL);

-- A calendar read twice under two names (`primary` and its own name): the later row goes, with its inputs.
DELETE FROM suggestions WHERE raw_input_id IN (
  SELECT r.id FROM raw_inputs r JOIN sources s ON s.id = r.source_id
  WHERE s.kind = 'gcal' AND s.id > (SELECT MIN(o.id) FROM sources o WHERE o.kind = 'gcal' AND o.user_id = s.user_id
                                    AND json_extract(o.config, '$.calendar') = json_extract(s.config, '$.calendar')));
DELETE FROM raw_inputs WHERE source_id IN (
  SELECT s.id FROM sources s
  WHERE s.kind = 'gcal' AND s.id > (SELECT MIN(o.id) FROM sources o WHERE o.kind = 'gcal' AND o.user_id = s.user_id
                                    AND json_extract(o.config, '$.calendar') = json_extract(s.config, '$.calendar')));
DELETE FROM sources
WHERE kind = 'gcal' AND id > (SELECT MIN(o.id) FROM sources o WHERE o.kind = 'gcal' AND o.user_id = sources.user_id
                              AND json_extract(o.config, '$.calendar') = json_extract(sources.config, '$.calendar'));

-- Mail that failed because the AI refused the key or was down, not because of the message: it is read again.
UPDATE raw_inputs SET status = 'new', error = NULL
WHERE status = 'failed' AND (error LIKE 'Error code: 401%' OR error LIKE 'Error code: 403%'
                             OR error LIKE 'Error code: 429%' OR error LIKE 'Error code: 5%');

-- A series that mirrors a repeating calendar event (`gcal:<event id>`): the calendar makes its occurrences, so it
-- never materializes and is changed in the calendar, not here.
ALTER TABLE series ADD COLUMN external_id TEXT;
