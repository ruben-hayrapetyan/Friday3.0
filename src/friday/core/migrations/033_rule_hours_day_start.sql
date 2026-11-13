-- A rule's hours run to your day's start, not 4am (audit, 12 Nov: "No work after 10pm" kept work out from 10pm to 4am
-- whatever time your day starts). Rules made before ran to 4am: those you wrote with "before" or "after" a time (as
-- your words, kept in rule_readings, say) now run to the day start you have, where it isn't 4am. An end you set to
-- another time yourself stays. Rules are kept in their order.
UPDATE settings SET version = version + 1, value = (
  SELECT json_group_array(json(CASE
    WHEN json_extract(r.value, '$.type') = 'time_preference'
     AND json_extract(k.value, '$."' || json_extract(r.value, '$.name') || '".reading.kind') = 'window'
     AND json_extract(k.value, '$."' || json_extract(r.value, '$.name') || '".reading.rel') = 'before'
     AND json_extract(r.value, '$.params.end') = '04:00'
    THEN json_set(r.value, '$.params.end', t.day_start)
    WHEN json_extract(r.value, '$.type') = 'time_preference'
     AND json_extract(k.value, '$."' || json_extract(r.value, '$.name') || '".reading.kind') = 'window'
     AND json_extract(k.value, '$."' || json_extract(r.value, '$.name') || '".reading.rel') = 'after'
     AND json_extract(r.value, '$.params.start') = '04:00'
    THEN json_set(r.value, '$.params.start', t.day_start)
    ELSE r.value END))
  FROM (SELECT key, value FROM json_each(settings.value) ORDER BY key) AS r,
       (SELECT coalesce(json_extract(value, '$.day_start'), '04:00') AS day_start FROM settings AS s
        WHERE s.user_id = settings.user_id AND s.key = 'time') AS t
  LEFT JOIN kv AS k ON k.user_id = settings.user_id AND k.key = 'rule_readings'
)
WHERE key = 'rules' AND json_valid(value) AND json_type(value) = 'array'
  AND EXISTS (SELECT 1 FROM kv WHERE kv.user_id = settings.user_id AND kv.key = 'rule_readings')
  AND (SELECT coalesce(json_extract(value, '$.day_start'), '04:00') FROM settings AS s
       WHERE s.user_id = settings.user_id AND s.key = 'time') NOT IN ('04:00');
