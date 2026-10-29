-- Naps (Sleep & meals → Sleep, with sleep tracking on): "Taking a nap" and "I'm up", or one logged after the fact.
-- While you nap the plan keeps the time clear for as long as you usually nap; a nap counts against the sleep the
-- night before fell short of.
CREATE TABLE naps (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  date TEXT NOT NULL,  -- the planning day it belongs to
  start_utc TEXT NOT NULL,
  end_utc TEXT,  -- NULL while you nap
  created_utc TEXT NOT NULL
) STRICT;
CREATE INDEX naps_by_day ON naps (user_id, date);
