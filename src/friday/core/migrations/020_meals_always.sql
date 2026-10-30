-- A meal you keep Always ("Never skip lunch or dinner", set to Always) was priced the same as Strongly, below what
-- work days overdue costs, so an overloaded plan left lunch and dinner off (30 Oct). Always is now priced above any
-- lateness (rule_text.MEAL_ALWAYS); rules saved before get the new price.
UPDATE settings SET version = version + 1, value = (
  SELECT json_group_array(json(rule)) FROM (
    SELECT CASE
      WHEN json_extract(r.value, '$.type') = 'elastic_shortfall' AND json_extract(r.value, '$.stage') = 'deadlines'
           AND EXISTS (
             SELECT 1 FROM kv
             WHERE kv.user_id = settings.user_id AND kv.key = 'rule_readings'
               AND json_extract(kv.value, '$."' || json_extract(r.value, '$.name') || '".strength') = 'Always'
               AND json_extract(kv.value, '$."' || json_extract(r.value, '$.name') || '".reading.kind') = 'meals_kept'
           )
        THEN json_set(r.value, '$.params.steep', 10000000.0)
      ELSE r.value END AS rule
    FROM json_each(settings.value) AS r ORDER BY r.key
  )
)
WHERE key = 'rules'
  AND EXISTS (
    SELECT 1 FROM json_each(settings.value) AS r, kv
    WHERE kv.user_id = settings.user_id AND kv.key = 'rule_readings'
      AND json_extract(r.value, '$.type') = 'elastic_shortfall'
      AND json_extract(kv.value, '$."' || json_extract(r.value, '$.name') || '".strength') = 'Always'
      AND json_extract(kv.value, '$."' || json_extract(r.value, '$.name') || '".reading.kind') = 'meals_kept'
  );
