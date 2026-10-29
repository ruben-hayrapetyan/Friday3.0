// A short tour of Friday: shown once, the first time it opens, and again from the ? beside Settings, from search
// ("Take the tour") or the Mac app's Help menu. Each step lights up the control it's about; a step whose control
// isn't on screen (nothing needs you today, a narrow window without the sidebar) is skipped, or shown in the middle
// when it says something you need anyway.

import { useEffect, useLayoutEffect, useState } from "react"
import { useLocation, useNavigate } from "react-router"
import { Icon } from "@/components/fr/controls"
import { useShell } from "./ShellContext"

export interface Step {
  target?: string // the control's data-tour name; none: in the middle of the window
  title: string
  body: string
  optional?: boolean // skipped when its control isn't there; otherwise shown in the middle
}

export const STEPS: Step[] = [
  {
    title: "Welcome to Friday",
    body: "Friday fits your to-dos into the free time around your events, and replans whenever something changes. Here’s a quick look around.",
  },
  {
    target: "nav",
    title: "Your pages",
    body: "Plan is home: your calendar with the work Friday planned. To-do has every task. Inbox holds what Friday found on your calendars and mail, for you to accept. Review asks how the day went, which is how Friday learns. Rules are how you like your days.",
  },
  {
    target: "menu",
    title: "Your pages",
    body: "The menu opens your pages: Plan, To-do, Inbox, Review, Rules and the rest.",
    optional: true,
  },
  {
    target: "calendar",
    title: "Your calendar",
    body: "Grey blocks are your events; coloured ones are work Friday planned. Click one to start it, mark it done or move it. Drag to move it; ⌘-click several to move or change them together; double-click an empty time to add an event.",
  },
  {
    target: "attention",
    title: "When something needs you",
    body: "If something will be late, a day is too full or two events overlap, it shows here, with ways out.",
    optional: true,
  },
  {
    target: "views",
    title: "Day, week or month",
    body: "Switch the view here. The arrows beside the date step back and forward; the date takes you back to today.",
    optional: true,
  },
  {
    target: "show",
    title: "What’s hidden",
    body: "Office hours and calendars with a toggle stay off your calendar. Switch them on here when you want to see them; they never change the plan.",
    optional: true,
  },
  {
    target: "plan-menu",
    title: "Change the plan",
    body: "Ask the AI in your own words (“move my 5pm to Thursday”), see other ways to plan your week, shove work out of a busy stretch, or set the pace.",
  },
  {
    target: "drawer",
    title: "Your to-do list",
    body: "Slides out beside the calendar (or press T). Type a task the way you’d say it: “essay 3h due Fri”.",
  },
  {
    target: "search",
    title: "Find anything",
    body: "Tasks, events, pages and actions, from anywhere with ⌘K.",
  },
  {
    target: "now",
    title: "Right now",
    body: "What Friday suggests doing now. Start the timer when you begin: Friday learns how long things really take you.",
    optional: true,
  },
  {
    target: "help",
    title: "That’s it",
    body: "Settings has your calendars, schedule and integrations, and Setup’s questions again. The ? brings this tour back whenever you want it.",
  },
]

const SEEN = "friday-tour-seen"

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
  for (const el of document.querySelectorAll<HTMLElement>(`[data-tour="${target}"]`)) {
    const r = el.getBoundingClientRect()
    if (r.width > 0 && r.height > 0) return el
  }
  return null
}

/** The steps to show now: optional ones only when their control is on screen. */
export function stepsFor(present: (target: string) => boolean): Step[] {
  return STEPS.filter((s) => !s.optional || (s.target !== undefined && present(s.target)))
}

/** Where the card goes: below the control when there's room, else above, else beside; kept inside the window. */
export function cardPlace(rect: DOMRect | null, card: { width: number; height: number }, win: { width: number; height: number }): { left: number; top: number } {
  const margin = 12
  if (!rect) return { left: (win.width - card.width) / 2, top: Math.max(margin, (win.height - card.height) / 2) }
  const clampX = (x: number) => Math.min(Math.max(margin, x), win.width - card.width - margin)
  const clampY = (y: number) => Math.min(Math.max(margin, y), win.height - card.height - margin)
  if (rect.width > win.width * 0.5 && rect.height > win.height * 0.5) {
    // something as big as the calendar: the card in the middle of it
    return { left: clampX(rect.left + (rect.width - card.width) / 2), top: clampY(rect.top + (rect.height - card.height) / 2) }
  }
  if (rect.bottom + 12 + card.height <= win.height - margin) return { left: clampX(rect.left), top: rect.bottom + 12 }
  if (rect.top - 12 - card.height >= margin) return { left: clampX(rect.left), top: rect.top - 12 - card.height }
  if (rect.right + 12 + card.width <= win.width - margin) return { left: rect.right + 12, top: clampY(rect.top) }
  return { left: clampX(rect.left - 12 - card.width), top: clampY(rect.top) }
}

export function Tour() {
  const { setTour, setDrawer, setPop, setDialog } = useShell()
  const navigate = useNavigate()
  const location = useLocation()
  const [steps] = useState(() => stepsFor((t) => find(t) !== null))
  const [n, setN] = useState(0)
  const [rect, setRect] = useState<DOMRect | null>(null)
  const [win, setWin] = useState({ width: window.innerWidth, height: window.innerHeight })
  const step = steps[Math.min(n, steps.length - 1)]
  useEffect(() => {
    if (location.pathname !== "/") navigate("/") // the tour is of the calendar's page
    setDrawer(false)
    setPop(null)
    setDialog(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useLayoutEffect(() => {
    let frame = 0
    const measure = () => {
      setRect(find(step.target)?.getBoundingClientRect() ?? null)
      setWin({ width: window.innerWidth, height: window.innerHeight })
      frame = requestAnimationFrame(measure) // follows the page as it settles and the window as it's resized
    }
    measure()
    return () => cancelAnimationFrame(frame)
  }, [step.target])
  const close = () => (markSeen(), setTour(false))
  const next = () => (n + 1 >= steps.length ? close() : setN(n + 1))
  const back = () => setN(Math.max(0, n - 1))
  useEffect(() => {
    const press = (e: KeyboardEvent) => {
      if (e.key === "Escape") close()
      else if (e.key === "ArrowRight" || e.key === "Enter") (e.preventDefault(), next())
      else if (e.key === "ArrowLeft") back()
      else return
      e.stopPropagation()
    }
    window.addEventListener("keydown", press, true)
    return () => window.removeEventListener("keydown", press, true)
  })
  const card = { width: Math.min(340, win.width - 24), height: 190 }
  const at = cardPlace(rect, card, win)
  const pad = 6
  return (
    <div role="dialog" aria-modal="true" aria-label="Tour of Friday" style={{ position: "fixed", inset: 0, zIndex: 60 }}>
      {rect ? (
        <div
          style={{
            position: "fixed",
            left: rect.left - pad,
            top: rect.top - pad,
            width: rect.width + pad * 2,
            height: rect.height + pad * 2,
            borderRadius: 10,
            boxShadow: "0 0 0 9999px color-mix(in srgb, #000 55%, transparent), 0 0 0 2px var(--color-accent)",
            transition: "all 180ms ease",
            pointerEvents: "none",
          }}
        />
      ) : (
        <div style={{ position: "fixed", inset: 0, background: "color-mix(in srgb, #000 55%, transparent)" }} />
      )}
      <div className="fr-float fr-dialog" style={{ position: "fixed", left: at.left, top: at.top, width: card.width, display: "flex", flexDirection: "column", gap: 10, padding: 18, transition: "left 180ms ease, top 180ms ease" }}>
        <span className="fr-kicker">
          {n + 1} of {steps.length}
        </span>
        <span className="fr-h" style={{ fontSize: 20 }}>
          {step.title}
        </span>
        <span style={{ textWrap: "pretty", color: "var(--color-neutral-200)", lineHeight: 1.45 }}>{step.body}</span>
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 4 }}>
          <button className="fr-plain fr-hover-text" onClick={close} style={{ fontSize: 12, color: "var(--color-neutral-500)" }}>
            Skip the tour
          </button>
          <span style={{ flex: 1 }} />
          {n > 0 && (
            <button className="btn btn-ghost" onClick={back}>
              Back
            </button>
          )}
          <button className="btn btn-primary" onClick={next} autoFocus>
            {n + 1 >= steps.length ? "Done" : "Next"}
            {n + 1 < steps.length && <Icon name="arrow-right" size={14} />}
          </button>
        </div>
      </div>
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
