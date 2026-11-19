-- A Light break day holds a time of work, not a number of things (19 Nov: "the number of time that you spend total
-- working shouldn't depend on the number of events that you choose to do"; it's yours to set). NULL follows your
-- default (Settings → Breaks). A break that had set "about N things" keeps what that meant: N x 45 minutes.
ALTER TABLE vacations ADD COLUMN work_min INTEGER CHECK (work_min IS NULL OR work_min BETWEEN 15 AND 1440);
UPDATE vacations SET work_min = per_day * 45 WHERE per_day IS NOT NULL;
UPDATE vacations SET per_day = NULL;
