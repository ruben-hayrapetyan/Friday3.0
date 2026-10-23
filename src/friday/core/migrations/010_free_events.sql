-- The combined Friday (COMBINED.md 28): an event marked free in its calendar is kept, but doesn't count as busy when
-- planning unless you say so (Settings → Calendars).
ALTER TABLE items ADD COLUMN free INTEGER NOT NULL DEFAULT 0 CHECK (free IN (0, 1));
