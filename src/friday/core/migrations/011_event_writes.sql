-- The combined Friday (COMBINED.md 69): changes you make in Friday to events from an editable Google calendar, and
-- events you make while `gcal.new_events_to` names a calendar, wait here until the job saves them to Google. A
-- command queues; the job loop (with the network) writes, so a command never waits on Google.
CREATE TABLE event_writes (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  item_id INTEGER NOT NULL REFERENCES items (id) ON DELETE CASCADE,
  op TEXT NOT NULL CHECK (op IN ('save', 'delete')),
  calendar_id TEXT,  -- for a new event: where it goes
  queued_utc TEXT NOT NULL,
  tries INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  done_utc TEXT
) STRICT;
CREATE INDEX event_writes_pending ON event_writes (user_id, done_utc);
