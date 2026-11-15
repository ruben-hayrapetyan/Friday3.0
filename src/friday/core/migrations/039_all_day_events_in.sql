-- All-day events come in for everyone (15 Nov: a client's Thanksgiving and own all-day events never showed, as
-- `gcal.include_all_day` was off unless you knew to turn it on; the app never offered it). A saved "off" you never
-- chose becomes on: one is kept off only where your settings' history shows you turning it off. Then every calendar
-- is read again on the next sync, as when the setting changes (commands/calendars.py reread_calendars): what it
-- suggested that you haven't answered is withdrawn and suggested afresh, the all-day events with it. A settings file
-- that sets `gcal` is read again too, so one that says "off" still says so.
CREATE TEMP TABLE chose_off AS
SELECT DISTINCT c.user_id
FROM command_log AS c, json_each(c.undo) AS ch
WHERE json_valid(c.undo) AND json_extract(ch.value, '$.table') = 'settings'
  AND json_extract(ch.value, '$.key.key') = 'gcal'
  AND json_valid(json_extract(ch.value, '$.before.value')) AND json_valid(json_extract(ch.value, '$.after.value'))
  AND json_extract(json_extract(ch.value, '$.before.value'), '$.include_all_day') = 1
  AND json_extract(json_extract(ch.value, '$.after.value'), '$.include_all_day') = 0;

CREATE TEMP TABLE turned_on AS
SELECT user_id FROM settings
WHERE key = 'gcal' AND json_valid(value) AND json_extract(value, '$.include_all_day') = 0
  AND user_id NOT IN (SELECT user_id FROM chose_off)
UNION  -- no gcal saved: the new default turns it on
SELECT DISTINCT s.user_id FROM sources AS s
WHERE s.kind IN ('gcal', 'mac', 'ics') AND NOT EXISTS (SELECT 1 FROM settings AS g WHERE g.user_id = s.user_id AND g.key = 'gcal');

UPDATE settings SET version = version + 1, value = json_set(value, '$.include_all_day', json('true'))
WHERE key = 'gcal' AND user_id IN (SELECT user_id FROM turned_on) AND json_valid(value);

UPDATE suggestions SET status = 'superseded'
WHERE status = 'pending' AND raw_input_id IN (
  SELECT r.id FROM raw_inputs AS r JOIN sources AS s ON s.id = r.source_id
  WHERE s.kind IN ('gcal', 'mac', 'ics') AND s.user_id IN (SELECT user_id FROM turned_on)
);

UPDATE raw_inputs SET content_hash = ''
WHERE source_id IN (SELECT id FROM sources WHERE kind IN ('gcal', 'mac', 'ics')
                    AND user_id IN (SELECT user_id FROM turned_on))
  AND NOT EXISTS (SELECT 1 FROM suggestions AS g WHERE g.raw_input_id = raw_inputs.id
                  AND g.status IN ('accepted', 'rejected'));

INSERT INTO kv (user_id, key, value)
SELECT user_id, 'sync_now', json_quote('migration 039') FROM turned_on WHERE true
ON CONFLICT (user_id, key) DO UPDATE SET value = excluded.value;

DELETE FROM kv WHERE key = 'config_stamp' AND user_id IN (
  SELECT k.user_id FROM kv AS k, json_each(k.value) AS j WHERE k.key = 'config_keys' AND json_valid(k.value)
  AND j.value = 'gcal'
);

DROP TABLE chose_off;
DROP TABLE turned_on;
