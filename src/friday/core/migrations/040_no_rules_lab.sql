-- The Rules lab is gone (15 Nov, the user: "i don't think we need a rules lab"; its ideas that worked live on the
-- Rules page): the saved value of its switch goes too, as reading settings refuses a key it doesn't know.
DELETE FROM settings WHERE key = 'rules_lab';
