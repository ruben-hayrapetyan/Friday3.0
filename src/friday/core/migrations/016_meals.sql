-- Meal tracking (Sleep & meals, off until you turn it on): when you ate breakfast, lunch, dinner or a snack, from one
-- tap to the next ("Eating now", "Done eating"), or that you skipped it. Friday learns when you usually eat, for how
-- long and how often you skip each meal; eating or skipping one ticks off that day's routine of the same name.
CREATE TABLE meals (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  kind TEXT NOT NULL CHECK (kind IN ('breakfast', 'lunch', 'dinner', 'snack')),
  date TEXT NOT NULL,  -- the planning day it belongs to
  start_utc TEXT,  -- NULL for a skipped meal
  end_utc TEXT,  -- NULL while you're eating, and for a skipped one
  skipped INTEGER NOT NULL DEFAULT 0,
  item_id INTEGER REFERENCES items (id) ON DELETE SET NULL,  -- the routine occurrence it ticked off, to open again
  created_utc TEXT NOT NULL
) STRICT;
CREATE INDEX meals_by_day ON meals (user_id, date);
