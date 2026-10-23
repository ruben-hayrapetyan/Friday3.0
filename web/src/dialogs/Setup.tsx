// Setup: a few questions when Friday first opens, so the defaults fit you instead of being changed one by one in
// Settings. Each starts from what Friday does now; Skip keeps those. All the answers are saved together at the end
// (`setup_save`, one change you can undo), and the tour follows. Again from Settings, search or the Help menu.

import { useQuery } from "@tanstack/react-query"
import { type ReactNode, useEffect, useState } from "react"
import { query, type Schemas } from "@/api/client"
import { Icon, Seg, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { ampm } from "@/lib/format"
import { Modal } from "./Dialogs"

export type Answers = Schemas["SetupInput"]
type Calendar = Schemas["SetupCalendar"]

export const useSetup = () => useQuery({ queryKey: ["setup"], queryFn: () => query("setup") })

/** Half-hour times from `from` to `to` o'clock (past midnight when `to` > 24), with `current` among them. */
export function timeOptions(from: number, to: number, current: string): { value: string; label: string }[] {
  const all = Array.from({ length: (to - from) * 2 + 1 }, (_, i) => `${String(Math.floor(from + i / 2) % 24).padStart(2, "0")}:${i % 2 ? "30" : "00"}`)
  const values = all.includes(current) ? all : [current, ...all]
  return values.map((value) => ({ value, label: ampm(value) }))
}

/** Hours as Seg options: "1h", "1.5h"; `none` and `all` name the ends. */
function hourOptions(values: number[], none?: string, all?: { value: number; label: string }) {
  return values.map((v) => ({ value: v, label: v === 0 && none ? none : all && v === all.value ? all.label : v < 1 ? `${v * 60}m` : `${v}h` }))
}

/** A value among `values`, adding it when you'd chosen something they don't offer (in Settings). */
function withValue(values: number[], value: number): number[] {
  return values.includes(value) ? values : [...values, value].sort((a, b) => a - b)
}

interface Step {
  id: string
  title: string
  note: string
  body: (a: Answers, set: (change: Partial<Answers>) => void, events: Record<string, number>) => ReactNode
}

const STEPS: Step[] = [
  {
    id: "day",
    title: "Your day",
    note: "When you usually get up and go to bed. Friday plans nothing in your sleep.",
    body: (a, set) => {
      const different = a.weekend_wake !== a.wake || a.weekend_bedtime !== a.bedtime
      return (
        <>
          <TimeRow label={different ? "Weekdays" : "Every day"} wake={a.wake} bedtime={a.bedtime} onWake={(wake) => set(different ? { wake } : { wake, weekend_wake: wake })} onBedtime={(bedtime) => set(different ? { bedtime } : { bedtime, weekend_bedtime: bedtime })} />
          {different && <TimeRow label="Weekends" wake={a.weekend_wake} bedtime={a.weekend_bedtime} onWake={(weekend_wake) => set({ weekend_wake })} onBedtime={(weekend_bedtime) => set({ weekend_bedtime })} />}
          <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
            <Switch on={different} onToggle={() => set(different ? { weekend_wake: a.wake, weekend_bedtime: a.bedtime } : { weekend_wake: shift(a.wake, 90), weekend_bedtime: shift(a.bedtime, 60) })} label="Weekends are different" />
            Weekends are different
          </label>
        </>
      )
    },
  },
  {
    id: "load",
    title: "How much work in a day",
    note: "Friday aims for a normal day, and goes up to the most only when deadlines need it.",
    body: (a, set) => (
      <>
        <Question label="A normal day">
          <Seg options={hourOptions(withValue([3, 4, 5, 6, 8, 10], a.normal_hours))} value={a.normal_hours} onPick={(normal_hours) => set({ normal_hours, most_hours: Math.max(a.most_hours, normal_hours) })} size="big" label="A normal day" />
        </Question>
        <Question label="At most, on a heavy day">
          <Seg options={hourOptions(withValue([4, 6, 8, 10, 12], a.most_hours))} value={a.most_hours} onPick={(most_hours) => set({ most_hours, normal_hours: Math.min(a.normal_hours, most_hours) })} size="big" label="At most" />
        </Question>
      </>
    ),
  },
  {
    id: "focus",
    title: "Focus",
    note: "The longest Friday plans focused work in one go before a break or something else.",
    body: (a, set) => <Seg options={hourOptions(withValue([0.75, 1, 1.5, 2, 3, 4], a.focus_hours))} value={a.focus_hours} onPick={(focus_hours) => set({ focus_hours })} size="big" label="Longest stretch" />,
  },
  {
    id: "free",
    title: "Free time",
    note: "Time Friday keeps clear of work when it can. A deadline can still need it.",
    body: (a, set) => (
      <>
        <Question label="Weekday evenings">
          <Seg options={hourOptions(withValue([0, 1, 2, 3, 5], a.evening_free), "None", { value: 5, label: "All of it" })} value={a.evening_free} onPick={(evening_free) => set({ evening_free })} size="big" label="Weekday evenings" />
        </Question>
        {a.evening_free > 0 && (
          <Question label="Evenings start at">
            <Seg options={["17:00", "18:00", "19:00", "20:00"].map((t) => ({ value: t, label: ampm(t) }))} value={a.evening_from} onPick={(evening_from) => set({ evening_from })} size="big" label="Evenings start at" />
          </Question>
        )}
        <Question label="Each weekend day">
          <Seg options={hourOptions(withValue([0, 2, 4, 6, 13], a.weekend_free), "None", { value: 13, label: "All of it" })} value={a.weekend_free} onPick={(weekend_free) => set({ weekend_free })} size="big" label="Each weekend day" />
        </Question>
      </>
    ),
  },
  {
    id: "early",
    title: "Deadlines",
    note: "How early Friday aims to have work done. Exam prep is always planned in the days just before the exam.",
    body: (a, set) => (
      <Seg
        options={[
          { value: 0, label: "On the day" },
          { value: 1, label: "A day early" },
          { value: 2, label: "2 days early" },
          { value: 3, label: "3 days early" },
        ]}
        value={a.finish_early_days}
        onPick={(finish_early_days) => set({ finish_early_days })}
        size="big"
        label="Finish work"
      />
    ),
  },
  {
    id: "calendars",
    title: "Your calendars",
    note: "Hidden ones stay off your calendar until you switch them on under Show. Busy ones keep Friday from planning work over their events.",
    body: (a, set, events) => (
      <div style={{ display: "flex", flexDirection: "column" }}>
        {(a.calendars ?? []).map((c) => (
          <CalendarRow key={c.name} c={c} events={events[c.name] ?? 0} onChange={(change) => set({ calendars: (a.calendars ?? []).map((x) => (x.name === c.name ? { ...x, ...change } : x)) })} />
        ))}
      </div>
    ),
  },
  {
    id: "brief",
    title: "Morning brief",
    note: "Each morning, what's planned and what matters most today, with a notification half an hour after you get up.",
    body: (a, set) => (
      <Seg
        options={[
          { value: "on", label: "Yes, show it" },
          { value: "off", label: "No thanks" },
        ]}
        value={a.brief ? "on" : "off"}
        onPick={(v) => set({ brief: v === "on" })}
        size="big"
        label="Morning brief"
      />
    ),
  },
]

/** The questions to ask: the calendars only when there are some. */
export function stepsFor(answers: Answers): string[] {
  return STEPS.filter((s) => s.id !== "calendars" || (answers.calendars ?? []).length > 0).map((s) => s.id)
}

/** A time `minutes` later, as "HH:MM". */
export function shift(hhmm: string, minutes: number): string {
  const [h, m] = hhmm.split(":").map(Number)
  const total = (((h * 60 + m + minutes) % 1440) + 1440) % 1440
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`
}

export function SetupDialog({ onClose }: { onClose: () => void }) {
  const setup = useSetup().data
  const save = useCommand("setup_save", { label: (o) => o.result.message ?? "Saved" })
  const [draft, setDraft] = useState<Answers | null>(null)
  const [n, setN] = useState(0)
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    if (setup && !draft) setDraft(setup.answers as unknown as Answers)
  }, [setup, draft])
  if (!draft || !setup) return null
  const ids = stepsFor(draft)
  const step = STEPS.find((s) => s.id === ids[Math.min(n, ids.length - 1)])!
  const last = n >= ids.length - 1
  const set = (change: Partial<Answers>) => setDraft({ ...draft, ...change })
  const finish = async (answers: Answers) => {
    setSaving(true)
    const out = await save(answers)
    setSaving(false)
    if (out) onClose()
  }
  return (
    <Modal onClose={setup.done ? onClose : () => undefined} width={600}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span className="fr-kicker" style={{ flex: 1 }}>
          {setup.done ? "Setup" : "Setting up Friday"} · {n + 1} of {ids.length}
        </span>
        <button className="fr-plain fr-hover-text" onClick={() => (setup.done ? onClose() : finish(setup.answers as unknown as Answers))} disabled={saving} style={{ fontSize: 12, color: "var(--color-neutral-500)" }}>
          {setup.done ? "Cancel" : "Skip: keep Friday's guesses"}
        </button>
      </div>
      <div style={{ display: "flex", gap: 4 }} aria-hidden>
        {ids.map((id, i) => (
          <span key={id} style={{ flex: 1, height: 3, borderRadius: 2, background: i <= n ? "var(--color-accent)" : "color-mix(in srgb, var(--color-text) 12%, transparent)" }} />
        ))}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span className="fr-h" style={{ fontSize: 26 }}>
          {step.title}
        </span>
        <span style={{ color: "var(--color-neutral-300)", textWrap: "pretty", lineHeight: 1.45 }}>{step.note}</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 14, minHeight: 200, maxHeight: "50vh", overflowY: "auto", overflowX: "hidden" }}>{step.body(draft, set, setup.events ?? {})}</div>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        {!setup.done && n === 0 && <span style={{ fontSize: 12, color: "var(--color-neutral-500)", flex: 1 }}>Change any of it later in Settings.</span>}
        <span style={{ flex: 1 }} />
        {n > 0 && (
          <button className="btn btn-ghost" onClick={() => setN(n - 1)} disabled={saving}>
            Back
          </button>
        )}
        <button className="btn btn-primary" onClick={() => (last ? finish(draft) : setN(n + 1))} disabled={saving} autoFocus>
          {last ? (saving ? "Saving…" : "Done") : "Next"}
          {!last && <Icon name="arrow-right" size={14} />}
        </button>
      </div>
    </Modal>
  )
}

function Question({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 0 }}>
      <span style={{ fontSize: 13, fontWeight: 500 }}>{label}</span>
      <div style={{ overflowX: "auto", maxWidth: "100%" }}>{children}</div>
    </div>
  )
}

function TimeRow({ label, wake, bedtime, onWake, onBedtime }: { label: string; wake: string; bedtime: string; onWake: (t: string) => void; onBedtime: (t: string) => void }) {
  const select = (value: string, options: { value: string; label: string }[], onPick: (t: string) => void, aria: string) => (
    <select className="input" value={value} onChange={(e) => onPick(e.target.value)} aria-label={aria} style={{ width: 120 }}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  )
  return (
    <div className="fr-stack" style={{ display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap" }}>
      <span style={{ fontSize: 13, fontWeight: 500, width: 90 }}>{label}</span>
      <span style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
        Up at {select(wake, timeOptions(5, 12, wake), onWake, `${label}: up at`)}
      </span>
      <span style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
        Bed at {select(bedtime, timeOptions(20, 27, bedtime), onBedtime, `${label}: bed at`)}
      </span>
    </div>
  )
}

function CalendarRow({ c, events, onChange }: { c: Calendar; events: number; onChange: (change: Partial<Calendar>) => void }) {
  return (
    <div className="fr-row" style={{ display: "flex", gap: 12, alignItems: "center", padding: "8px 0", flexWrap: "wrap" }}>
      <span style={{ flex: "1 1 160px", minWidth: 0, display: "flex", flexDirection: "column" }}>
        <span style={{ fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={c.name}>
          {c.name}
        </span>
        <span className="fr-kicker">{events ? `${events} event${events === 1 ? "" : "s"} in the next two weeks` : "Nothing in the next two weeks"}</span>
      </span>
      <Seg
        options={[
          { value: "shown", label: "Show" },
          { value: "hidden", label: "Hide" },
        ]}
        value={c.shown ? "shown" : "hidden"}
        onPick={(v) => onChange({ shown: v === "shown" })}
        label={`Show ${c.name}`}
      />
      <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12 }}>
        <Switch on={!!c.busy} onToggle={() => onChange({ busy: !c.busy })} label={`${c.name} counts as busy`} />
        Busy
      </label>
    </div>
  )
}
