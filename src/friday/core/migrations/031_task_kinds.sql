-- C97: Task and Work task, kinds for to-dos that aren't schoolwork. Anyone with kinds of their own saved gets the two,
-- once (deleting them afterwards keeps them gone); everyone else has them from the defaults. Kept in step with
-- core/presets.py.
UPDATE settings SET version = version + 1,
  value = json_set(value, '$.Task', json('{"when": "window", "amount": "fixed", "duration_units": 2, "shape": "one_sitting", "firmness": "hard"}'))
WHERE key = 'presets' AND json_extract(value, '$.Task') IS NULL;
UPDATE settings SET version = version + 1,
  value = json_set(value, '$."Work task"', json('{"when": "window", "amount": "fixed", "duration_units": 4, "shape": "split", "min_chunk_units": 2, "chunk_cost": 0.1, "firmness": "hard", "energy": "deep"}'))
WHERE key = 'presets' AND json_extract(value, '$."Work task"') IS NULL;
