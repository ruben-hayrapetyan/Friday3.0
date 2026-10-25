-- Sleep tracking (Settings → Schedule, off until you turn it on): when you went to bed, got up and were ready to
-- work, one tap each. Friday learns your real bedtime, wake time and morning routine from them, and your sleep debt.
CREATE TABLE sleep_marks (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  kind TEXT NOT NULL CHECK (kind IN ('bed', 'up', 'ready')),
  at_utc TEXT NOT NULL,
  created_utc TEXT NOT NULL
) STRICT;
CREATE INDEX sleep_marks_by_time ON sleep_marks (user_id, at_utc);
