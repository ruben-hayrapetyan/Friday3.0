// Setup: a few questions when Friday first opens, so the defaults fit you instead of being changed one by one in
// Settings. Each starts from what Friday does now; Skip keeps those. All the answers are saved together at the end
// (`setup_save`, one change you can undo), and the tour follows. Again from Settings, search or the Help menu. The last
// step brings things in (Google Calendar, course feeds, a syllabus, Gmail), each optional and done the moment you do
// it, with the same controls as Settings → Integrations.

import { useQuery } from "@tanstack/react-query"
import { type ReactNode, useEffect, useState } from "react"
import { query, type Schemas } from "@/api/client"
import { Icon, Seg, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useInbox } from "@/inbox/InboxPage"
import { ampm, parseLength } from "@/lib/format"
import { CalendarChoice, saying } from "@/settings/calendarChoice"
import { ConnectedAccounts } from "@/settings/GoogleAccounts"
import { ConnectGoogle, GmailConnect, GmailSwitch, useGoogleAccess } from "@/settings/GoogleConnect"
import { AddFeed, Upload } from "@/settings/Integrations"
import { Modal } from "./Dialogs"
import { TimeInput as TimeBox } from "@/components/fr/TimeInput"
import { type Expect, SLEEP_HOURS } from "@/lib/ampm"

export type Answers = Schemas["SetupInput"]
type Calendar = Schemas["SetupCalendar"]

export const useSetup = () => useQuery({ queryKey: ["setup"], queryFn: () => query("setup") })

/** Hours typed any way: "6" is 6 hours here (a question about hours), "6.5h", "1h30", "90 min", "an hour and a
 * half"; to the nearest quarter hour. Null when it can't be read. */
export function readHours(text: string): number | null {
  const t = text.trim()
  if (!t) return null
  const minutes = /^\d+(\.\d+)?$/.test(t) ? Number(t) * 60 : parseLength(t)
  return minutes === null ? null : Math.round(minutes / 15) / 4
}

/** Whole days typed: "2", "2 days", "a day"; null otherwise. */
export function readDays(text: string): number | null {
  const m = /^\s*(\d+|a|one|an)\s*(days?)?\s*$/i.exec(text)
  return m ? (/^\d+$/.test(m[1]) ? Number(m[1]) : 1) : null
}

/** "6h", "1.5h", "45m". */
export function hoursLabel(v: number): string {
  return v < 1 ? `${Math.round(v * 60)}m` : `${v}h`
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
          <Amount picks={[3, 4, 5, 6, 8, 10]} value={a.normal_hours} min={1} max={16} onPick={(normal_hours) => set({ normal_hours, most_hours: Math.max(a.most_hours, normal_hours) })} label="A normal day" />
        </Question>
        <Question label="At most, on a heavy day">
          <Amount picks={[4, 6, 8, 10, 12]} value={a.most_hours} min={1} max={16} onPick={(most_hours) => set({ most_hours, normal_hours: Math.min(a.normal_hours, most_hours) })} label="At most, on a heavy day" />
        </Question>
      </>
    ),
  },
  {
    id: "focus",
    title: "Focus",
    note: "The longest Friday plans focused work in one go before a break or something else.",
    body: (a, set) => <Amount picks={[0.75, 1, 1.5, 2, 3, 4]} value={a.focus_hours} min={0.5} max={8} onPick={(focus_hours) => set({ focus_hours })} label="Longest stretch" />,
  },
  {
    id: "free",
    title: "Free time",
    note: "Time Friday keeps clear of work when it can. A deadline can still need it.",
    body: (a, set) => (
      <>
        <Question label="Weekday evenings">
          <Amount picks={[0, 1, 2, 3, 5]} names={{ 0: "None", 5: "All of it" }} value={a.evening_free} min={0} max={6} onPick={(evening_free) => set({ evening_free })} label="Weekday evenings" />
        </Question>
        {a.evening_free > 0 && (
          <Question label="Evenings start at">
            <span style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <Seg options={["17:00", "18:00", "19:00", "20:00"].map((t) => ({ value: t, label: ampm(t) }))} value={a.evening_from} onPick={(evening_from) => set({ evening_from })} size="big" label="Evenings start at" />
              <TimeInput value={a.evening_from} onPick={(evening_from) => set({ evening_from })} label="Evenings start at, another time" expect={{ hours: ["14:00", "23:59"] }} />
            </span>
          </Question>
        )}
        <Question label="Each weekend day">
          <Amount picks={[0, 2, 4, 6, 13]} names={{ 0: "None", 13: "All of it" }} value={a.weekend_free} min={0} max={13} onPick={(weekend_free) => set({ weekend_free })} label="Each weekend day" />
        </Question>
      </>
    ),
  },
  {
    id: "early",
    title: "Deadlines",
    note: "How early Friday aims to have work done. Exam prep is always planned in the days just before the exam.",
    body: (a, set) => (
      <Amount
        picks={[0, 1, 2, 3]}
        names={{ 0: "On the day", 1: "A day early", 2: "2 days early", 3: "3 days early" }}
        value={a.finish_early_days}
        min={0}
        max={7}
        read={readDays}
        say={(d) => `${d} day${d === 1 ? "" : "s"} early`}
        example="5 days"
        onPick={(finish_early_days) => set({ finish_early_days })}
        label="Finish work"
      />
    ),
  },
  {
    id: "calendars",
    title: "Your calendars",
    note: "For each: plan around its events, just show them (dashed, and work may go over them), or hide it. A hidden one comes back under Show whenever you want it.",
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
  {
    id: "bring",
    title: "Bring things in",
    note: "Classes, deadlines and events from where they already are. Each is optional and happens right away; they're all in Settings → Integrations too.",
    body: () => <BringIn />,
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

/** The last step: each source is added (or connected) the moment you do it, not with the answers. */
function BringIn() {
  const feeds = (useInbox().data?.sources ?? []).filter((s) => s.kind === "ics")
  const accounts = useGoogleAccess()?.accounts ?? []
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <Source icon="google-logo" title="Google Calendar" note="Its events become fixed time Friday plans around. Connect your school's account too, if you have one.">
        <ConnectedAccounts accounts={accounts} />
        <ConnectGoogle why={accounts.length ? "Google's page asks which account." : undefined} done="Choose the calendars it reads in Settings → Integrations." />
      </Source>
      <Source icon="rss" title="Course feeds" note="A calendar link from Canvas or your school; new dates go to your Inbox.">
        <AddFeed />
        {feeds.length > 0 && <span className="fr-kicker">Added: {feeds.map((f) => f.name).join(", ")}</span>}
      </Source>
      <Source icon="file-pdf" title="Syllabus" note="A PDF becomes classes, readings, assignments and exam prep, in your Inbox.">
        <span>
          <Upload />
        </span>
      </Source>
      <Source icon="envelope-simple" title="Gmail" note="Friday suggests due dates and events from your mail. It never sends or deletes.">
        <GmailSwitch />
        <GmailConnect />
      </Source>
    </div>
  )
}

function Source({ icon, title, note, children }: { icon: string; title: string; note: string; children: ReactNode }) {
  return (
    <div className="fr-row" style={{ display: "grid", gridTemplateColumns: "24px minmax(0,1fr)", gap: 12, padding: "12px 0" }}>
      <Icon name={icon} size={18} style={{ color: "var(--color-neutral-400)", paddingTop: 1 }} />
      <div style={{ display: "flex", flexDirection: "column", gap: 8, minWidth: 0 }}>
        <span style={{ display: "flex", flexDirection: "column", gap: 1 }}>
          <span style={{ fontWeight: 500 }}>{title}</span>
          <span className="fr-kicker" style={{ textWrap: "pretty" }}>
            {note}
          </span>
        </span>
        {children}
      </div>
    </div>
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

/** Any time, to the minute, shown on the Mac's clock (12-hour here). */
function TimeInput({ value, onPick, label, expect }: { value: string; onPick: (t: string) => void; label: string; expect?: Expect }) {
  return <TimeBox className="input tnum" step={300} value={value} onChange={(t) => t && onPick(t)} label={label} expect={expect} style={{ width: 130 }} />
}

/** Quick picks, and a box to type any other amount: hours by default ("6", "6.5h", "90 min"), or what `read` reads. */
function Amount(props: { picks: number[]; names?: Record<number, string>; value: number; min: number; max: number; onPick: (v: number) => void; label: string; read?: (text: string) => number | null; say?: (v: number) => string; example?: string }) {
  const { picks, names, value, min, max, onPick, label } = props
  const read = props.read ?? readHours
  const say = props.say ?? hoursLabel
  const picked = picks.includes(value)
  const [text, setText] = useState(picked ? "" : say(value))
  const [problem, setProblem] = useState<string | null>(null)
  useEffect(() => {
    // the other question moved this one (a heavy day is never less than a normal one): the box follows
    if (text.trim() && read(text) !== value && !problem) setText(picks.includes(value) ? "" : say(value))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])
  const type = (t: string) => {
    setText(t)
    if (!t.trim()) return setProblem(null)
    const v = read(t)
    if (v === null) return setProblem(`Type it like ${props.example ?? "6, 6.5h or 90 min"}`)
    if (v < min || v > max) return setProblem(`Between ${say(min)} and ${say(max)}`)
    setProblem(null)
    onPick(v)
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <span style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <Seg options={picks.map((v) => ({ value: v, label: names?.[v] ?? say(v) }))} value={picked && !text ? value : null} onPick={(v) => (setText(""), setProblem(null), onPick(v))} size="big" label={label} />
        <input
          className="input"
          value={text}
          onChange={(e) => type(e.target.value)}
          placeholder="Or type"
          aria-label={`${label}, typed`}
          style={{ width: 110, boxShadow: problem ? "0 0 0 1px var(--fr-due)" : !picked || text ? "0 0 0 1px var(--color-accent)" : undefined }}
        />
      </span>
      {problem && <span style={{ fontSize: 12, color: "var(--fr-due)" }}>{problem}</span>}
    </div>
  )
}

function TimeRow({ label, wake, bedtime, onWake, onBedtime }: { label: string; wake: string; bedtime: string; onWake: (t: string) => void; onBedtime: (t: string) => void }) {
  return (
    <div className="fr-stack" style={{ display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap" }}>
      <span style={{ fontSize: 13, fontWeight: 500, width: 90 }}>{label}</span>
      <span style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
        Up at <TimeInput value={wake} onPick={onWake} label={`${label}: up at`} expect={{ hours: SLEEP_HOURS.up }} />
      </span>
      <span style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
        Bed at <TimeInput value={bedtime} onPick={onBedtime} label={`${label}: bed at`} expect={{ hours: SLEEP_HOURS.bed }} />
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
        <span className="fr-kicker">
          {events ? `${events} event${events === 1 ? "" : "s"} in the next two weeks` : "Nothing in the next two weeks"} · {saying(c.shown !== false, c.busy !== false)}
        </span>
      </span>
      <CalendarChoice name={c.name} shown={c.shown !== false} busy={c.busy !== false} onPick={onChange} />
    </div>
  )
}
