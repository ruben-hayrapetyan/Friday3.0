// A tour of Friday, shown round by the one who walked you through your week in setup (30 Oct: "when you are finished
// with the setup, make the welcome to friday be guided by the same character and make it more in depth"). Shown once,
// the first time Friday opens after setup, and again from the ? beside Settings, from search ("Take the tour") or the
// Mac app's Help menu. It goes page by page: each step lights up the control it's about while they jog along the foot
// of the window to below it and point at it (dialogs/walk/Guide.ts), and say what it does in a game's dialog box beside
// them, as setup's are. A step whose control isn't on screen (nothing needs you today, a narrow window without the
// sidebar) is skipped, or said anyway when it's something you need. Without WebGL, the box alone.

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import { useLocation, useNavigate } from "react-router"
import type { Gesture, Guide } from "@/dialogs/walk/Guide"
import { STRIP } from "@/dialogs/walk/strip"
import { useShell } from "./ShellContext"
import "./guide.css"

export interface Step {
  page?: string // the page it's on: the calendar's when not said
  target?: string // the control's data-tour name ("block": a planned block on the calendar); none: no control
  title: string
  body: string
  gesture?: Gesture // what they do there: point at the control when not said
  optional?: boolean // skipped when its control isn't there; otherwise said anyway
}

export const STEPS: Step[] = [
  {
    title: "Welcome to Friday",
    body: "That’s your week set up! Friday fits your to-dos into the free time around your events, and replans whenever something changes. Let me show you round: every page, about two minutes.",
    gesture: "wave",
  },
  {
    target: "nav",
    title: "Your pages",
    body: "Plan is home: your calendar with the work Friday planned. To-do has every task, Projects & exams the big ones, Inbox whatever needs you, Rules how you like your days. Insights and Sleep & meals show what Friday learns.",
  },
  {
    target: "menu",
    title: "Your pages",
    body: "The menu opens your pages: Plan, To-do, Inbox, Rules and the rest.",
    optional: true,
  },
  {
    target: "calendar",
    title: "Your week",
    body: "Grey blocks are your events; coloured ones are work Friday planned. Drag one to move it, drag its edge to change its length, ⌘-click to pick several. Double-click an empty time to add an event.",
    gesture: "present",
  },
  {
    target: "block",
    title: "A planned block",
    body: "Click one when you sit down to it. Start times it, Pause keeps the time for later, Done ticks it off: Friday learns how long things really take you. Pin keeps it where it is; double-click its time to type a new one.",
    optional: true,
  },
  {
    target: "attention",
    title: "When something needs you",
    body: "If work will be late, a day is too full or two events overlap, it shows here, with ways out: skip an event, move something, or ease off.",
    optional: true,
  },
  {
    target: "plan-menu",
    title: "Change the plan",
    body: "Ask the AI in your own words (“move my 5pm to Thursday”), see two other ways to plan the same work, Shove work out of a busy stretch, set the Pace, or open the morning brief.",
  },
  {
    target: "whatif",
    title: "What if",
    body: "Try changes on the calendar, like skipping a club or adding a shift, and see what they’d cost before you make them.",
    gesture: "think",
    optional: true,
  },
  {
    target: "views",
    title: "Day, week or month",
    body: "Switch the view here, or press D, 3, W or M. The arrows beside the date step back and forward; [ and ] do too.",
    optional: true,
  },
  {
    target: "show",
    title: "What’s hidden",
    body: "Office hours and calendars with a toggle stay off your calendar. Switch them on here when you want to see them; they never change the plan.",
    optional: true,
  },
  {
    target: "drawer",
    title: "Your to-do list",
    body: "Slides out beside the calendar (or press T). Type a task the way you’d say it: “essay 3h due Fri”.",
  },
  {
    target: "search",
    title: "Find anything",
    body: "Tasks, events, projects, settings and actions, from anywhere with ⌘K. When nothing matches, Enter adds what you typed as a to-do.",
  },
  {
    target: "now",
    title: "Right now",
    body: "What Friday suggests doing now. Start the timer when you begin (Space starts and pauses it), and Friday learns how long things take you.",
    optional: true,
  },
  {
    page: "/todo",
    target: "todo-list",
    title: "To-do",
    body: "Every task, by kind. Type in a section’s line the way you’d say it: “ch 4 #psych due fri ~1h”. Leave the length out and Friday guesses it. Click a task for everything about it; ⌘- or Shift-click picks several.",
  },
  {
    page: "/todo",
    target: "todo-lists",
    title: "Now, later, or by date",
    body: "Short term is what’s on the plan; Long term waits until you move it in. Due lists everything by its date.",
    optional: true,
  },
  {
    page: "/inbox",
    target: "inbox",
    title: "Inbox",
    body: "What needs you, a message each: what only you can decide, how much of your planned work you did (that’s how Friday learns your pace), and what it found in your mail, calendars and syllabi, for you to accept or not.",
    gesture: "mail",
  },
  {
    page: "/projects",
    target: "projects-new",
    title: "Projects & exams",
    body: "Exams come in from your class calendar, and Friday plans their prep before them. A project is something with steps, like an essay: Friday spreads the steps out before it’s due.",
  },
  {
    page: "/rules",
    target: "rule-new",
    title: "Rules",
    body: "How you like your days, in your own words: “no work after 10pm”, “gym Tuesday and Thursday mornings”. Friday shows how it read it, and you say how much it matters: Prefer, Strongly or Always.",
    gesture: "think",
  },
  {
    page: "/rules",
    target: "week-paces",
    title: "Easier days, harder days",
    body: "Days that go easier or harder, every week. Click a day to change it.",
    optional: true,
  },
  {
    page: "/insights",
    target: "insights",
    title: "Insights",
    body: "What you finished, how long things take you against your guesses, and what Friday learned from how you work. Nothing it learns changes your plan until you approve it.",
    gesture: "present",
  },
  {
    page: "/body",
    target: "tracking",
    title: "Sleep & meals",
    body: "Turn tracking on and the Now bar offers “Going to bed”, “I’m up” and “Eating now”. Friday learns when you really sleep and eat, and plans around it.",
  },
  {
    page: "/settings",
    target: "settings-nav",
    title: "Settings",
    body: "Your calendars and Google accounts, your schedule, the AI Friday uses, how it looks and its shortcuts. “Answer Setup’s questions again” walks you back through your week.",
  },
  {
    target: "help",
    title: "That’s it",
    body: "The ? brings this tour back whenever you want it. Have a good week!",
    gesture: "wave",
  },
]

/** The pages the tour goes through, in order, for the squares at the top of its box. */
const PAGES: [string, string][] = [
  ["/", "Plan"],
  ["/todo", "To-do"],
  ["/inbox", "Inbox"],
  ["/projects", "Projects"],
  ["/rules", "Rules"],
  ["/insights", "Insights"],
  ["/body", "Sleep & meals"],
  ["/settings", "Settings"],
]

const SEEN = "friday-tour-seen"
const WAIT = 900 // ms to look for a step's control once its page is up

/** Whether this device hasn't had the tour yet. */
export function tourDue(): boolean {
  try {
    return localStorage.getItem(SEEN) !== "1"
  } catch {
    return false // no storage: don't show it on every visit
  }
}

function markSeen(): void {
  try {
    localStorage.setItem(SEEN, "1")
  } catch {
    // private mode: it may come back next visit
  }
}

/** The visible element a step points at, if any. */
function find(target?: string): HTMLElement | null {
  if (!target) return null
  const selector = target === "block" ? '[data-block-key^="T"]' : `[data-tour="${target}"]`
  for (const el of document.querySelectorAll<HTMLElement>(selector)) {
    const r = el.getBoundingClientRect()
    if (r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < window.innerHeight) return el
  }
  return null
}

/** The steps to show: optional ones only when their control is on screen. */
export function stepsFor(present: (target: string) => boolean): Step[] {
  return STEPS.filter((s) => !s.optional || (s.target !== undefined && present(s.target)))
}

type Box = { left: number; top: number; right: number; bottom: number; width: number; height: number }
type Size = { width: number; height: number }

export const BOX = 380 // the box's width, at most
const BODY = 48 // half the guide's width with an arm out
const GAP = 14
const MARGIN = 16

/** Where the guide stands (`x`, from the window's left) and where their box goes (`left`, and `bottom` up from the
 * window's foot): below the control, pointing up at it, with the box beside them on the side with room; beside a
 * control down where they stand, the box on its far side; the two side by side in the middle with no control; and on
 * a phone, the box above them. */
export function spotFor(rect: Box | null, win: Size): { x: number; left: number; bottom: number; width: number } {
  const width = Math.min(BOX, win.width - 2 * MARGIN)
  if (win.width < 2 * BODY + GAP + width + 2 * MARGIN) return { x: MARGIN + BODY, left: (win.width - width) / 2, bottom: STRIP - 12, width }
  const inside = (x: number) => Math.min(Math.max(x, MARGIN + BODY), win.width - MARGIN - BODY)
  const fitsRight = (x: number) => x + BODY + GAP + width <= win.width - MARGIN
  const fitsLeft = (x: number) => x - BODY - GAP - width >= MARGIN
  let x: number
  let right: boolean
  if (!rect) {
    x = (win.width - (2 * BODY + GAP + width)) / 2 + BODY
    right = true
  } else if (rect.bottom > win.height - STRIP + 20 && rect.height < win.height * 0.5) {
    // down where they stand: beside it, the box further out on that side
    x = inside(rect.right + 24 + BODY)
    right = true
    if (!fitsRight(x) || x - BODY < rect.right) {
      x = inside(rect.left - 24 - BODY)
      right = false
    }
  } else {
    x = inside(rect.left + rect.width / 2)
    right = fitsRight(x) || !fitsLeft(x)
  }
  if (right && !fitsRight(x)) x = win.width - MARGIN - width - GAP - BODY
  if (!right && !fitsLeft(x)) x = MARGIN + width + GAP + BODY
  return { x, left: right ? x + BODY + GAP : x - BODY - GAP - width, bottom: 18, width }
}

const rounded = (r: DOMRect | null) => (r ? `${Math.round(r.left)},${Math.round(r.top)},${Math.round(r.width)},${Math.round(r.height)}` : "")

export function Tour() {
  const { setTour, setDrawer, setPop, setDialog } = useShell()
  const navigate = useNavigate()
  const location = useLocation()
  const reduced = useMemo(() => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false, [])
  const [n, setN] = useState(0)
  const way = useRef(1) // which way through the steps: skipping a missing one goes on the same way
  const [rect, setRect] = useState<DOMRect | null>(null)
  const [found, setFound] = useState(false) // the step's control was found, or looked for long enough
  const [win, setWin] = useState({ width: window.innerWidth, height: window.innerHeight })
  const [talking, setTalking] = useState(false) // the words have started
  const [shown, setShown] = useState(0) // how many of them so far
  const [leaving, setLeaving] = useState(false)
  const canvas = useRef<HTMLCanvasElement>(null)
  const guide = useRef<Guide | null>(null)
  const [loaded, setLoaded] = useState(false) // the guide's there (a moment after the tour opens)
  const since = useRef(performance.now())
  const step = STEPS[n]
  const page = step.page ?? "/"
  const here = page === "/" ? location.pathname === "/" : location.pathname.startsWith(page)

  // the guide, loaded with the 3D only now; without WebGL, the box alone
  useEffect(() => {
    setDrawer(false)
    setPop(null)
    setDialog(null)
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // to the step's page; the words start again
  useEffect(() => {
    if (!here) navigate(page)
    setFound(false)
    setTalking(false)
    setShown(0)
    since.current = performance.now()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [n])

  // the control, followed as the page settles and the window is resized; a missing optional one is skipped
  useLayoutEffect(() => {
    let frame = 0
    const measure = () => {
      frame = requestAnimationFrame(measure)
      const el = here ? find(step.target) : null
      const r = el?.getBoundingClientRect() ?? null
      setRect((was) => (rounded(was) === rounded(r) ? was : r))
      if (window.innerWidth !== win.width || window.innerHeight !== win.height) {
        setWin({ width: window.innerWidth, height: window.innerHeight })
        guide.current?.resize(window.innerWidth)
      }
      if (found) return
      if (el || !step.target) setFound(true)
      else if (performance.now() - since.current > WAIT) {
        if (step.optional) {
          const next = n + way.current
          if (next >= 0 && next < STEPS.length) setN(next)
          else setFound(true)
        } else setFound(true)
      }
    }
    measure()
    return () => cancelAnimationFrame(frame)
  }, [n, here, found, step, win])

  const spot = spotFor(found ? rect : null, win)
  const aim = rect && found ? { x: rect.left + rect.width / 2, y: rect.top + Math.min(rect.height / 2, 40) } : null
  const gesture: Gesture = step.gesture ?? (aim ? "point" : "wave")

  // there and doing it; the words start when they get there (or soon anyway)
  useEffect(() => {
    if (!found || leaving) return
    const g = guide.current
    if (!g) {
      setTalking(true)
      return
    }
    g.onArrive = () => setTalking(true)
    g.cue({ x: spot.x, gesture, aim })
    const anyway = setTimeout(() => setTalking(true), 1600)
    return () => clearTimeout(anyway)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [found, n, spot.x, gesture, aim?.x, aim?.y, leaving, loaded])

  // the words, a few at a time, as a game's box shows them
  useEffect(() => {
    const length = step.body.length
    if (!talking) return
    if (reduced) {
      setShown(length)
      return
    }
    let frame = 0
    const start = performance.now()
    const from = shown
    const type = () => {
      const now = Math.min(length, from + Math.floor(((performance.now() - start) / 1000) * 60))
      setShown(now)
      guide.current?.say(now < length)
      if (now < length) frame = requestAnimationFrame(type)
    }
    type()
    return () => {
      cancelAnimationFrame(frame)
      guide.current?.say(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [talking, n])

  const all = () => setShown(step.body.length)
  const finish = () => {
    markSeen()
    setLeaving(true)
    if (!guide.current) return setTour(false)
    guide.current.leave()
    setTimeout(() => setTour(false), 1100) // a wave and off the side of the window
  }
  const next = () => {
    if (shown < step.body.length) return all()
    if (n + 1 >= STEPS.length) return finish()
    way.current = 1
    setN(n + 1)
  }
  const back = () => {
    way.current = -1
    setN(Math.max(0, n - 1))
  }
  useEffect(() => {
    const press = (e: KeyboardEvent) => {
      if (leaving) return
      if (e.key === "Escape") finish()
      else if (e.key === "ArrowRight" || e.key === "Enter") (e.preventDefault(), next())
      else if (e.key === "ArrowLeft") back()
      else return
      e.stopPropagation()
    }
    window.addEventListener("keydown", press, true)
    return () => window.removeEventListener("keydown", press, true)
  })

  const pad = 6
  const lit = found && rect
  const at = PAGES.findIndex(([p]) => p === page)
  return (
    <div role="dialog" aria-modal="true" aria-label="Tour of Friday" className="gd-tour" data-leaving={leaving ? "" : undefined}>
      {!leaving &&
        (lit ? (
          <div className="gd-spot" style={{ left: rect.left - pad, top: rect.top - pad, width: rect.width + pad * 2, height: rect.height + pad * 2 }} />
        ) : (
          <div className="gd-dim" />
        ))}
      {/* over the dimmed page, under the box; still there after it, while they wave and go */}
      <canvas ref={canvas} className="gd-strip" aria-hidden="true" />
      {!leaving && (
        <div key={n} className="gd-box" style={{ left: spot.left, bottom: spot.bottom, width: spot.width }} onClick={all}>
          <div className="gd-where">
            <span>{PAGES[at]?.[1] ?? "Plan"}</span>
            <span className="gd-pages" aria-label={`Page ${at + 1} of ${PAGES.length}`}>
              {PAGES.map(([p], i) => (
                <i key={p} data-on={i === at ? "" : undefined} data-done={i < at ? "" : undefined} />
              ))}
            </span>
          </div>
          <h2 className="gd-title">{step.title}</h2>
          <p className="gd-body" aria-hidden="true">
            {step.body.slice(0, shown)}
            <span className="gd-rest">{step.body.slice(shown)}</span>
            {shown >= step.body.length && <span className="gd-caret" />}
          </p>
          <p className="gd-heard" aria-live="polite">
            {step.body}
          </p>
          <div className="gd-foot">
            <button className="gd-skip" onClick={finish}>
              Skip the tour
            </button>
            <span style={{ flex: 1 }} />
            {n > 0 && (
              <button className="gd-back" onClick={back}>
                Back
              </button>
            )}
            <button className="gd-go" onClick={(e) => (e.stopPropagation(), next())} autoFocus>
              {n + 1 >= STEPS.length ? "Done" : "Next"}
              <i />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

/** The tour the first time Friday opens on this device, once the calendar has drawn and Setup's questions are
 * answered. */
export function FirstTour({ ready }: { ready: boolean }) {
  const { setTour } = useShell()
  useEffect(() => {
    if (!ready || !tourDue()) return
    const timer = setTimeout(() => setTour(true), 900)
    return () => clearTimeout(timer)
  }, [ready, setTour])
  return null
}
