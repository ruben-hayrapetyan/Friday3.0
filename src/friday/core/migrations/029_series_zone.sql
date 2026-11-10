-- Each repeat keeps the timezone it was made in, so its later times keep their real moment when you move (PROGRESS.md,
-- 10 Nov: a 2pm New York lecture was 11am in Los Angeles until the times made after the move, then 2pm). Repeats made
-- before are taken to have been made in the timezone you have now.
ALTER TABLE series ADD COLUMN zone TEXT;
UPDATE series SET zone = (
  SELECT json_extract(s.value, '$.timezone') FROM settings s WHERE s.key = 'time' AND s.user_id = series.user_id
);
