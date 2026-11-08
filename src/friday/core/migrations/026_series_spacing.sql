-- A repeating task's times kept apart (PROGRESS.md C50, 8 Nov: "laundry sessions should have a minimum of 7 days
-- between each event"): at least this many days from one time's start to the next's, counted from when you did the
-- last one. Empty for a repeat without it.
ALTER TABLE series ADD COLUMN min_gap_days REAL CHECK (min_gap_days IS NULL OR min_gap_days > 0);
