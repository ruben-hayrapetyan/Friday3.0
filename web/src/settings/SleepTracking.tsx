// Track my sleep and Track my meals (Settings → Schedule, and Sleep & meals): each off until you turn it on. Logging
// a night or a meal, and putting one right, is in Sleep & meals, with what Friday learned from them; the Now
// bar offers the tap that fits the hour.

import { useNavigate } from "react-router"
import { Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useSettings } from "@/hooks/queries"
import { Field } from "./SettingsPage"

const SCHOOL_NIGHTS = ["sun", "mon", "tue", "wed", "thu"]
const WEEKDAY_MORNINGS = ["mon", "tue", "wed", "thu", "fri"]
const SHORT: Record<string, string> = { mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun" }

/** "Sunday to Thursday nights", "weekday mornings", or the days named. */
export function daysSaid(days: string[], field: "bedtime" | "wake"): string {
  const same = (group: string[]) => group.length === days.length && group.every((d) => days.includes(d))
  if (field === "bedtime" && same(SCHOOL_NIGHTS)) return "Sunday to Thursday nights"
  if (field === "bedtime" && same(["fri", "sat"])) return "Friday and Saturday nights"
  if (field === "wake" && same(WEEKDAY_MORNINGS)) return "Weekday mornings"
  if (field === "wake" && same(["sat", "sun"])) return "Weekend mornings"
  return `${days.map((d) => SHORT[d]).join(", ")} ${field === "bedtime" ? "nights" : "mornings"}`
}

/** One of the two switches, as Settings → Schedule shows it, with the way to Sleep & meals when it's on. */
export function Tracking({ what }: { what: "sleep" | "meals" }) {
  const settings = useSettings().data as Record<string, { on?: boolean }> | undefined
  const save = useCommand("settings_set", { label: () => "Saved" })
  const navigate = useNavigate()
  const key = what === "sleep" ? "sleep_tracking" : "meal_tracking"
  const on = !!settings?.[key]?.on
  const name = what === "sleep" ? "Track my sleep" : "Track my meals"
  const note =
    what === "sleep"
      ? "Optional. Tap “Done with work”, “Going to bed” and “I’m up” in the Now bar (or log a night in Sleep & meals); Friday learns your real bedtime, wake time, morning routine and wind-down before bed. Off, nothing is recorded or learned."
      : "Optional. Tap “Eating now” and “Done eating” in the Now bar (or log a meal in Sleep & meals); Friday learns when you eat, for how long and what you skip, and keeps your meal free while you eat. Off, nothing is recorded or learned."
  return (
    <Field name={name} note={note}>
      <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <Switch on={on} onToggle={() => save({ key, value: { ...settings?.[key], on: !on } })} label={name} />
        <span style={{ color: on ? "var(--color-text)" : "var(--color-neutral-400)" }}>{on ? "On" : "Off"}</span>
      </span>
      {on && (
        <button className="fr-link" onClick={() => navigate(`/body?tab=${what}`)} style={{ alignSelf: "flex-start", fontSize: 12 }}>
          {what === "sleep" ? "Log or fix a night in Sleep & meals" : "Log or fix a meal in Sleep & meals"}
        </button>
      )}
    </Field>
  )
}

export const TrackSleep = () => <Tracking what="sleep" />
export const TrackMeals = () => <Tracking what="meals" />
