-- A repeat deleted in Friday is taken off its calendar from that time on (8 Nov: twenty-two yearly birthdays
-- deleted here would have left every later year in Google, the Mac deleting only the one time it was given): a
-- write that deletes this time and every later one. SQLite can't change a CHECK, so the table is made again.
CREATE TABLE event_writes_new (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  item_id INTEGER NOT NULL REFERENCES items (id) ON DELETE CASCADE,
  op TEXT NOT NULL CHECK (op IN ('save', 'delete', 'repeat', 'delete_from')),
  calendar_id TEXT,  -- for a new event: where it goes
  rule TEXT,  -- for a repeat: its RRULE, like FREQ=WEEKLY;BYDAY=FR
  queued_utc TEXT NOT NULL,
  tries INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  done_utc TEXT
) STRICT;
INSERT INTO event_writes_new (id, user_id, item_id, op, calendar_id, rule, queued_utc, tries, error, done_utc)
  SELECT id, user_id, item_id, op, calendar_id, rule, queued_utc, tries, error, done_utc FROM event_writes;
DROP TABLE event_writes;
ALTER TABLE event_writes_new RENAME TO event_writes;
CREATE INDEX event_writes_pending ON event_writes (user_id, done_utc);
