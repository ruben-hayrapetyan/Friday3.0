// The tour of Friday (12 Nov: "instead of the todo list onboarding, there should be a new onboarding that covers how to
// generally use the app ... the first time i saw a user using the app ... they didn't have any rules, they were making
// "breakfast" and "lunch" and "dinner" events ... just walk through each of the tabs and explain what it is for. you
// can still have the little guy follow around but ... this should be a tour not a list of tasks"). It replaces the six
// quests of 31 Oct. One stop per page: the guide from setup (dialogs/walk/Guide.ts) runs to the page in the sidebar
// and points at it, and the card says what it's for and one thing worth knowing. Back and Next (or ← →); × or Esc
// ends it.
//
// It opens by itself once, when setup first finishes (`setup.toured`, kept by Friday, not the window: 31 Oct), and
// again from search ("Take the tour") or the Mac app's Help menu. The ? beside Settings is the page's own help
// (HelpOverlay.tsx): labels beside its buttons.

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { command, type Schemas } from "@/api/client"
import type { Gesture, Guide } from "@/dialogs/walk/Guide"
import { STRIP } from "@/dialogs/walk/strip"
import { useShell } from "./ShellContext"
import "./guide.css"

export interface Stop {
  id: string
  title: string
  body: string // what the page is for
  tip?: string // one thing worth knowing there
  target: string // the data-tour it points at
  gesture: Gesture
}

export const STOPS: Stop[] = [
  {
    id: "plan",
    title: "Here's your plan",
    body: "Your classes, events, meals and sleep, with the work Friday fits around them. Click a block to start it, finish it or move it.",
    tip: "You don't plan the week yourself: tell Friday what's due, and it finds the time, and finds it again when things change.",
    target: "nav-plan",
    gesture: "present",
  },
  {
    id: "todo",
    title: "To-do: what you have to do",
    body: "Type it the way you'd say it, “essay 3h due fri”, and Friday plans it at once. Lists for the short term, the long term and what's due.",
    tip: "Work is a to-do, not an event: add it here and Friday gives it a time.",
    target: "nav-todo",
    gesture: "point",
  },
  {
    id: "projects",
    title: "Projects and exams",
    body: "Big things in parts: a project split into steps, and exam prep planned in the days before each exam.",
    target: "nav-projects",
    gesture: "point",
  },
  {
    id: "inbox",
    title: "Inbox: what needs you",
    body: "Deadlines and events Friday found in your mail, calendars and apps, and its questions for you. Accept, change or reject each one.",
    tip: "Friday never sends notifications: anything that needs you waits here, with a count.",
    target: "nav-inbox",
    gesture: "mail",
  },
  {
    id: "insights",
    title: "Insights: how it really went",
    body: "How long things take you, where your time went, your sleep and meals, and a short look back at each week.",
    target: "nav-insights",
    gesture: "point",
  },
  {
    id: "rules",
    title: "Rules: how you like your days",
    body: "Say it in your own words, “no work after 10pm” or “readings in the morning”, and Friday plans by it. Notes about you go here too.",
    tip: "Meals and sleep come from your setup answers: no need to make Breakfast, Lunch or Dinner events.",
    target: "nav-rules",
    gesture: "think",
  },
  {
    id: "settings",
    title: "Settings",
    body: "Your calendars, mail and other apps (Integrations), how Friday looks, and your setup answers, one at a time.",
    target: "settings",
    gesture: "point",
  },
  {
    id: "end",
    title: "That's Friday",
    body: "Add what's due, and look in the Inbox now and then. Friday does the rest.",
    tip: "Lost on a page? The ? beside Settings labels its buttons.",
    target: "help",
    gesture: "wave",
  },
]

/** The visible element a stop points at, if any. */
function find(target: string): HTMLElement | null {
  for (const el of document.querySelectorAll<HTMLElement>(`[data-tour="${target}"]`)) {
    const r = el.getBoundingClientRect()
    if (r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < window.innerHeight) return el
  }
  return null
}

export const CARD = 340 // the card's width, at most
const MARGIN = 16
const BODY = 48 // half the guide's width with an arm out
const NARROW = 640 // below this, the card alone: no room for the guide

/** Where the guide stands by default: just left of the card, which sits in the window's bottom-right corner. */
export function homeOf(width: number): number {
  return width - MARGIN - Math.min(CARD, width - 2 * MARGIN) - 12 - BODY
}

/** Where the guide stands to show you a control: below it, kept clear of the card. */
export function standFor(rect: { left: number; width: number }, width: number): number {
  return Math.min(Math.max(rect.left + rect.width / 2, MARGIN + BODY), homeOf(width))
}

export function Tour() {
  const { setTour } = useShell()
  const reduced = useMemo(() => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false, [])
  const [at, setAt] = useState(0)
  const [ring, setRing] = useState<DOMRect | null>(null)
  const [width, setWidth] = useState(window.innerWidth)
  const [loaded, setLoaded] = useState(false)
  const [leaving, setLeaving] = useState(false)
  const canvas = useRef<HTMLCanvasElement>(null)
  const guide = useRef<Guide | null>(null)
  const next = useRef<HTMLButtonElement>(null)
  const stop = STOPS[at]
  const last = at === STOPS.length - 1
  const roomy = width >= NARROW
  const card = Math.min(CARD, width - 2 * MARGIN)

  // the guide, loaded with the 3D only now; without WebGL (or room), the card alone
  useEffect(() => {
    let gone = false
    import("@/dialogs/walk/Guide")
      .then(({ Guide }) => {
        if (gone || !canvas.current) return
        try {
          const made = new Guide(canvas.current, { reduced })
          made.resize(window.innerWidth)
          guide.current = made
          setLoaded(true)
        } catch {
          // no WebGL here
        }
      })
      .catch(() => {})
    return () => {
      gone = true
      guide.current?.dispose()
      guide.current = null
    }
  }, [reduced])

  // following the window and what the stop points at
  useLayoutEffect(() => {
    let frame = 0
    const measure = () => {
      frame = requestAnimationFrame(measure)
      if (window.innerWidth !== width) {
        setWidth(window.innerWidth)
        guide.current?.resize(window.innerWidth)
      }
      const r = find(stop.target)?.getBoundingClientRect() ?? null
      setRing((was) => (r && was && Math.abs(was.left - r.left) < 1 && Math.abs(was.top - r.top) < 1 && Math.abs(was.width - r.width) < 1 ? was : r))
    }
    measure()
    return () => cancelAnimationFrame(frame)
  }, [width, stop.target])

  // the guide by what the stop is about, pointing at it
  useEffect(() => {
    const g = guide.current
    if (!g || leaving) return
    if (!roomy) return g.leave()
    const aim = ring ? { x: ring.left + ring.width / 2, y: ring.top + ring.height / 2 } : null
    g.cue({ x: ring ? standFor(ring, width) : homeOf(width), gesture: stop.gesture, aim, jump: at === 0, cheer: at === 0 })
  }, [loaded, at, ring, width, roomy, leaving, stop.gesture])

  useEffect(() => next.current?.focus(), [at])

  const close = (end: boolean) => {
    const g = guide.current
    if (!g || !roomy) return setTour(false)
    setLeaving(true)
    g.onGone = () => setTour(false)
    g.leave(end)
    window.setTimeout(() => setTour(false), 4000)
  }
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLElement && e.target.closest("input, textarea, select")) return
      if (e.key === "Escape") close(false)
      if (e.key === "ArrowRight" && !last) setAt((n) => n + 1)
      if (e.key === "ArrowLeft" && at > 0) setAt((n) => n - 1)
    }
    window.addEventListener("keydown", key)
    return () => window.removeEventListener("keydown", key)
  })

  return (
    <div className="gd-quests" data-leaving={leaving ? "" : undefined}>
      {ring && !leaving && <div className="gd-ring" style={{ left: ring.left - 6, top: ring.top - 6, width: ring.width + 12, height: ring.height + 12 }} />}
      <canvas ref={canvas} className="gd-strip" aria-hidden="true" style={{ height: STRIP, display: roomy ? undefined : "none" }} />
      {!leaving && (
        <section className="gd-card" role="dialog" aria-label={`Tour of Friday: ${stop.title}`} style={{ width: card }}>
          <header className="gd-card-head">
            <span className="gd-where" aria-live="polite">
              Tour of Friday
            </span>
            <span className="gd-count">
              {at + 1}/{STOPS.length}
            </span>
            <button className="gd-icon" onClick={() => close(false)} aria-label="End the tour" title="End the tour (Esc)">
              ×
            </button>
          </header>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: "4px 2px 2px" }}>
            <h2 className="gd-title">{stop.title}</h2>
            <p style={{ margin: 0, lineHeight: 1.45, textWrap: "pretty" }}>{stop.body}</p>
            {stop.tip && (
              <p style={{ margin: 0, display: "flex", gap: 8, lineHeight: 1.4, fontSize: 13, opacity: 0.85, textWrap: "pretty" }}>
                <span aria-hidden="true">💡</span>
                <span>{stop.tip}</span>
              </p>
            )}
          </div>
          <div className="gd-foot">
            {at > 0 && (
              <button className="gd-show" onClick={() => setAt(at - 1)}>
                Back
              </button>
            )}
            <span style={{ flex: 1 }} />
            <button ref={next} className="gd-go" onClick={() => (last ? close(true) : setAt(at + 1))}>
              {last ? "Done" : "Next"}
              <i />
            </button>
          </div>
        </section>
      )}
    </div>
  )
}

/** The tour the first time setup finishes, once: Friday remembers it offered it. */
export function FirstTour({ ready, toured }: { ready: boolean; toured: boolean | undefined }) {
  const { setTour } = useShell()
  const client = useQueryClient()
  useEffect(() => {
    if (!ready || toured === undefined || toured) return
    const timer = setTimeout(() => {
      setTour(true)
      // offered: remembered by Friday, and known here at once, so it isn't offered again before the next read of setup
      client.setQueryData<Schemas["SetupOut"]>(["setup"], (was) => (was ? { ...was, toured: true } : was))
      command("tour_offered", {}).catch(() => {})
    }, 900)
    return () => clearTimeout(timer)
  }, [ready, toured, setTour, client])
  return null
}
