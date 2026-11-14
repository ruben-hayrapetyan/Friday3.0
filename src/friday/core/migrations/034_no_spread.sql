-- Tasks aren't marked spread or clustered any more (14 Nov: "Tasks are not marked as spread and i don't know where you
-- would find this distinction"): a rule says it for the work you name ("spread my essays over several days"). The
-- items' column goes; the kinds you saved lose the facet; the two built-in rules for marked work ("Spread out what you
-- marked spread", "Keep clustered work on few days") leave your saved rules, the others kept in their order. A rule
-- you wrote that spreads or clusters has a name of its own (you:…) and stays.
ALTER TABLE items DROP COLUMN spread;

UPDATE settings SET version = version + 1, value = (
  SELECT json_group_object(p.key, json(json_remove(p.value, '$.spread')))
  FROM (SELECT id, key, value FROM json_each(settings.value) ORDER BY id) AS p
)
WHERE key = 'presets' AND json_valid(value) AND json_type(value) = 'object'
  AND EXISTS (SELECT 1 FROM json_each(settings.value) AS p WHERE json_type(p.value, '$.spread') IS NOT NULL);

UPDATE settings SET version = version + 1, value = (
  SELECT json_group_array(json(r.value))
  FROM (SELECT key, value FROM json_each(settings.value) ORDER BY key) AS r
  WHERE NOT (json_extract(r.value, '$.name') IN ('spread', 'cluster')
             AND json_extract(r.value, '$.type') = json_extract(r.value, '$.name'))
)
WHERE key = 'rules' AND json_valid(value) AND json_type(value) = 'array'
  AND EXISTS (SELECT 1 FROM json_each(settings.value) AS r
              WHERE json_extract(r.value, '$.name') IN ('spread', 'cluster')
                AND json_extract(r.value, '$.type') = json_extract(r.value, '$.name'));
