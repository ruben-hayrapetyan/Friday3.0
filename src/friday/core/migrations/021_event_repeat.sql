-- An event from a Google calendar Friday may change can be made to repeat there (30 Oct: "the friday night salsa
-- that's on this week should be a weekly event" failed with "make it repeat there"): a write that adds the repeat,
-- its RRULE in `rule`. SQLite can't change a CHECK, so the table is made again with what it held.
CREATE TABLE event_writes_new (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  item_id INTEGER NOT NULL REFERENCES items (id) ON DELETE CASCADE,
  op TEXT NOT NULL CHECK (op IN ('save', 'delete', 'repeat')),
  calendar_id TEXT,  -- for a new event: where it goes
  rule TEXT,  -- for a repeat: its RRULE, like FREQ=WEEKLY;BYDAY=FR
  queued_utc TEXT NOT NULL,
  tries INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  done_utc TEXT
) STRICT;
INSERT INTO event_writes_new (id, user_id, item_id, op, calendar_id, queued_utc, tries, error, done_utc)
  SELECT id, user_id, item_id, op, calendar_id, queued_utc, tries, error, done_utc FROM event_writes;
DROP TABLE event_writes;
ALTER TABLE event_writes_new RENAME TO event_writes;
CREATE INDEX event_writes_pending ON event_writes (user_id, done_utc);
