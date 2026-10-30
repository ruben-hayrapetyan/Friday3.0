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
  bullets: string[] // what it says, a few words a line (30 Oct: "keep text to bullet points")
  gesture?: Gesture // what they do there: point at the control when not said
  jump?: boolean // a hop on getting there; when not said, a hop to point at something up the window
  cheer?: boolean // both arms up for the hop
  sweep?: boolean // pointing down the control and back, as a finger down a list
  sign?: string // over their head on getting there ("?", "z", "sweat", "!", "heart", "note")
  after?: string // and once they've said it
  finale?: boolean // the end: sunglasses on, a dance by the sign to the weekend, and off to it
  optional?: boolean // skipped when its control isn't there; otherwise said anyway
}

// 30 Oct: "make it a little shorter, have the sprite do more (like jump and point to something)... keep text to
// bullet points", then "be creative, have the guide do unique actions. and have the final animation be something to
// do with friday and going to the weekend"
export const STEPS: Step[] = [
  {
    title: "Welcome to Friday",
    bullets: ["Your week is set up", "Friday plans your to-dos around your events", "A quick look round: about a minute"],
    gesture: "wave",
    jump: true,
    cheer: true,
    after: "heart",
  },
  {
    target: "nav",
    title: "Your pages",
    bullets: ["Plan: your calendar, with the work planned", "To-do, Projects, Inbox and Rules", "Insights and Sleep & meals: what Friday learns"],
    sweep: true,
  },
  {
    target: "menu",
    title: "Your pages",
    bullets: ["The menu opens every page"],
    optional: true,
  },
  {
    target: "calendar",
    title: "Your week",
    bullets: ["Grey: your events · coloured: planned work", "Drag to move; drag an edge to resize", "Double-click empty time to add an event"],
    gesture: "drag",
  },
  {
    target: "block",
    title: "A planned block",
    bullets: ["Start when you sit down to it, Done when it’s done", "Friday learns how long things take you", "Pin it to keep it where it is"],
    gesture: "timer",
    optional: true,
  },
  {
    target: "attention",
    title: "When work runs late",
    bullets: ["Late work and too-full days show here", "With ways out: skip, move or ease off"],
    gesture: "worry",
    sign: "sweat",
    optional: true,
  },
  {
    target: "plan-menu",
    title: "Change the plan",
    bullets: ["Ask the AI: “move my 5pm to Thursday”", "Shove work out of a busy stretch", "What if (beside it): try a change first"],
  },
  {
    target: "search",
    title: "Find anything",
    bullets: ["Tasks, events, settings: ⌘K", "No match? Enter adds it as a to-do"],
    gesture: "search",
  },
  {
    target: "now",
    title: "Right now",
    bullets: ["What to do now", "Start the timer (Space) when you begin"],
    gesture: "watch",
    optional: true,
  },
  {
    page: "/todo",
    target: "todo-list",
    title: "To-do",
    bullets: ["Type it as you’d say it: “essay 3h due Fri”", "No length? Friday guesses", "T opens this list beside the calendar"],
    gesture: "write",
  },
  {
    page: "/inbox",
    target: "inbox",
    title: "Inbox",
    bullets: ["What only you can decide", "How much of the plan you did", "Events found in your mail and calendars"],
    gesture: "mail",
    after: "heart",
  },
  {
    page: "/projects",
    target: "projects-new",
    title: "Projects & exams",
    bullets: ["Exams come from your class calendar, prep planned", "Projects: big things, split into steps"],
    gesture: "book",
  },
  {
    page: "/rules",
    target: "rule-new",
    title: "Rules",
    bullets: ["How you like your days, in your own words", "Prefer, Strongly or Always"],
    gesture: "think",
    sign: "?",
    after: "!",
  },
  {
    page: "/insights",
    target: "insights",
    title: "Insights",
    bullets: ["How long things really take you", "What Friday learned, for you to approve"],
    gesture: "eureka",
    sign: "!",
  },
  {
    page: "/body",
    target: "tracking",
    title: "Sleep & meals",
    bullets: ["Track them in a tap from the Now bar", "Friday plans around when you really sleep and eat"],
    gesture: "yawn",
    sign: "z",
  },
  {
    page: "/settings",
    target: "settings-nav",
    title: "Settings",
    bullets: ["Calendars, Google accounts and the AI", "Setup’s questions again, any time"],
    gesture: "fix",
  },
  {
    target: "help",
    title: "That’s Friday!",
    bullets: ["The ? brings this tour back", "Next stop: the weekend"],
    gesture: "dance",
    jump: true,
    cheer: true,
    finale: true,
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
const SIGN = 170 // the room the sign to the weekend takes at the window's right

/** Where the guide stands (`x`, from the window's left) and where their box goes (`left`, and `bottom` up from the
 * window's foot): below the control, pointing up at it, with the box beside them on the side with room; beside a
 * control down where they stand, the box on its far side; the two side by side in the middle with no control; and on
 * a phone, the box above them. */
export function spotFor(rect: Box | null, win: Size, byTheSign = false): { x: number; left: number; bottom: number; width: number } {
  const width = Math.min(BOX, win.width - 2 * MARGIN)
  if (win.width < 2 * BODY + GAP + width + 2 * MARGIN) return { x: MARGIN + BODY, left: (win.width - width) / 2, bottom: STRIP - 12, width }
  if (byTheSign) {
    // the end: beside the sign to the weekend at the window's right, the box on their other side
    const x = Math.max(MARGIN + width + GAP + BODY, win.width - SIGN - BODY - 10)
    return { x, left: x - BODY - GAP - width, bottom: 18, width }
  }
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
  const text = step.bullets.join("") // typed out line by line
  const starts = step.bullets.map((_, i) => step.bullets.slice(0, i).join("").length)
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

  const spot = spotFor(found ? rect : null, win, step.finale)
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
    // a hop on getting there when the step says, or to point at something up the window; the step's own action,
    // its signs, and for the end, sunglasses
    const sweep = step.sweep && rect ? { top: Math.max(rect.top + 20, 10), bottom: Math.min(rect.bottom - 20, win.height - STRIP) } : undefined
    g.cue({ x: spot.x, gesture, aim, jump: step.jump ?? (gesture === "point" && !!aim && aim.y < win.height * 0.25), cheer: step.cheer, sweep, sign: step.sign, after: step.after, shades: step.finale })
    const anyway = setTimeout(() => setTalking(true), 1600)
    return () => clearTimeout(anyway)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [found, n, spot.x, gesture, aim?.x, aim?.y, leaving, loaded])

  // the words, a few at a time, as a game's box shows them
  useEffect(() => {
    const length = text.length
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
      else guide.current?.said() // a nod, or a sign
    }
    type()
    return () => {
      cancelAnimationFrame(frame)
      guide.current?.say(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [talking, n])

  const all = () => setShown(text.length)
  const finish = () => {
    markSeen()
    setLeaving(true)
    if (!guide.current) return setTour(false)
    // off the side of the window; at the end, skipping off to the weekend past its sign
    guide.current.onGone = () => setTour(false)
    guide.current.leave(!!step.finale)
    setTimeout(() => setTour(false), 4000)
  }
  const next = () => {
    if (shown < text.length) return all()
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
  const at = step.finale ? PAGES.length : PAGES.findIndex(([p]) => p === page) // the end: every page seen
  return (
    <div role="dialog" aria-modal="true" aria-label="Tour of Friday" className="gd-tour" data-leaving={leaving ? "" : undefined}>
      {!leaving &&
        (lit ? (
          <div className="gd-spot" style={{ left: rect.left - pad, top: rect.top - pad, width: rect.width + pad * 2, height: rect.height + pad * 2 }} />
        ) : (
          <div className="gd-dim" />
        ))}
      {step.finale && (found || leaving) && (
        <div className="gd-sign" aria-hidden="true">
          <span>Weekend →</span>
          <i />
        </div>
      )}
      {/* over the dimmed page, under the box; still there after it, while they wave and go */}
      <canvas ref={canvas} className="gd-strip" aria-hidden="true" style={{ height: STRIP }} />
      {!leaving && (
        <div key={n} className="gd-box" style={{ left: spot.left, bottom: spot.bottom, width: spot.width }} onClick={all}>
          <div className="gd-where">
            <span>{step.finale ? "Weekend" : (PAGES[at]?.[1] ?? "Plan")}</span>
            <span className="gd-pages" aria-label={step.finale ? "Every page" : `Page ${at + 1} of ${PAGES.length}`}>
              {PAGES.map(([p], i) => (
                <i key={p} data-on={i === at ? "" : undefined} data-done={i < at ? "" : undefined} />
              ))}
            </span>
          </div>
          <h2 className="gd-title">{step.title}</h2>
          <ul className="gd-body" aria-hidden="true">
            {step.bullets.map((line, i) => {
              const from = starts[i]
              const said = Math.max(0, Math.min(line.length, shown - from))
              return (
                <li key={i} data-said={said > 0 ? "" : undefined}>
                  {line.slice(0, said)}
                  <span className="gd-rest">{line.slice(said)}</span>
                  {i === step.bullets.length - 1 && shown >= text.length && <span className="gd-caret" />}
                </li>
              )
            })}
          </ul>
          <p className="gd-heard" aria-live="polite">
            {step.bullets.join(". ")}
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
