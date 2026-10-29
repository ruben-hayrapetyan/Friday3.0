// Setup: a few questions when Friday first opens, so the defaults fit you instead of being changed one by one in
// Settings. Each starts from what Friday does now; Skip keeps those. All the answers are saved together at the end
// (`setup_save`, one change you can undo), and the tour follows. Again from Settings, search or the Help menu. Near
// the end the AI is chosen and things are brought in (Google Calendar, course feeds, a syllabus, Gmail), each
// optional and done the moment you do it, with the same controls as Settings → Integrations.
//
// 29 Oct, "like Opal... animations, information, and you also select things but its very nice ui": a stage of its
// own (setup.css) in the colours of Friday's icon, one question a screen, choices as cards with a picture of what
// each means, and beside them the week your answers make, redrawn as you answer (setupWeek.ts). Friday's ring fills
// as you go and closes gold at the end, where your answers read back as a sentence, each part a way back to its
// question.

import "./setup.css"
import { useQuery } from "@tanstack/react-query"
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react"
import { query, type Schemas } from "@/api/client"
import { Icon, Switch } from "@/components/fr/controls"
import { TimeInput } from "@/components/fr/TimeInput"
import { useCommand } from "@/hooks/useCommand"
import { useInbox } from "@/inbox/InboxPage"
import { SLEEP_HOURS } from "@/lib/ampm"
import { ampm, parseLength } from "@/lib/format"
import { AiConnect, useAi } from "@/settings/AiConnect"
import { CalendarChoice, saying } from "@/settings/calendarChoice"
import { ConnectedAccounts } from "@/settings/GoogleAccounts"
import { ConnectGoogle, GmailConnect, GmailSwitch, useGoogleAccess } from "@/settings/GoogleConnect"
import { AddFeed, Upload } from "@/settings/Integrations"
import { Choices, EarlyGlyph, HourBar, LengthGlyph, Other, Ring, Source, TimeCard, WeekPanel } from "./SetupParts"
import { ALL_EVENING, ALL_WEEKEND, shift, sleepHours, weekOf } from "./setupWeek"

export { shift }
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

/** "an hour", "1.5 hours", "45 minutes": an amount as the summary says it. */
export function hoursWords(v: number): string {
  if (v < 1) return `${Math.round(v * 60)} minutes`
  return v === 1 ? "an hour" : `${v} hours`
}

const daysEarly = (d: number) => (d === 0 ? "on the day it's due" : d === 1 ? "a day early" : `${d} days early`)

/** The questions to ask: the calendars only when there are some. */
export function stepsFor(answers: Answers): string[] {
  return QUESTIONS.filter((id) => id !== "calendars" || (answers.calendars ?? []).length > 0)
}

const EVENINGS = ["17:00", "18:00", "19:00", "20:00"]

const QUESTIONS = ["day", "load", "focus", "free", "early", "calendars", "brief", "ai", "bring"]

/** Every screen, in order: Friday introduced, the questions, and your answers read back. */
export function screensFor(answers: Answers): string[] {
  return ["welcome", "how", ...stepsFor(answers), "ready"]
}

/** A part of the summary: what it says, and the question it goes back to. */
export type Part = string | { text: string; step: string }

/** Your answers as a few sentences, each answer a part that goes back to its question. */
export function summaryOf(a: Answers): Part[] {
  const different = a.weekend_wake !== a.wake || a.weekend_bedtime !== a.bedtime
  const out: Part[] = ["You're up at ", { text: ampm(a.wake), step: "day" }, " and in bed by ", { text: ampm(a.bedtime), step: "day" }]
  if (different) out.push(", or ", { text: ampm(a.weekend_wake), step: "day" }, " and ", { text: ampm(a.weekend_bedtime), step: "day" }, " at weekends")
  out.push(". Friday plans ", { text: hoursWords(a.normal_hours), step: "load" }, " of work on a normal day")
  if (a.most_hours > a.normal_hours) out.push(" and up to ", { text: hoursWords(a.most_hours), step: "load" }, " on a heavy one")
  out.push(", in sittings of up to ", { text: hoursWords(a.focus_hours), step: "focus" }, ". ")
  if (a.evening_free <= 0) out.push("Weekday evenings are ", { text: "open for work", step: "free" })
  else if (a.evening_free >= ALL_EVENING) out.push("Weekday evenings are yours from ", { text: ampm(a.evening_from), step: "free" })
  else out.push({ text: hoursWords(a.evening_free), step: "free" }, " of each weekday evening is yours from ", { text: ampm(a.evening_from), step: "free" })
  if (a.weekend_free <= 0) out.push(", and weekends are ", { text: "open for work", step: "free" }, ". ")
  else if (a.weekend_free >= ALL_WEEKEND) out.push(", and ", { text: "weekends are yours", step: "free" }, ". ")
  else out.push(", and ", { text: hoursWords(a.weekend_free), step: "free" }, " of each weekend day. ")
  out.push("Work is done ", { text: daysEarly(a.finish_early_days), step: "early" }, ", and exam prep goes in the days just before each exam.")
  out.push(a.brief ? " Each morning opens with " : " Friday opens ", { text: a.brief ? "your brief" : "straight to your plan", step: "brief" }, ".")
  return out
}

interface Screen {
  eyebrow: string
  title: string
  note?: string
  big?: boolean
  go?: string // the button's name, when not Continue
  body?: (a: Answers, set: (change: Partial<Answers>) => void, ctx: Ctx) => ReactNode
}

interface Ctx {
  events: Record<string, number>
  again: boolean // setup asked for again, from Settings
  go: (id: string) => void
}

const SCREENS: Record<string, Screen> = {
  welcome: {
    eyebrow: "Welcome to Friday",
    title: "Let's fit Friday to your week.",
    note: "A few questions about how your days go, so your first plan fits. About a minute; you can change any of it later in Settings.",
    big: true,
    go: "Start",
  },
  how: {
    eyebrow: "How Friday works",
    title: "You bring the deadlines. Friday finds the time.",
    body: () => (
      <div className="st-points">
        <Point icon="calendar-check" hue="var(--st-work)" title="Work goes where you have time" i={0}>
          Around your classes and events, never while you sleep, in sittings you can focus for.
        </Point>
        <Point icon="arrows-clockwise" hue="var(--st-gold)" title="When your week changes, so does the plan" i={1}>
          Something runs over or comes up, and the rest of the week is planned again.
        </Point>
        <Point icon="timer" hue="var(--st-class)" title="It learns how long things take you" i={2}>
          Time what you work on, and Friday plans with how long things really take.
        </Point>
      </div>
    ),
  },
  day: {
    eyebrow: "Your day",
    title: "When do your days start and end?",
    note: "Friday plans nothing while you sleep.",
    body: (a, set) => {
      const different = a.weekend_wake !== a.wake || a.weekend_bedtime !== a.bedtime
      return (
        <>
          <div className="st-group">
            {different && <span className="st-label st-rise">Weekdays</span>}
            <TimeCard icon="sun-horizon" hue="var(--st-gold)" label="Up at" value={a.wake} expect={{ hours: SLEEP_HOURS.up }} onPick={(wake) => set(different ? { wake } : { wake, weekend_wake: wake })} i={0} />
            <TimeCard icon="moon-stars" hue="var(--st-class)" label="Bed at" value={a.bedtime} expect={{ hours: SLEEP_HOURS.bed }} onPick={(bedtime) => set(different ? { bedtime } : { bedtime, weekend_bedtime: bedtime })} i={1} />
          </div>
          {different && (
            <div className="st-group">
              <span className="st-label st-rise">Weekends</span>
              <TimeCard icon="sun-horizon" hue="var(--st-gold)" label="Up at, weekends" value={a.weekend_wake} expect={{ hours: SLEEP_HOURS.up }} onPick={(weekend_wake) => set({ weekend_wake })} i={2} />
              <TimeCard icon="moon-stars" hue="var(--st-class)" label="Bed at, weekends" value={a.weekend_bedtime} expect={{ hours: SLEEP_HOURS.bed }} onPick={(weekend_bedtime) => set({ weekend_bedtime })} i={3} />
            </div>
          )}
          <label className="st-toggle st-rise" style={{ ["--i" as string]: 3 }}>
            <Switch on={different} onToggle={() => set(different ? { weekend_wake: a.wake, weekend_bedtime: a.bedtime } : { weekend_wake: shift(a.wake, 90), weekend_bedtime: shift(a.bedtime, 60) })} label="Weekends are different" />
            Weekends are different
          </label>
        </>
      )
    },
  },
  load: {
    eyebrow: "Work",
    title: "How much work fits in a day?",
    note: "Friday aims for a normal day, and goes up to your most only when deadlines need it.",
    body: (a, set) => (
      <>
        <div className="st-group">
          <HourBar label="On a normal day" value={a.normal_hours} min={1} segments={12} say={hoursLabel} onPick={(normal_hours) => set({ normal_hours, most_hours: Math.max(a.most_hours, normal_hours) })} i={0} />
          <Other value={a.normal_hours} picked={Number.isInteger(a.normal_hours)} read={readHours} say={hoursLabel} min={1} max={16} example="6.5h or 90 min" ask="Type an amount" label="A normal day, typed" onPick={(normal_hours) => set({ normal_hours, most_hours: Math.max(a.most_hours, normal_hours) })} />
        </div>
        <div className="st-group">
          <HourBar label="At most, on a heavy day" value={a.most_hours} min={1} segments={16} base={a.normal_hours} say={hoursLabel} onPick={(most_hours) => set({ most_hours, normal_hours: Math.min(a.normal_hours, most_hours) })} i={1} />
          <Other value={a.most_hours} picked={Number.isInteger(a.most_hours)} read={readHours} say={hoursLabel} min={1} max={16} example="10.5h" ask="Type an amount" label="At most, typed" onPick={(most_hours) => set({ most_hours, normal_hours: Math.min(a.normal_hours, most_hours) })} />
        </div>
      </>
    ),
  },
  focus: {
    eyebrow: "Focus",
    title: "How long can you work in one go?",
    note: "The longest Friday plans focused work before a break or something else.",
    body: (a, set) => {
      const picks = [0.75, 1, 1.5, 2, 3, 4]
      const notes: Record<number, string> = { 0.75: "Short sprints, many breaks", 1: "About a lecture's length", 1.5: "Most of a problem set", 2: "A long sitting", 3: "Deep work, few breaks", 4: "As long as it takes" }
      return (
        <>
          <Choices
            label="Longest stretch"
            value={picks.includes(a.focus_hours) ? a.focus_hours : null}
            onPick={(focus_hours) => set({ focus_hours })}
            choices={picks.map((v) => ({ value: v, title: hoursWords(v).replace(/^an/, "An"), note: notes[v], glyph: <LengthGlyph hours={v} />, hue: "var(--st-work)" }))}
          />
          <Other value={a.focus_hours} picked={picks.includes(a.focus_hours)} read={readHours} say={hoursLabel} min={0.5} max={8} example="2.5h or 100 min" ask="Another length" label="Longest stretch, typed" onPick={(focus_hours) => set({ focus_hours })} />
        </>
      )
    },
  },
  free: {
    eyebrow: "Free time",
    title: "How much time is yours?",
    note: "Time Friday keeps clear of work when it can. A deadline can still need it.",
    body: (a, set) => (
      <>
        <HourBar label="Of each weekday evening" value={a.evening_free} min={0} segments={ALL_EVENING} names={{ 0: "None", [ALL_EVENING]: "All of it" }} hue="var(--st-free)" say={hoursLabel} onPick={(evening_free) => set({ evening_free })} i={0} />
        {a.evening_free > 0 && (
          <div className="st-group st-rise" style={{ ["--i" as string]: 1 }}>
            <span className="st-label">Evenings start at</span>
            <div className="st-chips" role="radiogroup" aria-label="Evenings start at">
              {EVENINGS.map((t) => (
                <button key={t} type="button" role="radio" aria-checked={a.evening_from === t} className="st-chip" onClick={() => set({ evening_from: t })}>
                  {ampm(t)}
                </button>
              ))}
              <TimeInput className="st-input" step={300} value={EVENINGS.includes(a.evening_from) ? "" : a.evening_from} placeholder="Another time" onChange={(t) => t && set({ evening_from: t })} label="Evenings start at, another time" expect={{ hours: ["14:00", "23:59"] }} />
            </div>
          </div>
        )}
        <HourBar label="Of each weekend day" value={a.weekend_free} min={0} segments={ALL_WEEKEND} names={{ 0: "None", [ALL_WEEKEND]: "All of it" }} hue="var(--st-free)" say={hoursLabel} onPick={(weekend_free) => set({ weekend_free })} i={2} />
      </>
    ),
  },
  early: {
    eyebrow: "Deadlines",
    title: "How early do you like to be done?",
    note: "Exam prep is always planned in the days just before the exam.",
    body: (a, set) => {
      const picks = [0, 1, 2, 3]
      const titles = ["On the day", "A day early", "2 days early", "3 days early"]
      const notes = ["Finished by the deadline itself", "A day spare for surprises", "Room for a bad day", "Done well ahead"]
      return (
        <>
          <Choices
            label="Finish work"
            value={picks.includes(a.finish_early_days) ? a.finish_early_days : null}
            onPick={(finish_early_days) => set({ finish_early_days })}
            choices={picks.map((d) => ({ value: d, title: titles[d], note: notes[d], glyph: <EarlyGlyph days={d} />, hue: "var(--st-work)" }))}
          />
          <Other value={a.finish_early_days} picked={picks.includes(a.finish_early_days)} read={readDays} say={(d) => `${d} day${d === 1 ? "" : "s"} early`} min={0} max={7} example="5 days" ask="Further ahead" label="Days early, typed" onPick={(finish_early_days) => set({ finish_early_days })} />
        </>
      )
    },
  },
  calendars: {
    eyebrow: "Your calendars",
    title: "What should Friday do with each calendar?",
    note: "Plan around its events, just show them (dashed, and work may go over them), or hide it. A hidden one comes back under Show whenever you want it.",
    body: (a, set, ctx) => (
      <div className="st-group">
        {(a.calendars ?? []).map((c, i) => (
          <CalendarCard key={c.name} c={c} events={ctx.events[c.name] ?? 0} i={i} onChange={(change) => set({ calendars: (a.calendars ?? []).map((x) => (x.name === c.name ? { ...x, ...change } : x)) })} />
        ))}
      </div>
    ),
  },
  brief: {
    eyebrow: "Mornings",
    title: "Start each day with a brief?",
    note: "When you first open Friday each morning: what's planned, and what matters most today.",
    body: (a, set) => (
      <Choices
        one
        label="Morning brief"
        value={a.brief ? "on" : "off"}
        onPick={(v) => set({ brief: v === "on" })}
        choices={[
          { value: "on", title: "Yes, show it", note: "A minute's read, then your plan.", glyph: <Icon name="sun-horizon" fill size={22} />, hue: "var(--st-gold)" },
          { value: "off", title: "No thanks", note: "Open straight to your plan. It's in Settings if you change your mind.", glyph: <Icon name="arrow-right" size={22} />, hue: "var(--st-class)" },
        ]}
      />
    ),
  },
  ai: {
    eyebrow: "Your AI",
    title: "Which AI should Friday read with?",
    note: "It reads syllabi and mail and understands what you type. Friday plans without one, so you can skip this and choose later in Settings.",
    body: () => <AiConnect compact />,
  },
  bring: {
    eyebrow: "Bring things in",
    title: "Where are your classes and deadlines now?",
    note: "Each happens right away and is optional; they're all in Settings → Integrations too.",
    body: () => <BringIn />,
  },
  ready: {
    eyebrow: "All set",
    title: "Here's your week.",
    go: "Start planning",
    body: (a, _set, ctx) => (
      <p className="st-sum">
        {summaryOf(a).map((part, i) =>
          typeof part === "string" ? (
            part
          ) : (
            <button key={i} type="button" onClick={() => ctx.go(part.step)} title="Change it" style={{ ["--i" as string]: i / 2 }}>
              {part.text}
            </button>
          ),
        )}
      </p>
    ),
  },
}

export function SetupDialog({ onClose }: { onClose: () => void }) {
  const setup = useSetup().data
  const save = useCommand("setup_save", { label: (o) => o.result.message ?? "Saved" })
  const ai = useAi()
  const [draft, setDraft] = useState<Answers | null>(null)
  const [n, setN] = useState(0)
  const [back, setBack] = useState(false)
  const [saving, setSaving] = useState(false)
  const [beat, setBeat] = useState(0)
  const title = useRef<HTMLHeadingElement>(null)
  const main = useRef<HTMLElement>(null)
  useEffect(() => {
    if (setup && !draft) setDraft(setup.answers as unknown as Answers)
  }, [setup, draft])
  const ids = draft ? screensFor(draft) : []
  const id = ids[Math.min(n, ids.length - 1)] ?? "welcome"
  useEffect(() => {
    main.current?.scrollTo({ top: 0 })
    title.current?.focus({ preventScroll: true })
  }, [id])
  useEffect(() => {
    // "How Friday works": the week, and then something coming up on Wednesday and the work there moving
    setBeat(0)
    if (id !== "how") return
    const timer = setInterval(() => setBeat((b) => 1 - b), 2600)
    return () => clearInterval(timer)
  }, [id])
  const week = useMemo(() => (draft ? weekOf(draft, id, beat) : null), [draft, id, beat])
  const done = !!setup?.done
  const last = n >= ids.length - 1
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
  const next = () => (last && draft ? finish(draft) : to(n + 1))
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      if (e.key === "Escape" && done) return onClose()
      if (e.key !== "Enter" || e.shiftKey || e.metaKey || e.ctrlKey || e.altKey || saving) return
      if (target?.closest("input, textarea, select, button, a, [contenteditable]")) return // they answer Return themselves
      e.preventDefault()
      next()
    }
    window.addEventListener("keydown", key)
    return () => window.removeEventListener("keydown", key)
  })
  if (!draft || !setup || !week) return null
  const screen = SCREENS[id]
  const set = (change: Partial<Answers>) => setDraft({ ...draft, ...change })
  const ctx: Ctx = { events: setup.events ?? {}, again: done, go: (step) => to(ids.indexOf(step)) }
  const shown = id === "welcome" && done ? { ...screen, title: "Fit Friday to your week again.", note: "Your answers are filled in: change what's different." } : screen
  return (
    <div className="st-stage" role="dialog" aria-modal="true" aria-labelledby="st-title" data-quiet={["ai", "bring", "calendars"].includes(id) || undefined}>
      <header className="st-top">
        <Ring progress={n / Math.max(1, ids.length - 1)} closed={id === "ready"} />
        <span className="st-top-name">Friday</span>
        <span className="st-count">
          {n + 1} of {ids.length}
        </span>
        <button type="button" className="st-skip" onClick={() => (done ? onClose() : finish(setup.answers as unknown as Answers))} disabled={saving}>
          {done ? "Cancel" : "Skip: keep Friday's guesses"}
        </button>
      </header>
      <div className="st-frame">
        <main ref={main} className="st-main">
          <section key={id} className="st-q" data-back={back || undefined}>
            <div className="st-eyebrow st-rise">{shown.eyebrow}</div>
            <h1 ref={title} id="st-title" className="st-title st-rise" data-big={shown.big || undefined} tabIndex={-1} style={{ ["--i" as string]: 0.5 }}>
              {shown.title}
            </h1>
            {shown.note && (
              <p className="st-note st-rise" style={{ ["--i" as string]: 1 }}>
                {shown.note}
              </p>
            )}
            {shown.body && <div className="st-body">{shown.body(draft, set, ctx)}</div>}
          </section>
          <aside className="st-side" aria-label="Your week, as your answers make it">
            <WeekPanel bits={week.bits} stage={id} legend={["welcome", "how", "ready"].includes(id)} readout={readout(draft, id, week.workHours, beat, ai.ready ? ai.name : null)} />
          </aside>
        </main>
        <footer className="st-foot">
          <div className="st-foot-in">
            <div className="st-foot-row">
              {n > 0 && (
                <button type="button" className="st-back" onClick={() => to(n - 1)} disabled={saving}>
                  <Icon name="arrow-left" size={15} />
                  Back
                </button>
              )}
              {id === "welcome" && <span className="st-foot-hint">Press Return to go on</span>}
              <button type="button" className="st-go" onClick={next} disabled={saving}>
                {saving ? "Saving…" : (screen.go ?? "Continue")}
                {!saving && <Icon name="arrow-right" size={16} />}
              </button>
            </div>
          </div>
        </footer>
      </div>
    </div>
  )
}

/** What the week beside the question says. */
function readout(a: Answers, id: string, workHours: number, beat: number, ai: string | null): ReactNode {
  const sleep = sleepHours(a)
  switch (id) {
    case "welcome":
      return "Your week, drawn from your answers. It changes as you answer."
    case "how":
      return beat ? (
        <>
          Office hours came up on <b>Wednesday</b>: the work there moved.
        </>
      ) : (
        "Work fills the gaps around your classes."
      )
    case "day":
      return (
        <>
          <b>{hoursLabel(sleep.weekday)}</b> of sleep on weeknights
          {sleep.weekend !== sleep.weekday && (
            <>
              , <b>{hoursLabel(sleep.weekend)}</b> at weekends
            </>
          )}
          .
        </>
      )
    case "load":
      return (
        <>
          About <b>{workHours}h</b> of work in a normal week.{" "}
          {a.most_hours > a.normal_hours && (
            <>
              A heavy day (hatched) goes up to <b>{hoursLabel(a.most_hours)}</b>.
            </>
          )}
        </>
      )
    case "focus":
      return (
        <>
          Sittings of up to <b>{hoursLabel(a.focus_hours)}</b>, with a break between.
        </>
      )
    case "free":
      return a.evening_free <= 0 && a.weekend_free <= 0 ? (
        "No time kept free: work may go anywhere you're awake."
      ) : (
        <>
          {a.evening_free > 0 && (
            <>
              Evenings free from <b>{ampm(a.evening_from)}</b>
              {a.evening_free < ALL_EVENING && (
                <>
                  {" "}
                  for <b>{hoursLabel(a.evening_free)}</b>
                </>
              )}
              .{" "}
            </>
          )}
          {a.weekend_free > 0 && (
            <>
              {a.weekend_free >= ALL_WEEKEND ? (
                <>
                  <b>Weekends</b> free.
                </>
              ) : (
                <>
                  <b>{hoursLabel(a.weekend_free)}</b> free each weekend day.
                </>
              )}
            </>
          )}
        </>
      )
    case "early":
      return (
        <>
          An essay due <b>Friday at 5pm</b> is done <b>{daysEarly(a.finish_early_days)}</b>.
        </>
      )
    case "calendars": {
      const around = (a.calendars ?? []).filter((c) => c.shown !== false && c.busy !== false).length
      return (
        <>
          Friday plans around <b>{around}</b> of your calendars.
        </>
      )
    }
    case "brief":
      return a.brief ? "Each gold dot is a morning's brief." : "No brief: Friday opens straight to your plan."
    case "ai":
      return ai ? (
        <>
          Friday reads with <b>{ai}</b>.
        </>
      ) : (
        "No AI yet: Friday plans without one."
      )
    case "bring":
      return "Your classes and deadlines come in from where they already are."
    default:
      return (
        <>
          About <b>{workHours}h</b> of work in a normal week, around your classes.
        </>
      )
  }
}

function Point({ icon, hue, title, children, i }: { icon: string; hue: string; title: string; children: ReactNode; i: number }) {
  return (
    <div className="st-point st-rise" style={{ ["--i" as string]: i + 1 }}>
      <span className="st-glyph" style={{ ["--hue" as string]: hue }}>
        <Icon name={icon} fill size={20} />
      </span>
      <span>
        <b>{title}</b>
        <span>{children}</span>
      </span>
    </div>
  )
}

/** Bringing things in: each source is added (or connected) the moment you do it, not with the answers. */
function BringIn() {
  const feeds = (useInbox().data?.sources ?? []).filter((s) => s.kind === "ics")
  const accounts = useGoogleAccess()?.accounts ?? []
  return (
    <div className="st-group">
      <Source icon="google-logo" hue="var(--st-class)" title="Google Calendar" note="Its events become fixed time Friday plans around. Connect your school's account too, if you have one." i={0}>
        <ConnectedAccounts accounts={accounts} />
        <ConnectGoogle why={accounts.length ? "Google's page asks which account." : undefined} done="Choose the calendars it reads in Settings → Integrations." />
      </Source>
      <Source icon="rss" hue="var(--st-free)" title="Course feeds" note="A calendar link from Canvas or your school; new dates go to your Inbox." i={1}>
        <AddFeed />
        {feeds.length > 0 && <span className="st-source-note">Added: {feeds.map((f) => f.name).join(", ")}</span>}
      </Source>
      <Source icon="file-pdf" hue="var(--st-work)" title="Syllabus" note="A PDF becomes classes, readings, assignments and exam prep, in your Inbox." i={2}>
        <span>
          <Upload />
        </span>
      </Source>
      <Source icon="envelope-simple" hue="var(--st-gold)" title="Gmail" note="Friday suggests due dates and events from your mail. It never sends or deletes." i={3}>
        <GmailSwitch />
        <GmailConnect />
      </Source>
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
      <CalendarChoice name={c.name} shown={c.shown !== false} busy={c.busy !== false} onPick={onChange} />
    </div>
  )
}
