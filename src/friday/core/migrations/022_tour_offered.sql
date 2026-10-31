-- The tour opens by itself once, when setup first finishes, and is remembered here rather than by the window (31 Oct:
-- "make sure that when the initialization screen gets merged into the main, that it doesn't run every time"). Anyone
-- already through setup has had it.
INSERT OR IGNORE INTO kv (user_id, key, value)
  SELECT user_id, 'tour_offered', 'true' FROM kv WHERE key = 'setup_done' AND value = 'true';
