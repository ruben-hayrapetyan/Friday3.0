-- "Done with work" (Sleep & meals → Sleep): when you stopped working for the night, a tap of its own beside "Going to
-- bed", so the wind-down between them is learned as the morning routine is. SQLite can't alter a CHECK: rebuilt.
CREATE TABLE sleep_marks_new (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  kind TEXT NOT NULL CHECK (kind IN ('bed', 'up', 'ready', 'done')),
  at_utc TEXT NOT NULL,
  created_utc TEXT NOT NULL
) STRICT;
INSERT INTO sleep_marks_new (id, user_id, kind, at_utc, created_utc)
  SELECT id, user_id, kind, at_utc, created_utc FROM sleep_marks;
DROP TABLE sleep_marks;
ALTER TABLE sleep_marks_new RENAME TO sleep_marks;
CREATE INDEX sleep_marks_by_time ON sleep_marks (user_id, at_utc);
