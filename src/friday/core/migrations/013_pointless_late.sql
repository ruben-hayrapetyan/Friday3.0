-- The combined Friday (COMBINED.md 50): work that is pointless once its deadline has passed is never planned after
-- it. NULL follows the kinds and titles in `pointless_late` (exam prep by default); 1 or 0 is your own say.
ALTER TABLE items ADD COLUMN expires INTEGER CHECK (expires IN (0, 1));
