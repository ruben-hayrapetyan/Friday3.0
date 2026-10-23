-- C10: the Mac's calendars, fed in by the Mac app (COMBINED.md 4), are sources of their own kind. SQLite can't change
-- a CHECK, so the table is rebuilt.
CREATE TABLE sources_new (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  kind TEXT NOT NULL CHECK (kind IN ('ics', 'gcal', 'gmail', 'upload', 'mac')),
  name TEXT NOT NULL,
  config TEXT NOT NULL DEFAULT '{}',
  trusted INTEGER NOT NULL DEFAULT 0,
  enabled INTEGER NOT NULL DEFAULT 1,
  last_sync_utc TEXT,
  last_error TEXT,
  failures INTEGER NOT NULL DEFAULT 0,
  UNIQUE (user_id, kind, name)
) STRICT;
INSERT INTO sources_new SELECT * FROM sources;
DROP TABLE sources;
ALTER TABLE sources_new RENAME TO sources;
