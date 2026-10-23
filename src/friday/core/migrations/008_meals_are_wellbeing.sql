-- Meals were dropped whole (M16): a routine's shortfall was a preference, below wellbeing rules that counted a meal
-- as load. Rules kept from the old defaults get the new ones: late_night, the evening and weekend reserves and
-- daily_load leave routines out, and a meal below its minimum is priced in wellbeing (elastic_minimum).
UPDATE settings SET version = version + 1, value = (
  SELECT json_group_array(json(rule)) FROM (
    SELECT CASE
      WHEN json_extract(value, '$.name') IN ('late_night', 'weekday_evenings', 'weekends', 'daily_load')
           AND json_extract(value, '$.scope') IS NULL
        THEN json_set(value, '$.scope', json('{"except_preset": ["Routine"]}'))
      ELSE value END AS rule
    FROM json_each(settings.value) ORDER BY key
  )
)
WHERE key = 'rules';

UPDATE settings SET value = json_insert(value, '$[#]', json(
  '{"type": "elastic_shortfall", "name": "elastic_minimum", "weight": 1, "stage": "wellbeing", "scope": null, "reason": null, "params": {"steep": 20, "gentle": 0}, "enabled": true}'
))
WHERE key = 'rules'
  AND NOT EXISTS (SELECT 1 FROM json_each(settings.value) WHERE json_extract(value, '$.name') = 'elastic_minimum');

-- A meal isn't light work: deep_run (3 hours in a row of deep or light work) counted lunch towards the run.
UPDATE settings SET version = version + 1, value = json_remove(value, '$.Routine.energy')
WHERE key = 'presets' AND json_extract(value, '$.Routine.energy') = 'light';
UPDATE items SET energy = NULL WHERE preset = 'Routine' AND energy = 'light';
UPDATE series SET template = json_remove(template, '$.energy')
WHERE json_extract(template, '$.preset') = 'Routine' AND json_extract(template, '$.energy') = 'light';
