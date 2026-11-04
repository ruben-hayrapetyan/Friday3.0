-- Working on two things at once (2 Nov: "make support for working on two things at once even if friday didn't
-- originally plan to"): a timer per item you're on, not one per user. The one started last is "the timer" the plan
-- holds at now; the others run alongside it. SQLite can't drop a UNIQUE: rebuilt.
CREATE TABLE timer_new (
  user_id INTEGER NOT NULL DEFAULT 1,
  item_id INTEGER NOT NULL REFERENCES items (id) ON DELETE CASCADE,
  start_utc TEXT NOT NULL,
  PRIMARY KEY (user_id, item_id)
) STRICT;
INSERT INTO timer_new (user_id, item_id, start_utc) SELECT user_id, item_id, start_utc FROM timer;
DROP TABLE timer;
ALTER TABLE timer_new RENAME TO timer;
