-- Events read before as 12:00 AM to 11:59 PM (the Mac gives some birthdays so) were drawn the height of the day and
-- counted as busy (3 Nov: "don't make full day events actually look like they take the full day"). They end at the
-- next midnight, as whole-day events do, and leave the time free; the reading does the same from now on.
UPDATE items
SET end_utc = strftime('%Y-%m-%dT%H:%MZ', end_utc, '+1 minute'), blocks_time = 0
WHERE when_kind = 'fixed' AND start_utc IS NOT NULL AND end_utc IS NOT NULL
  AND CAST(round((julianday(end_utc) - julianday(start_utc)) * 1440) AS INTEGER) % 1440 = 1439;
-- A yearly birthday read so repeats from a template that says the same: its next times come whole-day too.
UPDATE series
SET template = json_set(template, '$.length_min', json_extract(template, '$.length_min') + 1,
                        '$.blocks_time', json('false'))
WHERE json_extract(template, '$.when') = 'fixed' AND json_extract(template, '$.length_min') % 1440 = 1439;
