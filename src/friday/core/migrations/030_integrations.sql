-- C96: integrations (Todoist, Notion, Asana…) are sources of their own kinds. Each kind is now checked by Friday's own
-- list of connectors (src/friday/integrations), not here, so a new one needs no rebuild; this is the last.
CREATE TABLE sources_new (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  kind TEXT NOT NULL CHECK (length(kind) BETWEEN 2 AND 40),
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

-- What goes back to an integration (C96: done in Friday marks it done there): queued in the command's own
-- transaction, so undoing the command takes it back; sent by the integrations job, retried, never for the sync's own
-- changes.
CREATE TABLE source_writes (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  source_id INTEGER NOT NULL REFERENCES sources (id) ON DELETE CASCADE,
  external_id TEXT NOT NULL,
  item_id INTEGER,
  op TEXT NOT NULL CHECK (op IN ('done', 'reopen')),
  created_utc TEXT NOT NULL,
  tries INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  done_utc TEXT
) STRICT;
CREATE INDEX source_writes_waiting ON source_writes (source_id) WHERE done_utc IS NULL;
