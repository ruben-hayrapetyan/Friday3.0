-- Every table has user_id so a hosted service stays possible (DESIGN §23). It is always 1 for now.

CREATE TABLE users (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  timezone TEXT
) STRICT;

CREATE TABLE areas (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  name TEXT NOT NULL,
  color TEXT,
  archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
  UNIQUE (user_id, name)
) STRICT;

CREATE TABLE series (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  template TEXT NOT NULL,
  rrule TEXT NOT NULL,
  dtstart_local TEXT NOT NULL,
  per_window INTEGER NOT NULL DEFAULT 1 CHECK (per_window >= 1),
  release_offset_min INTEGER,
  due_offset_min INTEGER,
  active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
  created_utc TEXT NOT NULL,
  updated_utc TEXT NOT NULL
) STRICT;

CREATE TABLE items (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  title TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT '',
  preset TEXT,
  area_id INTEGER REFERENCES areas (id),
  tags TEXT NOT NULL DEFAULT '[]',
  parent_id INTEGER REFERENCES items (id),
  when_kind TEXT NOT NULL CHECK (when_kind IN ('fixed', 'window', 'anytime')),
  start_utc TEXT,
  end_utc TEXT,
  release_utc TEXT,
  due_utc TEXT,
  amount TEXT NOT NULL CHECK (amount IN ('fixed', 'elastic', 'target', 'open')),
  duration_units INTEGER,
  min_units INTEGER,
  ideal_units INTEGER,
  max_units INTEGER,
  target_units INTEGER,
  cap_units INTEGER,
  daily_ceiling_units INTEGER,
  shape TEXT NOT NULL CHECK (shape IN ('one_sitting', 'split')),
  min_chunk_units INTEGER NOT NULL DEFAULT 2,
  max_chunk_units INTEGER,
  chunk_cost REAL NOT NULL DEFAULT 0 CHECK (chunk_cost BETWEEN 0 AND 1),
  spread TEXT NOT NULL DEFAULT 'none' CHECK (spread IN ('none', 'spread', 'cluster')),
  firmness TEXT NOT NULL DEFAULT 'none' CHECK (firmness IN ('hard', 'soft', 'none')),
  importance INTEGER NOT NULL DEFAULT 3 CHECK (importance BETWEEN 1 AND 5),
  neglect_carry REAL NOT NULL DEFAULT 0.5 CHECK (neglect_carry BETWEEN 0 AND 1),
  energy TEXT CHECK (energy IN ('deep', 'light', 'physical', 'social')),
  location TEXT,
  certainty TEXT NOT NULL DEFAULT 'planned' CHECK (certainty IN ('planned', 'tentative')),
  event_kind TEXT,
  blocks_time INTEGER NOT NULL DEFAULT 1 CHECK (blocks_time IN (0, 1)),
  buffer_before_min INTEGER,
  buffer_after_min INTEGER,
  status TEXT NOT NULL DEFAULT 'todo' CHECK (status IN ('todo', 'done', 'dropped', 'skipped')),
  series_id INTEGER REFERENCES series (id),
  occurrence_date TEXT,
  occurrence_n INTEGER,
  detached INTEGER NOT NULL DEFAULT 0 CHECK (detached IN (0, 1)),
  duration_source TEXT CHECK (duration_source IN ('you', 'estimate', 'preset')),
  your_estimate_units INTEGER,
  friday_estimate_units INTEGER,
  estimate_detail TEXT,
  created_utc TEXT NOT NULL,
  updated_utc TEXT NOT NULL,
  completed_utc TEXT,
  UNIQUE (series_id, occurrence_date, occurrence_n)
) STRICT;

CREATE INDEX items_by_status ON items (user_id, status);

CREATE TABLE dependencies (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  item_id INTEGER NOT NULL REFERENCES items (id) ON DELETE CASCADE,
  depends_on_id INTEGER NOT NULL REFERENCES items (id) ON DELETE CASCADE,
  fraction REAL NOT NULL DEFAULT 1.0 CHECK (fraction > 0 AND fraction <= 1),
  lag_min INTEGER NOT NULL DEFAULT 0 CHECK (lag_min >= 0),
  UNIQUE (item_id, depends_on_id),
  CHECK (item_id != depends_on_id)
) STRICT;

CREATE TABLE pins (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  item_id INTEGER NOT NULL REFERENCES items (id) ON DELETE CASCADE,
  start_utc TEXT NOT NULL,
  end_utc TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('preferred', 'locked')),
  created_utc TEXT NOT NULL,
  CHECK (start_utc < end_utc)
) STRICT;

CREATE TABLE plans (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  created_utc TEXT NOT NULL,
  generation INTEGER NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('current', 'replaced', 'preview', 'waiting')),
  stage_values TEXT NOT NULL,
  solve_seconds REAL NOT NULL,
  report TEXT NOT NULL
) STRICT;

CREATE UNIQUE INDEX one_current_plan ON plans (user_id) WHERE status = 'current';

CREATE TABLE blocks (
  plan_id INTEGER NOT NULL REFERENCES plans (id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL DEFAULT 1,
  item_id INTEGER NOT NULL REFERENCES items (id) ON DELETE CASCADE,
  start_utc TEXT NOT NULL,
  end_utc TEXT NOT NULL,
  cost TEXT NOT NULL,
  tentative INTEGER NOT NULL DEFAULT 0 CHECK (tentative IN (0, 1)),
  PRIMARY KEY (plan_id, item_id, start_utc)
) STRICT;

CREATE TABLE progress (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  item_id INTEGER NOT NULL REFERENCES items (id) ON DELETE CASCADE,
  start_utc TEXT,
  end_utc TEXT,
  minutes INTEGER NOT NULL CHECK (minutes >= 0),
  source TEXT NOT NULL CHECK (source IN ('timer', 'review', 'slider', 'retro', 'assumed')),
  block_key TEXT,
  created_utc TEXT NOT NULL
) STRICT;

CREATE INDEX progress_by_item ON progress (item_id);

CREATE TABLE timer (
  user_id INTEGER NOT NULL DEFAULT 1 UNIQUE,
  item_id INTEGER NOT NULL REFERENCES items (id) ON DELETE CASCADE,
  start_utc TEXT NOT NULL
) STRICT;

CREATE TABLE reviews (
  user_id INTEGER NOT NULL DEFAULT 1,
  date TEXT NOT NULL,
  submitted_utc TEXT NOT NULL,
  PRIMARY KEY (user_id, date)
) STRICT;

CREATE TABLE completions (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  item_id INTEGER NOT NULL,
  area TEXT,
  preset TEXT,
  norm_title TEXT NOT NULL,
  your_estimate_units INTEGER,
  friday_estimate_units INTEGER,
  actual_minutes INTEGER NOT NULL,
  actual_source TEXT NOT NULL CHECK (actual_source IN ('timer', 'review', 'slider', 'retro', 'assumed')),
  completed_utc TEXT NOT NULL
) STRICT;

CREATE TABLE day_overrides (
  user_id INTEGER NOT NULL DEFAULT 1,
  date TEXT NOT NULL,
  bedtime TEXT,
  wake TEXT,
  margin_min INTEGER,
  cap_hours REAL,
  PRIMARY KEY (user_id, date)
) STRICT;

CREATE TABLE pace_periods (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  pace_name TEXT,
  dials TEXT NOT NULL,
  start_date TEXT NOT NULL,
  end_date TEXT,
  created_utc TEXT NOT NULL,
  CHECK (end_date IS NULL OR start_date <= end_date)
) STRICT;

CREATE TABLE settings (
  user_id INTEGER NOT NULL DEFAULT 1,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  version INTEGER NOT NULL,
  updated_utc TEXT NOT NULL,
  PRIMARY KEY (user_id, key)
) STRICT;

CREATE TABLE command_log (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  at_utc TEXT NOT NULL,
  actor TEXT NOT NULL CHECK (actor IN ('you', 'cli', 'job') OR actor LIKE 'agent:%'),
  command TEXT NOT NULL,
  input TEXT NOT NULL,
  result TEXT NOT NULL,
  undo TEXT,
  idempotency_key TEXT UNIQUE,
  undone_by INTEGER REFERENCES command_log (id)
) STRICT;

CREATE TABLE notifications (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  kind TEXT NOT NULL CHECK (kind IN ('morning_brief', 'block_start', 'slack_low', 'overload', 'conflict',
                                     'evening_review', 'weekly_review')),
  item_id INTEGER REFERENCES items (id) ON DELETE SET NULL,
  dedup_key TEXT NOT NULL UNIQUE,
  channel TEXT NOT NULL,
  sent_utc TEXT NOT NULL,
  acted INTEGER CHECK (acted IN (0, 1))
) STRICT;

CREATE TABLE comparisons (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  asked_utc TEXT NOT NULL,
  plan_a TEXT NOT NULL,
  plan_b TEXT NOT NULL,
  features_a TEXT NOT NULL,
  features_b TEXT NOT NULL,
  answer TEXT CHECK (answer IN ('a', 'b', 'skip')),
  answered_utc TEXT,
  source TEXT NOT NULL CHECK (source IN ('question', 'drag')),
  dials TEXT NOT NULL
) STRICT;

CREATE TABLE learned_profile (
  user_id INTEGER NOT NULL DEFAULT 1,
  version INTEGER NOT NULL,
  created_utc TEXT NOT NULL,
  theta TEXT NOT NULL,
  answer_noise REAL,
  state TEXT,
  proposals TEXT,
  wall_decisions TEXT,
  evidence TEXT,
  status TEXT NOT NULL CHECK (status IN ('suggested', 'active', 'rejected')),
  PRIMARY KEY (user_id, version)
) STRICT;

CREATE TABLE checkins (
  user_id INTEGER NOT NULL DEFAULT 1,
  date TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('tired', 'normal', 'motivated')),
  PRIMARY KEY (user_id, date)
) STRICT;

CREATE TABLE push_subscriptions (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  endpoint TEXT NOT NULL UNIQUE,
  keys TEXT NOT NULL,
  created_utc TEXT NOT NULL
) STRICT;

CREATE TABLE job_runs (
  user_id INTEGER NOT NULL DEFAULT 1,
  name TEXT NOT NULL,
  last_run_utc TEXT,
  last_status TEXT,
  last_error TEXT,
  PRIMARY KEY (user_id, name)
) STRICT;

CREATE TABLE kv (
  user_id INTEGER NOT NULL DEFAULT 1,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  PRIMARY KEY (user_id, key)
) STRICT;

INSERT INTO users (id, name) VALUES (1, 'me');
