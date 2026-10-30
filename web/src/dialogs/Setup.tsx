// Setup: the questions when Friday first opens, so the defaults fit you instead of being changed one by one in
// Settings. Each starts from what Friday does now; Skip keeps those. All the answers are saved together at the end
// (`setup_save`, one change you can undo), and the tour follows. Again from Settings, search or the Help menu. Near
// the end the AI is chosen and things are brought in (Google Calendar, course feeds, a syllabus, Gmail), each
// optional and done the moment you do it, with the same controls as Settings → Integrations.
//
// 29 Oct, after a pixel game: "the intro is going in the right direction. i dont like the pixel art or the sprite
// though. look at how opal the app on the app store does its intro and take inspiration but for friday". As Opal
// does it: a dark stage, one question a screen under a picture of the answer that moves as you choose
// (onboard/Visuals.tsx), a progress bar along the top, then "Building your week…", your week in numbers, and hold to
// start, Friday's ring where Opal has its gem, your week building itself behind it. No gradients (29 Oct: "i don't
// want gradients in the startup page"): every colour flat.

import "./setup.css"
import { useQuery } from "@tanstack/react-query"
import { type CSSProperties, type ReactNode, useEffect, useRef, useState } from "react"
import { query, type Schemas } from "@/api/client"
import { Icon, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useInbox } from "@/inbox/InboxPage"
import { SLEEP_HOURS } from "@/lib/ampm"
import { ampm, parseLength } from "@/lib/format"
import { AiConnect } from "@/settings/AiConnect"
import { CHOICES, choiceOf, fromChoice, saying } from "@/settings/calendarChoice"
import { ConnectedAccounts } from "@/settings/GoogleAccounts"
import { ConnectGoogle, GmailConnect, GmailSwitch, useGoogleAccess } from "@/settings/GoogleConnect"
import { AddFeed, Upload } from "@/settings/Integrations"
import { BriefCard, Count, DeadlineLine, Evening, FocusDial, freeSpan, minutesOf, Ring, Sky, WeekBars, Weekend, WeekGrid } from "./onboard/Visuals"
import { Choices, HourBar, Other, Source, TimeCard } from "./SetupParts"
import { ALL_EVENING, ALL_WEEKEND, shift, sleepHours, weekOf } from "./setupWeek"

export { shift }
export type Answers = Schemas["SetupInput"]
type Calendar = Schemas["SetupCalendar"]

const vars = (v: Record<string, string | number | undefined>) => v as CSSProperties

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

/** "an hour", "1.5 hours", "45 minutes": an amount as Friday says it. */
export function hoursWords(v: number): string {
  if (v < 1) return `${Math.round(v * 60)} minutes`
  return v === 1 ? "an hour" : `${v} hours`
}

const daysEarly = (d: number) => (d === 0 ? "on the day" : d === 1 ? "a day early" : `${d} days early`)

/** The draft with calendars Friday has come to read since setup opened (connected a moment ago, in Bring things in)
 * added, as the server would first set them; the ones already there keep what you chose. */
export function withCalendars(draft: Answers, listed: Calendar[] | null | undefined): Answers {
  const have = new Set((draft.calendars ?? []).map((c) => c.name))
  const fresh = (listed ?? []).filter((c) => !have.has(c.name))
  return fresh.length ? { ...draft, calendars: [...(draft.calendars ?? []), ...fresh] } : draft
}

// In order: hello; your day from getting up to bed, work, focus, deadlines, evenings and weekends; mornings; the AI and
// where your things are (the calendars after bringing them in, 29 Oct, and only when there are some); then Friday
// builds the week, shows it, and you hold to start.
const STORY = ["hello", "wake", "bed", "work", "heavy", "focus", "deadline", "evening", "weekend", "brief", "ai", "bring", "calendars", "build", "reveal", "start"]

/** The screens for these answers. */
export function storyFor(answers: Answers): string[] {
  return STORY.filter((id) => id !== "calendars" || (answers.calendars ?? []).length > 0)
}

/** Your answers as the end shows them, each a way back to where it was asked. */
export function badgesOf(a: Answers): { label: string; value: string; step: string }[] {
  const free = a.evening_free <= 0 ? "none" : a.evening_free >= ALL_EVENING ? `from ${ampm(a.evening_from)}` : `${hoursLabel(a.evening_free)} from ${ampm(a.evening_from)}`
  const weekend = a.weekend_free <= 0 ? "none" : a.weekend_free >= ALL_WEEKEND ? "all day" : `${hoursLabel(a.weekend_free)} a day`
  return [
    { label: "Up", value: ampm(a.wake), step: "wake" },
    { label: "Bed", value: ampm(a.bedtime), step: "bed" },
    { label: "Work", value: a.most_hours > a.normal_hours ? `${hoursLabel(a.normal_hours)}, up to ${hoursLabel(a.most_hours)}` : hoursLabel(a.normal_hours), step: "work" },
    { label: "Focus", value: hoursLabel(a.focus_hours), step: "focus" },
    { label: "Done", value: daysEarly(a.finish_early_days), step: "deadline" },
    { label: "Evenings free", value: free, step: "evening" },
    { label: "Weekends free", value: weekend, step: "weekend" },
    { label: "Morning brief", value: a.brief ? "yes" : "no", step: "brief" },
  ]
}

/** Your week in four numbers, for the reveal: sleep a night, work a week, hours kept yours, and done early. */
export function numbersOf(a: Answers): { sleep: number; work: number; free: number; early: number } {
  const span = (s: [number, number] | null) => (s ? (s[1] - s[0]) / 60 : 0)
  return {
    sleep: sleepHours(a).weekday,
    work: weekOf(a, "ready").workHours,
    free: Math.round((span(freeSpan(a, false)) * 5 + span(freeSpan(a, true)) * 2) * 2) / 2,
    early: a.finish_early_days,
  }
}

interface Ctx {
  events: Record<string, number>
  go: (id: string) => void
}

interface Step {
  kicker?: string
  title: (a: Answers) => string
  note?: (a: Answers) => string
  picture?: (a: Answers) => ReactNode
  control?: (a: Answers, set: (change: Partial<Answers>) => void, ctx: Ctx) => ReactNode
  go?: string
  wide?: boolean // the answer needs the room: no picture
}

const WAKES = ["06:30", "07:00", "07:30", "08:00", "08:30", "09:00"]
const BEDS = ["22:30", "23:00", "23:30", "00:00", "00:30", "01:00"]
const FOCUS_PICKS = [0.75, 1, 1.5, 2, 3, 4]
const FOCUS_NOTES: Record<number, string> = { 0.75: "Short sprints, many breaks", 1: "About a lecture's length", 1.5: "Most of a problem set", 2: "A long sitting", 3: "Deep work, few breaks", 4: "As long as it takes" }
const EARLY_TITLES = ["On the day", "A day early", "2 days early", "3 days early"]
const EARLY_NOTES = ["Done by the deadline itself", "A day spare for surprises", "Room for a bad day", "Done well ahead"]
const EVENINGS = ["17:00", "18:00", "19:00", "20:00"]

/** A time to pick: a row of the usual ones, and the exact one stepped or typed. */
function TimePick({ value, presets, label, glyph, expect, onPick }: { value: string; presets: string[]; label: string; glyph: string; expect: { hours: readonly [string, string] }; onPick: (t: string) => void }) {
  return (
    <div className="st-group">
      <div className="st-chips" role="radiogroup" aria-label={`${label}: the usual times`}>
        {presets.map((t) => (
          <button key={t} type="button" role="radio" aria-checked={value === t} className="st-chip" onClick={() => onPick(t)}>
            {ampm(t)}
          </button>
        ))}
      </div>
      <TimeCard glyph={<Icon name={glyph} fill size={22} />} hue="var(--ob-gold)" label={label} value={value} expect={expect} onPick={onPick} />
    </div>
  )
}

const STEPS: Record<string, Step> = {
  hello: {
    title: () => "Your week, planned around your life.",
    note: () => "A few questions about how your days go, and Friday builds your first week from them. About a minute.",
    go: "Get started",
  },
  wake: {
    kicker: "Mornings",
    title: () => "When do you usually get up?",
    picture: (a) => <Sky minutes={minutesOf(a.wake)} />,
    control: (a, set) => <TimePick value={a.wake} presets={WAKES} label="Up at" glyph="sun-horizon" expect={{ hours: SLEEP_HOURS.up }} onPick={(wake) => set(a.weekend_wake === a.wake ? { wake, weekend_wake: wake } : { wake })} />,
  },
  bed: {
    kicker: "Nights",
    title: () => "And when do you go to bed?",
    note: () => "Friday never plans anything while you sleep.",
    picture: (a) => <Sky minutes={minutesOf(a.bedtime)} caption={`${hoursLabel(sleepHours(a).weekday)} of sleep a night`} />,
    control: (a, set) => {
      const different = a.weekend_wake !== a.wake || a.weekend_bedtime !== a.bedtime
      return (
        <div className="st-group">
          <TimePick value={a.bedtime} presets={BEDS} label="Bed at" glyph="moon-stars" expect={{ hours: SLEEP_HOURS.bed }} onPick={(bedtime) => set(different ? { bedtime } : { bedtime, weekend_bedtime: bedtime })} />
          <label className="st-toggle">
            <Switch on={different} onToggle={() => set(different ? { weekend_wake: a.wake, weekend_bedtime: a.bedtime } : { weekend_wake: shift(a.wake, 90), weekend_bedtime: shift(a.bedtime, 60) })} label="Weekends are different" />
            Weekends are different
          </label>
          {different && (
            <div className="ob-pair">
              <TimeCard glyph={<Icon name="sun-horizon" fill size={20} />} hue="var(--ob-gold)" label="Up at, weekends" value={a.weekend_wake} expect={{ hours: SLEEP_HOURS.up }} onPick={(weekend_wake) => set({ weekend_wake })} />
              <TimeCard glyph={<Icon name="moon-stars" fill size={20} />} hue="var(--ob-class)" label="Bed at, weekends" value={a.weekend_bedtime} expect={{ hours: SLEEP_HOURS.bed }} onPick={(weekend_bedtime) => set({ weekend_bedtime })} />
            </div>
          )}
        </div>
      )
    },
  },
  work: {
    kicker: "Work",
    title: () => "How much work fits in a normal day?",
    note: () => "Friday aims for this, and goes past it only when deadlines need it.",
    picture: (a) => <WeekBars normal={a.normal_hours} most={a.most_hours} heavy={false} />,
    control: (a, set) => (
      <div className="st-group">
        <HourBar label="On a normal day" value={a.normal_hours} min={1} segments={12} say={hoursLabel} onPick={(normal_hours) => set({ normal_hours, most_hours: Math.max(a.most_hours, normal_hours) })} />
        <Other value={a.normal_hours} picked={Number.isInteger(a.normal_hours)} read={readHours} say={hoursLabel} min={1} max={16} example="6.5h or 90 min" ask="Type an amount" label="A normal day, typed" onPick={(normal_hours) => set({ normal_hours, most_hours: Math.max(a.most_hours, normal_hours) })} />
      </div>
    ),
  },
  heavy: {
    kicker: "Work",
    title: () => "And when deadlines pile up?",
    note: () => "The most work Friday will put in one day.",
    picture: (a) => <WeekBars normal={a.normal_hours} most={a.most_hours} heavy />,
    control: (a, set) => (
      <div className="st-group">
        <HourBar label="At most, on a heavy day" value={a.most_hours} min={1} segments={16} base={a.normal_hours} say={hoursLabel} onPick={(most_hours) => set({ most_hours, normal_hours: Math.min(a.normal_hours, most_hours) })} />
        <Other value={a.most_hours} picked={Number.isInteger(a.most_hours)} read={readHours} say={hoursLabel} min={1} max={16} example="10.5h" ask="Type an amount" label="At most, typed" onPick={(most_hours) => set({ most_hours, normal_hours: Math.min(a.normal_hours, most_hours) })} />
      </div>
    ),
  },
  focus: {
    kicker: "Focus",
    title: () => "How long can you work in one go?",
    picture: (a) => <FocusDial hours={a.focus_hours} />,
    control: (a, set) => (
      <>
        <Choices label="Longest stretch" value={FOCUS_PICKS.includes(a.focus_hours) ? a.focus_hours : null} onPick={(focus_hours) => set({ focus_hours })} choices={FOCUS_PICKS.map((v) => ({ value: v, title: hoursWords(v).replace(/^an/, "An"), note: FOCUS_NOTES[v] }))} />
        <Other value={a.focus_hours} picked={FOCUS_PICKS.includes(a.focus_hours)} read={readHours} say={hoursLabel} min={0.5} max={8} example="2.5h or 100 min" ask="Another length" label="Longest stretch, typed" onPick={(focus_hours) => set({ focus_hours })} />
      </>
    ),
  },
  deadline: {
    kicker: "Deadlines",
    title: () => "An essay's due Friday at 5pm. When do you want it done?",
    note: () => "Exam prep always goes in the days just before the exam.",
    picture: (a) => <DeadlineLine early={a.finish_early_days} />,
    control: (a, set) => (
      <>
        <Choices label="Finish work" value={[0, 1, 2, 3].includes(a.finish_early_days) ? a.finish_early_days : null} onPick={(finish_early_days) => set({ finish_early_days })} choices={[0, 1, 2, 3].map((d) => ({ value: d, title: EARLY_TITLES[d], note: EARLY_NOTES[d] }))} />
        <Other value={a.finish_early_days} picked={[0, 1, 2, 3].includes(a.finish_early_days)} read={readDays} say={(d) => `${d} day${d === 1 ? "" : "s"} early`} min={0} max={7} example="5 days" ask="Further ahead" label="Days early, typed" onPick={(finish_early_days) => set({ finish_early_days })} />
      </>
    ),
  },
  evening: {
    kicker: "Evenings",
    title: () => "How much of each evening stays yours?",
    note: () => "Time Friday keeps clear of work when it can. A deadline can still need it.",
    picture: (a) => <Evening a={a} />,
    control: (a, set) => (
      <div className="st-group">
        <HourBar label="Of each weekday evening" value={a.evening_free} min={0} segments={ALL_EVENING} names={{ 0: "None", [ALL_EVENING]: "All of it" }} hue="var(--ob-free)" say={hoursLabel} onPick={(evening_free) => set({ evening_free })} />
        {a.evening_free > 0 && (
          <div className="st-chips" role="radiogroup" aria-label="Evenings start at">
            <span className="st-label">From</span>
            {EVENINGS.map((t) => (
              <button key={t} type="button" role="radio" aria-checked={a.evening_from === t} className="st-chip" onClick={() => set({ evening_from: t })}>
                {ampm(t)}
              </button>
            ))}
          </div>
        )}
      </div>
    ),
  },
  weekend: {
    kicker: "Weekends",
    title: () => "And of each weekend day?",
    picture: (a) => <Weekend a={a} />,
    control: (a, set) => <HourBar label="Of each weekend day" value={a.weekend_free} min={0} segments={ALL_WEEKEND} names={{ 0: "None", [ALL_WEEKEND]: "All of it" }} hue="var(--ob-free)" say={hoursLabel} onPick={(weekend_free) => set({ weekend_free })} />,
  },
  brief: {
    kicker: "Mornings",
    title: () => "Start each day with a brief?",
    note: () => "When you first open Friday each morning: what's planned, and what matters most.",
    picture: (a) => <BriefCard on={a.brief} />,
    control: (a, set) => (
      <Choices
        one
        label="Morning brief"
        value={a.brief ? "on" : "off"}
        onPick={(v) => set({ brief: v === "on" })}
        choices={[
          { value: "on", title: "Yes, every morning", note: "A minute's read, then your plan." },
          { value: "off", title: "No thanks", note: "Straight to your plan. It's in Settings if you change your mind." },
        ]}
      />
    ),
  },
  ai: {
    kicker: "Your AI",
    title: () => "Which AI should Friday read with?",
    note: () => "It reads syllabi and mail and understands what you type. Friday plans without one, so you can skip this.",
    control: () => <AiConnect compact />,
    wide: true,
  },
  bring: {
    kicker: "Bring things in",
    title: () => "Where are your classes and deadlines now?",
    note: () => "Each happens right away and is optional; they're all in Settings → Integrations too.",
    control: () => <BringIn />,
    wide: true,
  },
  calendars: {
    kicker: "Your calendars",
    title: () => "What should Friday do with each calendar?",
    note: () => "Plan around its events, just show them, or hide it.",
    control: (a, set, ctx) => (
      <div className="st-group">
        {(a.calendars ?? []).map((c, i) => (
          <CalendarCard key={c.name} c={c} events={ctx.events[c.name] ?? 0} i={i} onChange={(change) => set({ calendars: (a.calendars ?? []).map((x) => (x.name === c.name ? { ...x, ...change } : x)) })} />
        ))}
      </div>
    ),
    wide: true,
  },
  build: { title: () => "Building your week…" },
  reveal: { kicker: "Your week", title: () => "Here's your week.", go: "Continue" },
  start: { title: () => "Ready when you are.", note: () => "Hold to start planning." },
}

const BUILDING = ["Reading your nights", "Keeping your evenings", "Fitting work around your classes", "Leaving room before deadlines"]

export function SetupDialog({ onClose }: { onClose: () => void }) {
  const at = useRef("hello")
  // Read again every few seconds while things are brought in: a calendar connected then is asked about next.
  const setup = useQuery({ queryKey: ["setup"], queryFn: () => query("setup"), refetchInterval: () => (at.current === "bring" ? 3000 : false) }).data
  const save = useCommand("setup_save", { label: (o) => o.result.message ?? "Saved" })
  const [draft, setDraft] = useState<Answers | null>(null)
  // While building it (`pnpm dev` only), ?step=focus opens at that screen.
  const jump = import.meta.env.DEV ? new URLSearchParams(location.search).get("step") : null
  const [n, setN] = useState(0)
  const [back, setBack] = useState(false)
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    if (!setup) return
    setDraft((d) => (d ? withCalendars(d, setup.answers.calendars as Calendar[]) : (setup.answers as unknown as Answers)))
  }, [setup])
  useEffect(() => {
    if (jump && draft) setN(Math.max(0, storyFor(draft).indexOf(jump)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [!!draft])
  const ids = draft ? storyFor(draft) : STORY
  const id = ids[Math.min(n, ids.length - 1)]
  at.current = id
  const step = STEPS[id]
  const done = !!setup?.done
  const finish = async (answers: Answers) => {
    setSaving(true)
    const out = await save(answers)
    setSaving(false)
    if (out) onClose()
  }
  const to = (next: number) => {
    setBack(next < n)
    setN(Math.max(0, Math.min(ids.length - 1, next)))
  }
  const next = () => to(n + 1)
  // Building the week takes a moment, as Opal's report does, then shows it.
  useEffect(() => {
    if (id !== "build") return
    const timer = setTimeout(next, 3400)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      if (e.key === "Escape" && done) return onClose()
      if (e.key !== "Enter" || e.shiftKey || e.metaKey || e.ctrlKey || e.altKey || saving) return
      if (target?.closest("input, textarea, select, button, a, [contenteditable]")) return // they answer Return themselves
      if (id === "build" || id === "start") return
      e.preventDefault()
      next()
    }
    window.addEventListener("keydown", key)
    return () => window.removeEventListener("keydown", key)
  })
  if (!draft || !setup) return null
  const set = (change: Partial<Answers>) => setDraft({ ...draft, ...change })
  const ctx: Ctx = { events: setup.events ?? {}, go: (s) => to(ids.indexOf(s)) }
  const title = id === "hello" && done ? "Fit Friday to your week again." : step.title(draft)
  const note = id === "hello" && done ? "Your answers are filled in: change what's different." : step.note?.(draft)
  const asking = !["hello", "build", "reveal", "start"].includes(id)
  return (
    <div className="st-stage ob-stage" role="dialog" aria-modal="true" aria-labelledby="ob-title" data-screen={id}>
      <header className="ob-top">
        {n > 0 && id !== "build" ? (
          <button type="button" className="ob-back" onClick={() => to(n - 1)} aria-label="Back" disabled={saving}>
            <Icon name="caret-left" size={20} />
          </button>
        ) : (
          <span className="ob-back" />
        )}
        <div className="ob-progress" role="progressbar" aria-valuemin={0} aria-valuemax={ids.length - 1} aria-valuenow={n} aria-label="Setup">
          <i style={vars({ "--p": n / (ids.length - 1) })} />
        </div>
        <button type="button" className="ob-skip" onClick={() => (done ? onClose() : finish(setup.answers as unknown as Answers))} disabled={saving}>
          {done ? "Cancel" : "Skip"}
        </button>
      </header>
      <main className="ob-main">
        <section key={id} className="ob-screen" data-back={back || undefined} data-wide={step.wide || undefined}>
          {id === "hello" && (
            <div className="ob-hero">
              <Ring size={190} />
            </div>
          )}
          {step.picture && <div className="ob-picture">{step.picture(draft)}</div>}
          {id === "build" && <Building />}
          {(step.kicker || asking) && <div className="ob-kicker ob-in">{step.kicker}</div>}
          {id !== "build" && (
            <h1 id="ob-title" className="ob-title" data-big={id === "hello" || id === "start" || undefined}>
              <Words text={title} />
            </h1>
          )}
          {note && id !== "start" && <p className="ob-note ob-in" style={vars({ "--i": 3 })}>{note}</p>}
          {step.control && <div className="ob-control">{step.control(draft, set, ctx)}</div>}
          {id === "reveal" && <Reveal a={draft} go={ctx.go} />}
          {id === "start" && <Hold onDone={() => finish(draft)} busy={saving} />}
        </section>
      </main>
      {id !== "build" && id !== "start" && (
        <footer className="ob-foot">
          <button type="button" className="ob-go" onClick={next} disabled={saving}>
            {step.go ?? "Continue"}
          </button>
        </footer>
      )}
    </div>
  )
}

/** A headline arriving a word at a time. */
function Words({ text }: { text: string }) {
  return (
    <>
      {text.split(" ").map((word, i) => (
        <span key={`${i}${word}`} className="ob-word" style={vars({ "--i": i })}>
          {word}{" "}
        </span>
      ))}
    </>
  )
}

/** "Building your week…": the ring turning, a bar filling, and what Friday does, ticked off one by one. */
function Building() {
  const [done, setDone] = useState(0)
  useEffect(() => {
    const timers = BUILDING.map((_, i) => setTimeout(() => setDone(i + 1), 500 + i * 700))
    return () => timers.forEach(clearTimeout)
  }, [])
  return (
    <div className="ob-building">
      <Ring size={150} />
      <h1 id="ob-title" className="ob-title">
        Building your week…
      </h1>
      <div className="ob-bar-line">
        <i />
      </div>
      <ul>
        {BUILDING.map((line, i) => (
          <li key={line} data-done={i < done || undefined}>
            <Icon name={i < done ? "check-circle" : "circle-dashed"} fill={i < done} size={18} />
            {line}
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Your week in numbers, counted up, and the week itself building; your answers below, each a way back. */
function Reveal({ a, go }: { a: Answers; go: (step: string) => void }) {
  const k = numbersOf(a)
  const tiles: [ReactNode, string, string][] = [
    [<Count key="w" to={k.work} suffix="h" />, "of work a week, each with a time", "var(--ob-work)"],
    [<Count key="f" to={k.free} suffix="h" />, "kept yours, evenings and weekends", "var(--ob-free)"],
    [<Count key="s" to={k.sleep} suffix="h" />, "of sleep a night, never planned over", "var(--ob-class)"],
    [k.early ? <Count key="e" to={k.early} suffix={k.early === 1 ? " day" : " days"} /> : "0", "spare before every deadline", "var(--ob-gold)"],
  ]
  return (
    <div className="ob-reveal">
      <div className="ob-tiles">
        {tiles.map(([big, line, tint], i) => (
          <div key={line} className="ob-tile ob-in" style={vars({ "--i": 2 + i, "--tint": tint })}>
            <b>{big}</b>
            <span>{line}</span>
          </div>
        ))}
      </div>
      <WeekGrid a={a} />
      <div className="ob-answers">
        {badgesOf(a).map((b) => (
          <button key={b.label} type="button" onClick={() => go(b.step)} title="Change it">
            {b.label} <b>{b.value}</b>
          </button>
        ))}
      </div>
    </div>
  )
}

/** Hold to start, as Opal has you commit: the ring fills while you hold, and lets go if you do. Return or Space on the
 * button starts at once. */
function Hold({ onDone, busy }: { onDone: () => void; busy: boolean }) {
  const [holding, setHolding] = useState(false)
  const [burst, setBurst] = useState(false)
  const complete = () => {
    if (burst) return
    setBurst(true)
    setTimeout(onDone, 650)
  }
  return (
    <div className="ob-hold" data-holding={holding || undefined} data-burst={burst || undefined}>
      <button
        type="button"
        className="ob-hold-button"
        disabled={busy}
        onPointerDown={() => setHolding(true)}
        onPointerUp={() => setHolding(false)}
        onPointerLeave={() => setHolding(false)}
        onPointerCancel={() => setHolding(false)}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), complete())}
        aria-label="Hold to start planning"
      >
        <Ring size={170} />
        <svg viewBox="0 0 200 200" className="ob-hold-ring">
          <circle cx="100" cy="100" r="94" pathLength={100} onAnimationEnd={complete} />
        </svg>
      </button>
      <span className="ob-hold-say">{burst ? "Here's your week" : holding ? "Keep holding…" : "Hold to start planning"}</span>
    </div>
  )
}

/** Whether this is the Mac app's window (it names itself in its user agent), where the Mac's calendars come in. */
export const inMacApp = () => typeof navigator !== "undefined" && navigator.userAgent.includes("FridayMac")

// System Settings, from the Mac app's window: Internet Accounts, where Google is added; Calendars' privacy pane.
const ACCOUNTS = "x-apple.systempreferences:com.apple.Internet-Accounts-Settings.extension"
const PRIVACY = "x-apple.systempreferences:com.apple.preference.security?Privacy_Calendars"

type MacCalendar = Schemas["GoogleCalendarOut"]

/** The Mac's calendars by account ("iCloud", an address), each account's names in order. */
export function byAccount(calendars: MacCalendar[]): [string, MacCalendar[]][] {
  const out = new Map<string, MacCalendar[]>()
  for (const c of calendars) out.set(c.account || "On this Mac", [...(out.get(c.account || "On this Mac") ?? []), c])
  return [...out].sort(([, x], [, y]) => Number(!x.some((c) => c.on)) - Number(!y.some((c) => c.on))) // all left off: last
}

/** Bringing things in, simplest first (29 Oct: "i also don't love the more technical aspects of the setup - eg the
 * google calendar implementation. also is there a way not to use the api"). In the Mac app every calendar on the Mac
 * comes in, so Google is added to the Mac, as your own Friday reads your Gmail calendar; elsewhere a calendar's
 * private link does it. Google's own connection, a key file from Google Cloud, is only for Gmail, under More. Each is
 * done the moment you do it, not with the answers. */
function BringIn() {
  const mac = useQuery({ queryKey: ["mac_calendars"], queryFn: () => query("mac_calendars"), refetchInterval: 3000 }).data ?? []
  const feeds = (useInbox().data?.sources ?? []).filter((s) => s.kind === "ics")
  const accounts = useGoogleAccess()?.accounts ?? []
  const [more, setMore] = useState(accounts.length > 0)
  const onMac = inMacApp() || mac.length > 0
  return (
    <div className="st-group">
      {onMac ? (
        <Source icon="calendar-dots" hue="var(--px-class)" title="The calendars on this Mac" note="Friday reads every calendar the Mac's Calendar has: iCloud, Google, Outlook, your school's. To bring in Google, add your Google account to the Mac." i={0}>
          {mac.length > 0 && <Accounts calendars={mac} />}
          <span className="st-chips">
            <a className="st-chip st-chip-link" href={ACCOUNTS}>
              <Icon name="plus" size={14} /> Add an account to this Mac…
            </a>
          </span>
          <span className="st-source-note">In System Settings choose Google, sign in, and keep Calendars on. Its calendars appear here within a few seconds.</span>
          {mac.length === 0 && (
            <span className="st-source-note">
              Nothing here yet? Friday needs your permission to see them: <a className="st-link" href={PRIVACY}>Privacy & Security → Calendars</a>.
            </span>
          )}
        </Source>
      ) : (
        <Source icon="google-logo" hue="var(--px-class)" title="Google Calendar" note="Paste your calendar's private link: in Google Calendar's settings, choose your calendar, then copy “Secret address in iCal format”. Friday reads it; it can't change it." i={0}>
          <a className="st-link" href="https://calendar.google.com/calendar/r/settings" target="_blank" rel="noreferrer">
            Open Google Calendar's settings
          </a>
          <AddFeed trusted />
        </Source>
      )}
      <Source icon="link-simple" hue="var(--px-free)" title="A calendar link" note="From Canvas, your school or Outlook: paste its address, and new dates go to your Inbox." i={1}>
        <AddFeed />
        {feeds.length > 0 && <span className="st-source-note">Added: {feeds.map((f) => f.name).join(", ")}</span>}
      </Source>
      <Source icon="file-pdf" hue="var(--px-work)" title="Syllabus" note="A PDF or a course page becomes classes, readings, assignments and exam prep, in your Inbox." i={2}>
        <span>
          <Upload />
        </span>
      </Source>
      <button type="button" className="st-link st-rise" style={{ ["--i" as string]: 3 }} onClick={() => setMore(!more)} aria-expanded={more}>
        {more ? "Fewer options" : "More: Gmail, and connecting to Google directly"}
      </button>
      {more && (
        <Source icon="envelope-simple" hue="var(--px-gold)" title="Gmail, and Google's own connection" note="Friday can suggest due dates and events from your mail (it never sends or deletes). That needs Google's own connection, a one-time setup of about five minutes, step by step. It also reads Google Calendar without the Mac." i={0}>
          <ConnectedAccounts accounts={accounts} />
          <ConnectGoogle why={accounts.length ? "Google's page asks which account." : undefined} done="Choose the calendars it reads in Settings → Integrations." />
          <GmailSwitch />
          <GmailConnect />
        </Source>
      )}
    </div>
  )
}

/** The Mac's calendars Friday reads, by account; the ones it leaves off (birthdays, subscriptions) said as a count. */
function Accounts({ calendars }: { calendars: MacCalendar[] }) {
  return (
    <div className="st-accounts">
      {byAccount(calendars).map(([account, list]) => {
        const on = list.filter((c) => c.on)
        const off = list.filter((c) => !c.on)
        return (
          <div key={account} className="st-account">
            <Icon name={/@gmail\.com$|google/i.test(account) ? "google-logo" : /icloud/i.test(account) ? "cloud" : "calendar-blank"} size={15} />
            <span>
              <b>{account}</b> {on.map((c) => c.name).join(", ")}
              {off.length > 0 && (
                <span className="st-source-note">
                  {on.length ? " · " : ""}
                  {off.map((c) => c.name).join(", ")} left off
                </span>
              )}
            </span>
          </div>
        )
      })}
    </div>
  )
}

function CalendarCard({ c, events, onChange, i }: { c: Calendar; events: number; onChange: (change: Partial<Calendar>) => void; i: number }) {
  return (
    <div className="st-calendar st-rise" style={{ ["--i" as string]: i }}>
      <span style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
        <span className="st-source-title" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={c.name}>
          {c.name}
        </span>
        <span className="st-source-note">
          {events ? `${events} event${events === 1 ? "" : "s"} in the next two weeks` : "Nothing in the next two weeks"} · {saying(c.shown !== false, c.busy !== false)}
        </span>
      </span>
      <span className="st-chips" role="radiogroup" aria-label={`${c.name} on your calendar`}>
        {CHOICES.map((o) => (
          <button key={o.value} type="button" role="radio" aria-checked={choiceOf(c.shown !== false, c.busy !== false) === o.value} className="st-chip" onClick={() => onChange(fromChoice(o.value))}>
            {o.label}
          </button>
        ))}
      </span>
    </div>
  )
}
