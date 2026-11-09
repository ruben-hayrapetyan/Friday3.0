-- One course for a stretch of work (PROGRESS.md C64, 8 Nov: "i would wanna do math for the entire time not 3
-- different things"): rules saved before get the new built-in, a preference, so it never makes work late.
UPDATE settings SET version = version + 1, value = json_insert(value, '$[#]', json(
  '{"type": "same_course", "name": "same_course", "weight": 2, "stage": null, "scope": null, "reason": null, "params": {}, "enabled": true}'
))
WHERE key = 'rules'
  AND NOT EXISTS (SELECT 1 FROM json_each(settings.value) WHERE json_extract(value, '$.name') = 'same_course');
