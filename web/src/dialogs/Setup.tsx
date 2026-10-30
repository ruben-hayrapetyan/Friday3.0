// Setup: the questions when Friday first opens, so the defaults fit you instead of being changed one by one in
// Settings. Each starts from what Friday does now; Skip keeps those. All the answers are saved together at the end
// (`setup_save`, one change you can undo), and the tour follows. Again from Settings, search or the Help menu. Near
// the end the AI is chosen and things are brought in (Google Calendar, course feeds, a syllabus, Gmail), each
// optional and done the moment you do it, with the same controls as Settings → Integrations.
//
// 29 Oct, "the pixel art thing is just the same intro from before but pixelated. no i mean like actually have cool
// game-like animations where an animated sprite is taking you through for example a week... not just random
// questions with at the end a fill in the blank": a little game. Friday, a calendar page with a face, lives through a
// week on screen (intro/scenes.ts), and asks each question as it comes to it, in a text box below: the alarm as it
// sleeps, how much work as books pile up on its desk, when you finish the essay as it walks to that day's sign, your
// free evening as the evening plays in fast forward. Answers change the world at once. At the end it runs across your
// week and the blocks drop in.

import "@fontsource/pixelify-sans/500.css"
import "@fontsource/pixelify-sans/600.css"
import "@fontsource/silkscreen/400.css"
import "./setup.css"
import { useQuery } from "@tanstack/react-query"
import { type ReactNode, useEffect, useLayoutEffect, useRef, useState } from "react"
import { query, type Schemas } from "@/api/client"
import { Icon, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useInbox } from "@/inbox/InboxPage"
import { SLEEP_HOURS } from "@/lib/ampm"
import { ampm, parseLength } from "@/lib/format"
import { AiConnect, useAi } from "@/settings/AiConnect"
import { CHOICES, choiceOf, fromChoice, saying } from "@/settings/calendarChoice"
import { ConnectedAccounts } from "@/settings/GoogleAccounts"
import { ConnectGoogle, GmailConnect, GmailSwitch, useGoogleAccess } from "@/settings/GoogleConnect"
import { AddFeed, Upload } from "@/settings/Integrations"
import { friday, MOON, SUN } from "./intro/art"
import { G, H, W } from "./intro/draw"
import { clockOf, finishAt, type Mem, paint, placeOf, type World } from "./intro/scenes"
import { Sprite, Steps, useTyped } from "./pixel"
import { Choices, EarlyGlyph, HourBar, LengthGlyph, Other, Source, TimeCard } from "./SetupParts"
import { ALL_EVENING, ALL_WEEKEND, shift } from "./setupWeek"

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

// The week, in order: Friday says hello, gets up, goes to class and to work, finishes an essay, has an evening and a
// Saturday, goes to bed, reads the morning's brief, packs its bag, and shows you the week. The calendars are asked
// about after bringing things in (29 Oct: "why does the choosing for calendars come before the calendar
// integration"), and only when there are some.
const STORY = ["title", "hello", "hello2", "wake", "classes", "work", "heavy", "focus", "deadline", "evening", "weekend", "bed", "brief", "ai", "bring", "calendars", "week"]

/** The steps of the story for these answers. */
export function storyFor(answers: Answers): string[] {
  return STORY.filter((id) => id !== "calendars" || (answers.calendars ?? []).length > 0)
}

/** What the end shows of your answers, each a way back to where it was asked. */
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

interface Ctx {
  events: Record<string, number>
  go: (id: string) => void
}

interface Step {
  say: (a: Answers) => string
  control?: (a: Answers, set: (change: Partial<Answers>) => void, ctx: Ctx) => ReactNode
  outro?: (a: Answers) => number // ms the ending plays after you answer, before the next step
  wide?: boolean // its answer needs room: the screen gets smaller
  go?: string
}

const FOCUS_PICKS = [0.75, 1, 1.5, 2, 3, 4]
const FOCUS_NOTES: Record<number, string> = { 0.75: "Short sprints", 1: "About a lecture", 1.5: "Most of a problem set", 2: "A long sitting", 3: "Deep work", 4: "As long as it takes" }
const EARLY_TITLES = ["On the day", "A day early", "2 days early", "3 days early"]
const EARLY_NOTES = ["Done by 5pm Friday", "Thursday, with a day spare", "Wednesday: room for a bad day", "Tuesday: well ahead"]
const EVENINGS = ["17:00", "18:00", "19:00", "20:00"]

const STEPS: Record<string, Step> = {
  title: { say: () => "", go: "Start" },
  hello: { say: () => "Hi! I'm Friday, a day on your calendar. I find time for your work around everything else in your life." },
  hello2: { say: () => "Let's live through one of your weeks together, so I learn how yours goes. About a minute, and you can change any of it later." },
  wake: {
    say: () => "First, the alarm. When do you get up?",
    control: (a, set) => {
      const same = a.weekend_wake === a.wake
      return <TimeCard glyph={<Sprite art={SUN} scale={2} />} hue="var(--px-gold)" label="Up at" value={a.wake} expect={{ hours: SLEEP_HOURS.up }} onPick={(wake) => set(same ? { wake, weekend_wake: wake } : { wake })} />
    },
    outro: () => 3000,
    go: "Wake up",
  },
  classes: { say: () => "Mornings bring classes. I plan around everything on your calendars, and never while you're asleep." },
  work: {
    say: () => "Then the real work. How much fits in a normal day?",
    control: (a, set) => (
      <div className="st-group">
        <HourBar label="On a normal day" value={a.normal_hours} min={1} segments={12} say={hoursLabel} onPick={(normal_hours) => set({ normal_hours, most_hours: Math.max(a.most_hours, normal_hours) })} />
        <Other value={a.normal_hours} picked={Number.isInteger(a.normal_hours)} read={readHours} say={hoursLabel} min={1} max={16} example="6.5h or 90 min" ask="Type an amount" label="A normal day, typed" onPick={(normal_hours) => set({ normal_hours, most_hours: Math.max(a.most_hours, normal_hours) })} />
      </div>
    ),
  },
  heavy: {
    say: (a) => (a.most_hours >= 10 ? "Phew. Some days are heavier. When deadlines pile up, how much at most?" : "Some days are heavier. When deadlines pile up, how much at most?"),
    control: (a, set) => (
      <div className="st-group">
        <HourBar label="At most, on a heavy day" value={a.most_hours} min={1} segments={16} base={a.normal_hours} say={hoursLabel} onPick={(most_hours) => set({ most_hours, normal_hours: Math.min(a.normal_hours, most_hours) })} />
        <Other value={a.most_hours} picked={Number.isInteger(a.most_hours)} read={readHours} say={hoursLabel} min={1} max={16} example="10.5h" ask="Type an amount" label="At most, typed" onPick={(most_hours) => set({ most_hours, normal_hours: Math.min(a.normal_hours, most_hours) })} />
      </div>
    ),
  },
  focus: {
    say: () => "How long can you work in one go, before you need a break?",
    control: (a, set) => (
      <>
        <Choices label="Longest stretch" value={FOCUS_PICKS.includes(a.focus_hours) ? a.focus_hours : null} onPick={(focus_hours) => set({ focus_hours })} choices={FOCUS_PICKS.map((v) => ({ value: v, title: hoursLabel(v), note: FOCUS_NOTES[v], glyph: <LengthGlyph hours={v} />, hue: "var(--px-work)" }))} />
        <Other value={a.focus_hours} picked={FOCUS_PICKS.includes(a.focus_hours)} read={readHours} say={hoursLabel} min={0.5} max={8} example="2.5h or 100 min" ask="Another length" label="Longest stretch, typed" onPick={(focus_hours) => set({ focus_hours })} />
      </>
    ),
  },
  deadline: {
    say: () => "An essay's due Friday at 5pm. When do you like to be done with it?",
    control: (a, set) => (
      <>
        <Choices label="Finish work" value={[0, 1, 2, 3].includes(a.finish_early_days) ? a.finish_early_days : null} onPick={(finish_early_days) => set({ finish_early_days })} choices={[0, 1, 2, 3].map((d) => ({ value: d, title: EARLY_TITLES[d], note: EARLY_NOTES[d], glyph: <EarlyGlyph days={d} />, hue: "var(--px-work)" }))} />
        <Other value={a.finish_early_days} picked={[0, 1, 2, 3].includes(a.finish_early_days)} read={readDays} say={(d) => `${d} day${d === 1 ? "" : "s"} early`} min={0} max={7} example="5 days" ask="Further ahead" label="Days early, typed" onPick={(finish_early_days) => set({ finish_early_days })} />
      </>
    ),
    outro: () => 1500,
  },
  evening: {
    say: (a) => (a.evening_free <= 0 ? "Evenings. None kept free? Then I may plan work right up to bedtime." : "Evenings. How much of each one stays yours, no work?"),
    control: (a, set) => (
      <div className="st-group">
        <HourBar label="Of each weekday evening" value={a.evening_free} min={0} segments={ALL_EVENING} names={{ 0: "None", [ALL_EVENING]: "All of it" }} hue="var(--px-free)" say={hoursLabel} onPick={(evening_free) => set({ evening_free })} />
        {a.evening_free > 0 && (
          <span className="st-chips" role="radiogroup" aria-label="Evenings start at">
            <span className="st-label">From</span>
            {EVENINGS.map((t) => (
              <button key={t} type="button" role="radio" aria-checked={a.evening_from === t} className="st-chip" onClick={() => set({ evening_from: t })}>
                {ampm(t)}
              </button>
            ))}
          </span>
        )}
      </div>
    ),
  },
  weekend: {
    say: (a) => (a.weekend_free >= ALL_WEEKEND ? "And weekends are all yours. Nice." : "And on weekend days, how much is yours?"),
    control: (a, set) => <HourBar label="Of each weekend day" value={a.weekend_free} min={0} segments={ALL_WEEKEND} names={{ 0: "None", [ALL_WEEKEND]: "All of it" }} hue="var(--px-free)" say={hoursLabel} onPick={(weekend_free) => set({ weekend_free })} />,
  },
  bed: {
    say: () => "It's getting late. When do you go to bed?",
    control: (a, set) => {
      const different = a.weekend_wake !== a.wake || a.weekend_bedtime !== a.bedtime
      return (
        <div className="st-group">
          <TimeCard glyph={<Sprite art={MOON} scale={3} />} hue="var(--px-class)" label="Bed at" value={a.bedtime} expect={{ hours: SLEEP_HOURS.bed }} onPick={(bedtime) => set(different ? { bedtime } : { bedtime, weekend_bedtime: bedtime })} />
          <label className="st-toggle">
            <Switch on={different} onToggle={() => set(different ? { weekend_wake: a.wake, weekend_bedtime: a.bedtime } : { weekend_wake: shift(a.wake, 90), weekend_bedtime: shift(a.bedtime, 60) })} label="Weekends are different" />
            Weekends are different
          </label>
          {different && (
            <div className="in-pair">
              <TimeCard glyph={<Sprite art={SUN} scale={2} />} hue="var(--px-gold)" label="Up at, weekends" value={a.weekend_wake} expect={{ hours: SLEEP_HOURS.up }} onPick={(weekend_wake) => set({ weekend_wake })} />
              <TimeCard glyph={<Sprite art={MOON} scale={3} />} hue="var(--px-class)" label="Bed at, weekends" value={a.weekend_bedtime} expect={{ hours: SLEEP_HOURS.bed }} onPick={(weekend_bedtime) => set({ weekend_bedtime })} />
            </div>
          )}
        </div>
      )
    },
    outro: () => 2300,
    go: "Good night",
  },
  brief: {
    say: () => "Morning! Want a quick brief like this each day? What's planned, and what matters most.",
    control: (a, set) => (
      <Choices
        one
        label="Morning brief"
        value={a.brief ? "on" : "off"}
        onPick={(v) => set({ brief: v === "on" })}
        choices={[
          { value: "on", title: "Yes, every morning", note: "A minute's read, then your plan.", glyph: <Sprite art={SUN} scale={2} />, hue: "var(--px-gold)" },
          { value: "off", title: "No thanks", note: "Straight to your plan. It's in Settings if you change your mind.", glyph: <Icon name="arrow-right" size={22} />, hue: "var(--px-class)" },
        ]}
      />
    ),
    outro: (a) => (a.brief ? 1900 : 1000),
  },
  ai: { say: () => "Let's pack your bag. Which AI should I read your syllabi and mail with? You can skip this.", control: () => <AiConnect compact />, wide: true },
  bring: { say: () => "Where are your classes and deadlines now? Bring them in and I'll take it from there.", control: () => <BringIn />, wide: true },
  calendars: {
    say: () => "What should I do with each of your calendars?",
    control: (a, set, ctx) => (
      <div className="st-group">
        {(a.calendars ?? []).map((c) => (
          <CalendarCard key={c.name} c={c} events={ctx.events[c.name] ?? 0} i={0} onChange={(change) => set({ calendars: (a.calendars ?? []).map((x) => (x.name === c.name ? { ...x, ...change } : x)) })} />
        ))}
      </div>
    ),
    wide: true,
  },
  week: {
    say: () => "Here's your week. Anything look off? Click it to change it.",
    control: (a, _set, ctx) => (
      <div className="in-badges">
        {badgesOf(a).map((b) => (
          <button key={b.label} type="button" className="in-badge" onClick={() => ctx.go(b.step)}>
            <span>{b.label}</span>
            <b>{b.value}</b>
          </button>
        ))}
      </div>
    ),
    go: "Start planning",
  },
}

const still = () => typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches

/** The size the screen is drawn at: whole pixels when there's room, so the pixel art stays sharp. */
export function screenScale(width: number, height: number): number {
  const s = Math.min(width / W, height / H)
  return s >= 2 ? Math.floor(s) : Math.max(1, s)
}

export function SetupDialog({ onClose }: { onClose: () => void }) {
  const at = useRef("title")
  // Read again every few seconds while things are brought in: a calendar connected then is asked about next.
  const setup = useQuery({ queryKey: ["setup"], queryFn: () => query("setup"), refetchInterval: () => (at.current === "bring" ? 3000 : false) }).data
  const save = useCommand("setup_save", { label: (o) => o.result.message ?? "Saved" })
  const ai = useAi()
  const feeds = (useInbox().data?.sources ?? []).length
  const [draft, setDraft] = useState<Answers | null>(null)
  // While building it (`pnpm dev` only), ?step=evening opens the story at that step.
  const [n, setN] = useState(() => (import.meta.env.DEV ? Math.max(0, STORY.indexOf(new URLSearchParams(location.search).get("step") ?? "")) : 0))
  const [saving, setSaving] = useState(false)
  const [ending, setEnding] = useState<number | null>(null) // when the step's ending began
  const [scale, setScale] = useState(3)
  const canvas = useRef<HTMLCanvasElement>(null)
  const stage = useRef<HTMLDivElement>(null)
  const world = useRef<{ step: string; began: number; ending: number | null; a: Answers | null; bag: World["bag"]; mem: Mem; pick?: string; fresh: boolean }>({ step: "title", began: 0, ending: null, a: null, bag: { ai: false, connected: 0 }, mem: { books: [] }, fresh: true })
  useEffect(() => {
    if (!setup) return
    setDraft((d) => (d ? withCalendars(d, setup.answers.calendars as Calendar[]) : (setup.answers as unknown as Answers)))
  }, [setup])
  const ids = draft ? storyFor(draft) : STORY
  const id = ids[Math.min(n, ids.length - 1)]
  at.current = id
  const step = STEPS[id]
  const done = !!setup?.done
  const line = id === "title" && done ? "" : draft ? step.say(draft) : ""
  const [typed, typing, showAll] = useTyped(line)
  const [clock, setClock] = useState<string | null>(null)
  const ready = !!draft && !!setup

  // The world the canvas draws, kept current without redrawing React.
  const w = world.current
  if (w.step !== id) {
    w.fresh = placeOf(w.step) !== placeOf(id)
    w.step = id
    w.began = performance.now()
    w.ending = null
    if (id === "deadline") w.mem.x = finishAt(4) + 1 // it walks there from Monday
    else w.mem.x = undefined
  }
  w.a = draft
  w.ending = ending
  w.bag = { ai: ai.ready, connected: feeds + (draft?.calendars?.length ?? 0) }
  w.pick = draft?.brief ? "on" : "off"

  // The screen: a frame a refresh, drawn from the world above, once there's a canvas to draw on.
  useEffect(() => {
    const ctx = canvas.current?.getContext("2d")
    if (!ctx) return
    const g = new G(ctx)
    const calm = still()
    let last = performance.now()
    let raf = 0
    let shown = ""
    const frame = (now: number) => {
      const s = world.current
      if (s.a) {
        const view: World = { step: s.step, t: now - s.began, done: s.ending === null ? null : now - s.ending, now, dt: Math.min(100, now - last), a: s.a, still: calm, bag: s.bag, pick: s.pick, mem: s.mem, fresh: s.fresh }
        paint(g, view)
        const c = clockOf(view)
        const said = c ? `${c.day} ${ampm(clockText(c.minutes))}` : ""
        if (said !== shown) setClock((shown = said) || null)
      }
      last = now
      raf = requestAnimationFrame(frame)
    }
    raf = requestAnimationFrame(frame)
    return () => cancelAnimationFrame(raf)
  }, [ready])

  // Whole-pixel scaling to the room there is, the answer's box below.
  useLayoutEffect(() => {
    const fit = () => {
      const box = stage.current
      if (!box) return
      const room = step.wide ? 0.46 : 0.6
      setScale(screenScale(box.clientWidth - 32, box.clientHeight * room - 60))
    }
    fit()
    window.addEventListener("resize", fit)
    return () => window.removeEventListener("resize", fit)
  }, [step.wide, ready])

  const finish = async (answers: Answers) => {
    setSaving(true)
    const out = await save(answers)
    setSaving(false)
    if (out) onClose()
  }
  const to = (next: number) => {
    setEnding(null)
    setN(Math.max(0, Math.min(ids.length - 1, next)))
  }
  const last = n >= ids.length - 1
  const next = () => {
    if (!draft) return
    if (ending !== null) return to(n + 1) // the ending playing: on at once
    if (last) return finish(draft)
    const length = still() ? 0 : (step.outro?.(draft) ?? 0)
    if (!length) return to(n + 1)
    setEnding(performance.now())
  }
  // The ending plays, then the next step.
  useEffect(() => {
    if (ending === null || !draft) return
    const timer = setTimeout(() => to(n + 1), step.outro?.(draft) ?? 0)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ending])
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      if (e.key === "Escape" && done) return onClose()
      const own = target?.closest("input, textarea, select, a, [contenteditable], .st-step, .in-own")
      if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && draft && !own && !target?.closest("[role=slider], [role=radio]") && (id === "wake" || id === "bed")) {
        e.preventDefault()
        const by = e.key === "ArrowLeft" ? -15 : 15
        setDraft(id === "wake" ? { ...draft, wake: shift(draft.wake, by), ...(draft.weekend_wake === draft.wake ? { weekend_wake: shift(draft.wake, by) } : {}) } : { ...draft, bedtime: shift(draft.bedtime, by), ...(draft.weekend_bedtime === draft.bedtime ? { weekend_bedtime: shift(draft.bedtime, by) } : {}) })
        return
      }
      if (e.key !== "Enter" || e.shiftKey || e.metaKey || e.ctrlKey || e.altKey || saving || own) return
      e.preventDefault()
      if (typing) showAll() // as a game's text box: the first Return shows the whole line
      else next()
    }
    window.addEventListener("keydown", key)
    return () => window.removeEventListener("keydown", key)
  })
  if (!draft || !setup) return null
  const set = (change: Partial<Answers>) => setDraft({ ...draft, ...change })
  const ctx: Ctx = { events: setup.events ?? {}, go: (s) => to(ids.indexOf(s)) }
  const talking = typing && Math.floor(typed.length / 3) % 2 === 0
  return (
    <div ref={stage} className="st-stage in-stage" role="dialog" aria-modal="true" aria-label="Set up Friday" data-wide={step.wide || undefined}>
      <header className="st-top">
        <Steps at={n} of={ids.length} done={last} />
        <span className="st-count">
          {n + 1}/{ids.length}
        </span>
        <button type="button" className="st-skip in-own" onClick={() => (done ? onClose() : finish(setup.answers as unknown as Answers))} disabled={saving}>
          {done ? "Cancel" : "Skip: keep Friday's guesses"}
        </button>
      </header>
      <div className="in-screen" style={{ width: W * scale, height: H * scale }} onClick={() => (typing ? showAll() : id === "title" ? next() : undefined)}>
        <canvas ref={canvas} width={W} height={H} aria-hidden />
        {clock && <span className="in-clock">{clock}</span>}
      </div>
      {id !== "title" && (
        <div className="in-box" style={{ width: Math.max(W * scale, Math.min(720, (stage.current?.clientWidth ?? 800) - 32)) }}>
          <div className="in-say" onClick={() => typing && showAll()}>
            <span className="in-face" aria-hidden>
              <Sprite art={friday(talking ? "happy" : "open", "none").slice(0, 15)} scale={3} />
            </span>
            <p className="in-line" aria-live="polite">
              <span className="sr-only">{line}</span>
              <span className="px-type" aria-hidden>
                <span className="px-ghost">{line}</span>
                <span className="px-typed">
                  {typed}
                  {typing && <i className="px-caret" />}
                </span>
              </span>
            </p>
          </div>
          {step.control && (
            <div className="in-control" data-on={!typing || undefined} inert={ending !== null || undefined}>
              {step.control(draft, set, ctx)}
            </div>
          )}
          <div className="in-foot">
            {n > 1 && (
              <button type="button" className="st-back in-own" onClick={() => to(n - 1)} disabled={saving}>
                ◀ Back
              </button>
            )}
            <span className="in-hint">{typing ? "Return: the whole line" : "Return: go on"}</span>
            <button type="button" className="st-go in-own" onClick={() => (typing ? showAll() : next())} disabled={saving}>
              {saving ? "Saving…" : ending !== null ? "Skip ▶" : (step.go ?? "Next")}
              {!saving && ending === null && " ▶"}
            </button>
          </div>
        </div>
      )}
      {id === "title" && (
        <button type="button" className="st-go in-start in-own" onClick={next}>
          {done ? "Fit Friday to your week again ▶" : "Start ▶"}
        </button>
      )}
    </div>
  )
}

/** Minutes past midnight (past 24:00 the next day's) as "HH:MM". */
function clockText(minutes: number): string {
  const m = ((Math.round(minutes / 5) * 5) % 1440 + 1440) % 1440
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`
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
