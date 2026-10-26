-- "Runs by itself" (a task's switch): laundry, a long simulation, a download. Only its first quarter hour needs you;
-- the plan holds that and plans other work on top of the rest while it runs.
ALTER TABLE items ADD COLUMN background INTEGER NOT NULL DEFAULT 0 CHECK (background IN (0, 1));
