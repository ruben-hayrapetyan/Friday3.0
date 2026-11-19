// Settings → Breaks (18 Nov): your breaks, each opening its popup, and what a new one starts with: how many things a
// day when Light, what pauses, meals and sleep. A break can say otherwise for itself.

import { Icon, Switch } from "@/components/fr/controls"
import { useSettings } from "@/hooks/queries"
import { useCommand } from "@/hooks/useCommand"
import { useShell } from "@/shell/ShellContext"
import { type Defaults, PauseValue, useBreakDefaults, useVacations } from "@/breaks/BreakDialog"
import { PauseChooser } from "@/breaks/PauseChooser"
import { BREAK_ICON, modeWords, rangeWords, WORK_AMOUNTS } from "@/breaks/words"
import { LengthField } from "@/todo/Pickers"
import { useState } from "react"
import { Field, SectionHead } from "./SettingsPage"

export function BreaksSection() {
  const { setBreakEdit, today } = useShell()
  const vacations = useVacations().data?.vacations ?? []
  const defaults = useBreakDefaults()
  const settings = useSettings().data as Record<string, unknown> | undefined
  const save = useCommand("settings_set", {
    label: () => "Saved",
    optimistic: (client, input) => client.setQueryData(["settings"], (was: Record<string, unknown> | undefined) => (was ? { ...was, [input.key]: input.value } : was)),
  })
  const set = (fields: Partial<Defaults>) => save({ key: "breaks", value: { ...(settings?.breaks as object), ...defaults, ...fields } })
  const [choosing, setChoosing] = useState(false)
  const coming = vacations.filter((v) => v.end >= today)
  const past = vacations.filter((v) => v.end < today)
  return (
    <>
      <SectionHead
        title="Breaks"
        note="Days off or light: vacations, holidays, a week away. Repeating events pause, and each day is a short list of things to do instead of times."
        right={
          <button className="btn btn-primary" onClick={() => setBreakEdit({})}>
            <Icon name="plus" size={14} /> Add a break
          </button>
        }
      />
      <Field name="Your breaks" note={coming.length ? "Click one to change it." : "None coming up. Friday suggests one in the Inbox when your calendar shows time away."}>
        {[...coming, ...past].map((v) => (
          <button key={v.id} className="fr-plain fr-hover" onClick={() => setBreakEdit({ id: v.id })} style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 8px", borderRadius: "var(--radius-md)", textAlign: "left", cursor: "pointer", opacity: v.end < today ? 0.7 : 1 }}>
            <Icon name={BREAK_ICON} size={14} style={{ color: "var(--fr-break)", flex: "none" }} />
            <span style={{ display: "flex", flexDirection: "column", minWidth: 0, flex: 1 }}>
              <span style={{ fontWeight: 500, overflowWrap: "anywhere" }}>{v.name}</span>
              <span className="tnum" style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>
                {rangeWords(v.start, v.end)} · {modeWords(v.mode, v.work_min)}
                {v.end < today ? " · over" : ""}
              </span>
            </span>
            <Icon name="caret-right" size={12} style={{ color: "var(--color-neutral-500)" }} />
          </button>
        ))}
      </Field>
      <Field name="A light day" note="About how much work a Light break day holds, however many things that is. Its list names tasks, not minutes.">
        <LengthField value={defaults.work_min} onPick={(m) => m && set({ work_min: m })} label="Work on a light day" amounts={WORK_AMOUNTS} unit=" a day" />
      </Field>
      <Field name="What pauses" note="Only repeating events pause; one-off events stay. With many calendars, search for one.">
        <PauseValue pause={defaults.pause} onClick={() => setChoosing(!choosing)} />
        {choosing && (
          <div className="fr-well" style={{ padding: 12 }}>
            <PauseChooser pause={defaults.pause} onChange={(pause) => set({ pause })} />
          </div>
        )}
      </Field>
      <Field name="Meals" note="Whether meals are planned on break days.">
        <label style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Switch on={defaults.plan_meals} onToggle={() => set({ plan_meals: !defaults.plan_meals })} label="Plan meals on break days" />
          {defaults.plan_meals ? "Planned as usual" : "Not planned"}
        </label>
      </Field>
      <Field name="Sleep" note="Whether your sleep schedule holds on break days.">
        <label style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Switch on={defaults.keep_sleep} onToggle={() => set({ keep_sleep: !defaults.keep_sleep })} label="Keep my sleep schedule on break days" />
          {defaults.keep_sleep ? "Your usual schedule" : "Not planned"}
        </label>
      </Field>
    </>
  )
}
