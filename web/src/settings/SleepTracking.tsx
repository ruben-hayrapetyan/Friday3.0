// Track my sleep and Track my meals (Settings → Schedule, and Insights → Sleep and Meals): each off until you turn it on. Logging
// a night or a meal, and putting one right, is in Insights → Sleep and Meals, with what Friday learned from them; the Now
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

/** One of the two switches, as Settings → Schedule shows it, with the way to Insights → Sleep or Meals when it's on. */
export function Tracking({ what }: { what: "sleep" | "meals" }) {
  const settings = useSettings().data as Record<string, { on?: boolean }> | undefined
  const save = useCommand("settings_set", { label: () => "Saved" })
  const navigate = useNavigate()
  const key = what === "sleep" ? "sleep_tracking" : "meal_tracking"
  const on = !!settings?.[key]?.on
  const name = what === "sleep" ? "Track my sleep" : "Track my meals"
  const note =
    what === "sleep"
      ? "Tap “Done with work”, “Going to bed” and “I’m up” in the Now bar, and Friday learns your real bedtime, wake time and routines. Off, nothing is recorded."
      : "Tap “Eating now” and “Done eating” in the Now bar, and Friday learns when and how long you eat. Off, nothing is recorded."
  return (
    <Field name={name} note={note}>
      <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <Switch on={on} onToggle={() => save({ key, value: { ...settings?.[key], on: !on } })} label={name} />
        <span style={{ color: on ? "var(--color-text)" : "var(--color-neutral-400)" }}>{on ? "On" : "Off"}</span>
      </span>
      {on && (
        <button className="fr-link" onClick={() => navigate(`/insights?tab=${what}`)} style={{ alignSelf: "flex-start", fontSize: 12 }}>
          {what === "sleep" ? "Log or fix a night in Insights → Sleep" : "Log or fix a meal in Insights → Meals"}
        </button>
      )}
    </Field>
  )
}

export const TrackSleep = () => <Tracking what="sleep" />
export const TrackMeals = () => <Tracking what="meals" />
