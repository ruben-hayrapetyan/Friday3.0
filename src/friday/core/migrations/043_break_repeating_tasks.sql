-- Repeating tasks on a break (21 Nov: "on vacation, errands/other repeated tasks should be turned off by default"):
-- NULL follows your default (Settings → Breaks), which doesn't plan them.
ALTER TABLE vacations ADD COLUMN plan_repeating INTEGER CHECK (plan_repeating IS NULL OR plan_repeating IN (0, 1));
