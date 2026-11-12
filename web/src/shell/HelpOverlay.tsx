// What's on this page (12 Nov: "if you hit the question mark, there should be text boxes next to the buttons on the
// page that say what they do with the page dimmed so the buttons and text boxes are highlighted"). A label beside every
// control was too much (12 Nov: "everything is super cluttered and it doesn't look good"), so: the page dims, its own
// controls stay lit with a small number on each, and one card lists what each number does. Pointing at a line lights
// its control, and pointing at a control lights its line. The sidebar's pages aren't numbered: the tour covers them.
// The words are kept here, by the control's data-tour name, so a page needs only its anchor; a control not on the page
// isn't listed. A click outside the card, Esc or the ? again closes it; the tour is a click away.

import { useEffect, useLayoutEffect, useState, type CSSProperties } from "react"
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

/** Not numbered: the sidebar's pages (the tour's), and the ? itself. */
const left = (key: string) => key.startsWith("nav-") || key === "settings" || key === "help"

interface Box {
  left: number
  top: number
  width: number
  height: number
}

export interface Mark {
  key: string
  n: number
  text: string
  box: Box // the control, with a little room around it
  big: boolean // a whole area (the calendar): numbered, not cut out of the dimming, or nothing would be dimmed
  badge: { left: number; top: number }
}

export const BADGE = 20
const ROW = 24 // controls this close in height count as one row when numbering

/** This page's controls, numbered in reading order (the small ones first, then the big areas), each with its badge. */
export function mark(found: { key: string; rect: DOMRect }[], width: number, height: number): Mark[] {
  const isBig = (r: DOMRect) => r.width * r.height > width * height * 0.3 // most of the window, not just a wide box
  const order = found
    .filter((f) => HELP[f.key] && !left(f.key))
    .sort((a, b) => Number(isBig(a.rect)) - Number(isBig(b.rect)) || Math.round(a.rect.top / ROW) - Math.round(b.rect.top / ROW) || a.rect.left - b.rect.left)
  const clamp = (v: number, most: number) => Math.min(Math.max(4, v), most - BADGE - 4)
  return order.map(({ key, rect: r }, i) => {
    const big = isBig(r)
    // on the control's top-left corner; inside a big area's
    const at = big ? { left: r.left + 10, top: r.top + 10 } : { left: r.left - BADGE / 2, top: r.top - BADGE / 2 }
    return {
      key,
      n: i + 1,
      text: HELP[key],
      box: { left: r.left - 4, top: r.top - 4, width: r.width + 8, height: r.height + 8 },
      big,
      badge: { left: clamp(at.left, width), top: clamp(at.top, height) },
    }
  })
}

export const CARD_W = 340
const EDGE = 16

/** The card's corner: a bottom one, on the side that covers fewer of the numbered controls. */
export function corner(marks: Mark[], width: number, height: number): "left" | "right" {
  const tall = 104 + marks.length * 34
  const covers = (x: number) =>
    marks.filter((m) => !m.big && m.box.left < x + CARD_W && m.box.left + m.box.width > x && m.box.top + m.box.height > height - EDGE - tall).length
  return covers(width - EDGE - CARD_W) < covers(EDGE) ? "right" : "left"
}

function visible(): { key: string; rect: DOMRect }[] {
  const seen = new Set<string>()
  const out: { key: string; rect: DOMRect }[] = []
  for (const el of document.querySelectorAll<HTMLElement>("[data-tour]")) {
    const key = el.dataset.tour as string
    if (!HELP[key] || left(key) || seen.has(key) || el.closest(".fr-help")) continue
    const r = el.getBoundingClientRect()
    if (r.width < 4 || r.height < 4 || r.bottom < 0 || r.top > window.innerHeight || r.right < 0 || r.left > window.innerWidth) continue
    seen.add(key)
    out.push({ key, rect: r })
  }
  return out
}

const inside = (b: Box, x: number, y: number) => x >= b.left && x <= b.left + b.width && y >= b.top && y <= b.top + b.height

function Badge({ n, on, style }: { n: number; on: boolean; style?: CSSProperties }) {
  return (
    <span
      aria-hidden="true"
      style={{
        display: "inline-grid",
        placeItems: "center",
        flex: "none",
        width: BADGE,
        height: BADGE,
        borderRadius: "50%",
        background: on ? "var(--color-accent)" : "color-mix(in srgb, var(--color-accent) 82%, black)",
        color: "#fff",
        fontSize: 11,
        fontWeight: 600,
        fontVariantNumeric: "tabular-nums",
        boxShadow: on ? "0 0 0 3px color-mix(in srgb, var(--color-accent) 35%, transparent)" : "0 1px 3px rgba(0,0,0,.35)",
        transition: "box-shadow 120ms, background 120ms",
        ...style,
      }}
    >
      {n}
    </span>
  )
}

export function HelpOverlay() {
  const { setHelp, setTour } = useShell()
  const [marks, setMarks] = useState<Mark[]>([])
  const [on, setOn] = useState<string | null>(null)
  const [size, setSize] = useState({ width: window.innerWidth, height: window.innerHeight })
  useLayoutEffect(() => {
    const measure = () => {
      setSize({ width: window.innerWidth, height: window.innerHeight })
      setMarks((was) => {
        const now = mark(visible(), window.innerWidth, window.innerHeight)
        return JSON.stringify(now) === JSON.stringify(was) ? was : now
      })
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
  const side = corner(marks, size.width, size.height)
  const lit = marks.filter((m) => !m.big)
  const point = (x: number, y: number) => setOn(lit.find((m) => inside(m.box, x, y))?.key ?? marks.find((m) => m.big && inside(m.box, x, y))?.key ?? null)
  return (
    <div
      className="fr-help"
      role="dialog"
      aria-label="What's on this page"
      onClick={() => setHelp(false)}
      onMouseMove={(e) => point(e.clientX, e.clientY)}
      style={{ position: "fixed", inset: 0, zIndex: 60, cursor: "pointer" }}
    >
      <svg width={size.width} height={size.height} style={{ position: "absolute", inset: 0 }} aria-hidden="true">
        <defs>
          <mask id="fr-help-holes">
            <rect width="100%" height="100%" fill="white" />
            {lit.map((m) => (
              <rect key={m.key} x={m.box.left} y={m.box.top} width={m.box.width} height={m.box.height} rx="8" fill="black" />
            ))}
          </mask>
        </defs>
        <rect width="100%" height="100%" fill="rgba(6, 8, 12, 0.58)" mask="url(#fr-help-holes)" />
        {marks.map((m) =>
          m.big && m.key !== on ? null : (
            <rect
              key={m.key}
              x={m.box.left}
              y={m.box.top}
              width={m.box.width}
              height={m.box.height}
              rx="8"
              fill="none"
              stroke="var(--color-accent)"
              strokeWidth={m.key === on ? 2 : 1}
              strokeOpacity={m.key === on ? 1 : on ? 0.3 : 0.6}
              strokeDasharray={m.big ? "6 5" : undefined}
            />
          ),
        )}
      </svg>
      {marks.map((m) => (
        <Badge key={m.key} n={m.n} on={m.key === on} style={{ position: "absolute", left: m.badge.left, top: m.badge.top }} />
      ))}
      <section
        className="fr-float"
        onClick={(e) => e.stopPropagation()}
        onMouseMove={(e) => e.stopPropagation()}
        onMouseLeave={() => setOn(null)}
        style={{
          position: "absolute",
          bottom: EDGE,
          [side]: EDGE,
          width: CARD_W,
          maxHeight: size.height - 2 * EDGE,
          display: "flex",
          flexDirection: "column",
          gap: 10,
          padding: "14px 12px 12px",
          cursor: "default",
        }}
      >
        <h2 style={{ margin: "0 4px", fontSize: 14, fontWeight: 600 }}>What's on this page</h2>
        <ol style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 2, overflowY: "auto" }}>
          {marks.map((m) => (
            <li
              key={m.key}
              onMouseEnter={() => setOn(m.key)}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: 10,
                padding: "6px 6px",
                borderRadius: "var(--radius-md)",
                fontSize: 13,
                lineHeight: 1.4,
                textWrap: "pretty",
                background: m.key === on ? "color-mix(in srgb, var(--color-accent) 14%, transparent)" : undefined,
              }}
            >
              <Badge n={m.n} on={m.key === on} />
              <span style={{ paddingTop: 1 }}>{m.text}</span>
            </li>
          ))}
        </ol>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button className="btn btn-secondary" onClick={() => (setHelp(false), setTour(true))}>
            Take the tour
          </button>
          <button className="btn btn-primary" onClick={() => setHelp(false)} autoFocus>
            Close
          </button>
        </div>
      </section>
    </div>
  )
}
