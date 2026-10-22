-- M10: what comes in from outside, kept before anything is read from it, and the suggestions made from it (§22.1).
CREATE TABLE sources (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  kind TEXT NOT NULL CHECK (kind IN ('ics', 'gcal', 'gmail', 'upload')),
  name TEXT NOT NULL,
  config TEXT NOT NULL DEFAULT '{}',
  trusted INTEGER NOT NULL DEFAULT 0,
  enabled INTEGER NOT NULL DEFAULT 1,
  last_sync_utc TEXT,
  last_error TEXT,
  failures INTEGER NOT NULL DEFAULT 0,
  UNIQUE (user_id, kind, name)
) STRICT;

CREATE TABLE raw_inputs (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  source_id INTEGER NOT NULL REFERENCES sources (id) ON DELETE CASCADE,
  external_id TEXT NOT NULL,
  received_utc TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  media_type TEXT NOT NULL DEFAULT 'text/plain',
  content TEXT NOT NULL,  -- text, or base64 for a document
  status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'extracted', 'ignored', 'failed')),
  error TEXT,
  UNIQUE (source_id, external_id)
) STRICT;

CREATE TABLE suggestions (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  raw_input_id INTEGER REFERENCES raw_inputs (id) ON DELETE CASCADE,
  batch TEXT,
  command TEXT NOT NULL,
  input TEXT NOT NULL,
  quotes TEXT NOT NULL DEFAULT '{}',
  confidence REAL NOT NULL DEFAULT 1.0,
  duplicate_of INTEGER REFERENCES items (id) ON DELETE SET NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected', 'superseded')),
  created_utc TEXT NOT NULL,
  decided_utc TEXT,
  item_id INTEGER REFERENCES items (id) ON DELETE SET NULL  -- what accepting made, so a later update can edit it
) STRICT;

-- New actors: `config` (friday.toml), `sync:<source>` (a trusted source), `mcp:<client>` (an assistant). SQLite can't
-- change a CHECK, so the log is rebuilt; ids are kept, so `undone_by` still points where it did.
CREATE TABLE command_log_new (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  at_utc TEXT NOT NULL,
  actor TEXT NOT NULL CHECK (actor IN ('you', 'cli', 'job', 'config') OR actor LIKE 'agent:%' OR actor LIKE 'sync:%'
                             OR actor LIKE 'mcp:%'),
  command TEXT NOT NULL,
  input TEXT NOT NULL,
  result TEXT NOT NULL,
  undo TEXT,
  idempotency_key TEXT UNIQUE,
  undone_by INTEGER REFERENCES command_log (id)
) STRICT;
INSERT INTO command_log_new SELECT * FROM command_log;
DROP TABLE command_log;
ALTER TABLE command_log_new RENAME TO command_log;
