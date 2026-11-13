-- The times Stop took off a repeat, kept so Start brings back those and no others (audit, 12 Nov: a repeat stopped
-- and started again brought back the times you had dropped one at a time). A JSON list of item ids, empty while it
-- runs. NULL for a repeat stopped before this was kept: Start brings back every dropped time from today on, as it did.
ALTER TABLE series ADD COLUMN stopped_items TEXT DEFAULT '[]';
UPDATE series SET stopped_items = NULL WHERE active = 0;
