-- The combined Friday (COMBINED.md 21): personal's short and long term lists. A long-term task is planned like any
-- other; the to-do list keeps it on its own page, in its own ink.
ALTER TABLE items ADD COLUMN long_term INTEGER NOT NULL DEFAULT 0 CHECK (long_term IN (0, 1));
