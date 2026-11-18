-- Breaks (18 Nov): a run of days off or light. A break's own choices are NULL until set, and follow your defaults
-- (Settings → Breaks) till then. Named vacations here: "breaks" already means naps and snacks in the code.
CREATE TABLE vacations (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  name TEXT NOT NULL,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  mode TEXT NOT NULL DEFAULT 'light' CHECK (mode IN ('off', 'light')),
  per_day INTEGER CHECK (per_day IS NULL OR per_day >= 1),
  pause TEXT,
  plan_meals INTEGER,
  keep_sleep INTEGER,
  created_utc TEXT NOT NULL,
  CHECK (start_date <= end_date)
) STRICT;

-- What you ticked off a break day's list: the item, and what the tick did (finished it, or logged the day's share).
CREATE TABLE vacation_ticks (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  date TEXT NOT NULL,
  item_id INTEGER NOT NULL,
  finished INTEGER NOT NULL DEFAULT 0,
  progress_id INTEGER,
  created_utc TEXT NOT NULL,
  UNIQUE (user_id, date, item_id)
) STRICT;
