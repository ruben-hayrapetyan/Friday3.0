-- M8: two more kinds (`check`: "did you finish it?" after the last block before a hard due; `test`), and the text
-- sent, so the app can list what was sent. SQLite can't change a CHECK, so the table is rebuilt.
CREATE TABLE notifications_new (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  kind TEXT NOT NULL CHECK (kind IN ('morning_brief', 'block_start', 'slack_low', 'overload', 'conflict',
                                     'evening_review', 'weekly_review', 'check', 'test')),
  item_id INTEGER REFERENCES items (id) ON DELETE SET NULL,
  dedup_key TEXT NOT NULL UNIQUE,
  channel TEXT NOT NULL,
  sent_utc TEXT NOT NULL,
  acted INTEGER CHECK (acted IN (0, 1)),
  title TEXT NOT NULL DEFAULT '',
  body TEXT NOT NULL DEFAULT ''
) STRICT;
INSERT INTO notifications_new (id, user_id, kind, item_id, dedup_key, channel, sent_utc, acted)
  SELECT id, user_id, kind, item_id, dedup_key, channel, sent_utc, acted FROM notifications;
DROP TABLE notifications;
ALTER TABLE notifications_new RENAME TO notifications;
