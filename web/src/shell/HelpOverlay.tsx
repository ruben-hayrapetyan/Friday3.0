// What's on this page (12 Nov: "if you hit the question mark, there should be text boxes next to the buttons on the
// page that say what they do with the page dimmed so the buttons and text boxes are highlighted"): the ? beside
// Settings dims the page, leaves its main controls lit, and puts a short label beside each. The labels are kept here,
// by the control's data-tour name, so a page needs only its anchor; a control not on the page isn't labelled. A click
// anywhere, Esc or the ? again closes it; the tour is a click away.

import { useEffect, useLayoutEffect, useState } from "react"
import { useShell } from "./ShellContext"

/** What each anchored control does, in a few words. */
export const HELP: Record<string, string> = {
  "nav-plan": "Plan: your week, with work fitted around your events",
  "nav-todo": "To-do: everything you have to do",
  "nav-projects": "Projects in steps, and exams with their prep",
  "nav-inbox": "Inbox: what Friday found, and its questions for you",
  "nav-insights": "Insights: how long things take you, and how weeks went",
  "nav-rules": "Rules: how you like your days, and notes about you",
  settings: "Settings: calendars, mail, other apps, look and setup",
  help: "This help: press again or Esc to close",
  menu: "Pages and settings",
  views: "Show a day, three days, a week or a month",
  search: "Find anything: to-dos, events, settings (⌘K)",
  "plan-menu": "Change the plan: pace, take time back, try a change, ask your AI",
  show: "What the calendar shows: the past, each calendar",
  drawer: "Your to-dos beside the calendar",
  attention: "What needs a look: late work, slipping deadlines",
  calendar: "Click a block to start, finish or move it; double-click empty time for a new event",
  now: "What's on now: start, pause or finish it here",
  "drawer-add": "Add a to-do the way you'd say it: “essay 3h due fri”",
  "todo-lists": "Short term, long term, or everything with a due date",
  "todo-list": "Click a to-do for everything about it; ⌘-click to pick several",
  "projects-new": "Start a project or add an exam",
  inbox: "Open one to accept it, change it or say no",
  insights: "Your last weeks in a few numbers",
  "rule-new": "Type a rule, or a note about you, in your own words",
  "week-paces": "Days that go easier or harder every week",
  tracking: "Your sleep and meals as you've logged them",
  "settings-nav": "Each part of Settings",
}

interface Label {
  key: string
  text: string
  hole: { left: number; top: number; width: number; height: number }
  at: { left: number; top: number }
  side: "right" | "left" | "below" | "inside"
  lit: boolean // cut out of the dimming: a control, not a whole area (a lit calendar would leave nothing dimmed)
}

const W = 230 // a label's width, at most
const H = 44 // room kept for a label's height when placing them apart
const GAP = 10

/** The labels for what's on screen now, each beside its control and kept clear of the others. */
export function place(found: { key: string; rect: DOMRect }[], width: number, height: number): Label[] {
  const placed: Label[] = []
  const clashes = (l: { left: number; top: number }) => placed.some((p) => l.left < p.at.left + W && l.left + W > p.at.left && l.top < p.at.top + H && l.top + H > p.at.top)
  for (const { key, rect } of found) {
    const hole = { left: rect.left - 4, top: rect.top - 4, width: rect.width + 8, height: rect.height + 8 }
    const big = rect.width > width * 0.5 || rect.height > height * 0.5
    let side: Label["side"] = big ? "inside" : rect.right + GAP + W < width ? "right" : rect.left - GAP - W > 0 ? "left" : "below"
    let at =
      side === "inside"
        ? { left: rect.left + rect.width / 2 - W / 2, top: rect.top + rect.height / 2 - H / 2 }
        : side === "right"
          ? { left: rect.right + GAP, top: rect.top + rect.height / 2 - H / 2 }
          : side === "left"
            ? { left: rect.left - GAP - W, top: rect.top + rect.height / 2 - H / 2 }
            : { left: Math.min(Math.max(8, rect.left), width - W - 8), top: rect.bottom + GAP }
    // moved down, a little at a time, until it clears the labels already placed
    for (let n = 0; n < 12 && clashes(at); n++) at = { ...at, top: at.top + H / 2 + 4 }
    if (at.top + H > height) {
      side = side === "below" ? "below" : side
      at = { ...at, top: Math.max(8, height - H - 8) }
    }
    placed.push({ key, text: HELP[key], hole, at, side, lit: !big })
  }
  return placed
}

function visible(): { key: string; rect: DOMRect }[] {
  const seen = new Set<string>()
  const out: { key: string; rect: DOMRect }[] = []
  for (const el of document.querySelectorAll<HTMLElement>("[data-tour]")) {
    const key = el.dataset.tour as string
    if (!HELP[key] || seen.has(key) || el.closest(".fr-help")) continue
    const r = el.getBoundingClientRect()
    if (r.width < 4 || r.height < 4 || r.bottom < 0 || r.top > window.innerHeight || r.right < 0 || r.left > window.innerWidth) continue
    seen.add(key)
    out.push({ key, rect: r })
  }
  // the page's own controls before the big areas, so the small ones get the room beside them
  return out.sort((a, b) => a.rect.width * a.rect.height - b.rect.width * b.rect.height)
}

export function HelpOverlay() {
  const { setHelp, setTour } = useShell()
  const [labels, setLabels] = useState<Label[]>([])
  const [size, setSize] = useState({ width: window.innerWidth, height: window.innerHeight })
  useLayoutEffect(() => {
    const measure = () => {
      setSize({ width: window.innerWidth, height: window.innerHeight })
      setLabels(place(visible(), window.innerWidth, window.innerHeight))
    }
    measure()
    // again as the page settles (a calendar still drawing when the ? was pressed), and with the window
    const again = window.setInterval(measure, 500)
    window.addEventListener("resize", measure)
    return () => (window.clearInterval(again), window.removeEventListener("resize", measure))
  }, [])
  useEffect(() => {
    const key = (e: KeyboardEvent) => e.key === "Escape" && setHelp(false)
    window.addEventListener("keydown", key)
    return () => window.removeEventListener("keydown", key)
  }, [setHelp])
  return (
    <div className="fr-help" role="dialog" aria-label="What's on this page" onClick={() => setHelp(false)} style={{ position: "fixed", inset: 0, zIndex: 60, cursor: "pointer" }}>
      <svg width={size.width} height={size.height} style={{ position: "absolute", inset: 0 }} aria-hidden="true">
        <defs>
          <mask id="fr-help-holes">
            <rect width="100%" height="100%" fill="white" />
            {labels
              .filter((l) => l.lit)
              .map((l) => (
                <rect key={l.key} x={l.hole.left} y={l.hole.top} width={l.hole.width} height={l.hole.height} rx="8" fill="black" />
              ))}
          </mask>
        </defs>
        <rect width="100%" height="100%" fill="rgba(6, 8, 12, 0.62)" mask="url(#fr-help-holes)" />
        {labels
          .filter((l) => l.lit)
          .map((l) => (
            <rect key={l.key} x={l.hole.left} y={l.hole.top} width={l.hole.width} height={l.hole.height} rx="8" fill="none" stroke="var(--color-accent)" strokeWidth="1.5" />
          ))}
      </svg>
      {labels.map((l) => (
        <span
          key={l.key}
          role="note"
          className="fr-float"
          style={{ position: "absolute", left: l.at.left, top: l.at.top, maxWidth: W, padding: "7px 10px", fontSize: 12.5, lineHeight: 1.35, textWrap: "pretty", borderRadius: "var(--radius-md)", boxShadow: "inset 0 0 0 1px var(--color-accent), var(--shadow-lg)" }}
        >
          {l.text}
        </span>
      ))}
      <div className="fr-float" onClick={(e) => e.stopPropagation()} style={{ position: "absolute", left: 16, bottom: 16, display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, padding: "8px 10px 8px 16px", borderRadius: "var(--radius-lg)", cursor: "default" }}>
        <span style={{ fontWeight: 500 }}>What's on this page</span>
        <button className="btn btn-secondary" onClick={() => (setHelp(false), setTour(true))}>
          Take the tour
        </button>
        <button className="btn btn-primary" onClick={() => setHelp(false)} autoFocus>
          Close
        </button>
      </div>
    </div>
  )
}
