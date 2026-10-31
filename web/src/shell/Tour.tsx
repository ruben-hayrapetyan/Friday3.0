// Getting to know Friday, by doing it (31 Oct: "right now i really don't love the app tour. its kindof tedious and
// boring, make it better"): not a slideshow of Next, Next, Next but six small quests done in the app itself, at your
// own pace, with the guide from setup beside them (dialogs/walk/Guide.ts). Each quest notices when you've done it (a
// command you ran, a page you opened, a block you clicked) and the guide cheers; "Show me" sends them running to the
// control it's about. Nothing is dimmed or blocked: the card sits in a corner and tucks away into a pill. All six
// done, the guide tears Friday off the calendar and dances off to the weekend.
//
// It opens by itself once, when setup first finishes (`setup.toured`, kept by Friday, not the window: 31 Oct, "make
// sure that when the initialization screen gets merged into the main, that it doesn't run every time"), then only from
// the ? beside Settings, search ("Take the tour") or the Mac app's Help menu. Where you are in it is kept on this
// device; a tucked-away card comes back as its pill until you finish or close it.

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import { useLocation, useNavigate } from "react-router"
import { useQueryClient } from "@tanstack/react-query"
import { command, type Schemas } from "@/api/client"
import type { Gesture, Guide } from "@/dialogs/walk/Guide"
import { STRIP } from "@/dialogs/walk/strip"
import { useShell } from "./ShellContext"
import "./guide.css"

export interface Quest {
  id: string
  title: string
  hint: string
  page?: string // where "Show me" takes you
  target?: string // the control it points at (a data-tour name; "block": a planned block on the calendar)
  gesture: Gesture // what the guide does showing you
  drawer?: "open" | "closed" // "Show me" opens the to-do list beside the calendar, or closes it to show the calendar
  done: Partial<Signal> // what counts as done
}

/** What you did that a quest can count: a command that ran, a page you opened, a block you clicked, a dialog. */
export interface Signal {
  command: string
  page: string
  picked: boolean
  dialog: string
}

export const QUESTS: Quest[] = [
  { id: "add", title: "Add a to-do", hint: "Type it as you’d say it: “essay 3h due Fri”", page: "/", target: "drawer-add", gesture: "write", drawer: "open", done: { command: "add" } },
  { id: "find", title: "Find where Friday put it", hint: "Click a coloured block: work Friday planned", page: "/", target: "block", gesture: "point", drawer: "closed", done: { picked: true } },
  { id: "start", title: "Start working on it", hint: "Start, on the block or with Space: Friday learns your pace", page: "/", target: "now", gesture: "timer", drawer: "closed", done: { command: "start" } },
  { id: "search", title: "Find anything", hint: "⌘K: tasks, events, settings, all in one place", page: "/", target: "search", gesture: "search", done: { dialog: "search" } },
  { id: "inbox", title: "Look in your Inbox", hint: "What needs you waits there, a message each", page: "/inbox", target: "inbox", gesture: "mail", done: { page: "/inbox" } },
  { id: "rule", title: "Write a rule", hint: "In your own words: “no work after 10pm”", page: "/rules", target: "rule-new", gesture: "think", done: { command: "rule_add" } },
]

/** The quests a signal completes, of those not done yet. */
export function completes(signal: Partial<Signal>, done: string[]): string[] {
  return QUESTS.filter(
    (q) =>
      !done.includes(q.id) &&
      Object.entries(q.done).every(([k, v]) => (k === "page" ? signal.page !== undefined && signal.page.startsWith(String(v)) : signal[k as keyof Signal] === v)),
  ).map((q) => q.id)
}

// What the card says when one's done, in turn
const CHEERS = ["Nice!", "There you go!", "Look at you!", "Nailed it!", "Easy, right?", "One more!"]

interface Kept {
  done: string[]
  small: boolean // tucked away into the pill
  over: boolean // finished or closed
}

const KEY = "friday-quests"

export function keptQuests(): Kept | null {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as Kept) : null
  } catch {
    return null
  }
}

function keep(k: Kept): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(k))
  } catch {
    // private mode: it starts over next visit
  }
}

/** Whether the quests are under way on this device (to bring the pill back when Friday opens). */
export function questsUnderway(): boolean {
  const k = keptQuests()
  return !!k && !k.over
}

/** The visible element a quest points at, if any. */
function find(target?: string): HTMLElement | null {
  if (!target) return null
  const selector = target === "block" ? '[data-block-key^="T"]' : `[data-tour="${target}"]`
  for (const el of document.querySelectorAll<HTMLElement>(selector)) {
    const r = el.getBoundingClientRect()
    if (r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < window.innerHeight) return el
  }
  return null
}

export const CARD = 330 // the card's width, at most
const MARGIN = 16
const BODY = 48 // half the guide's width with an arm out
const NARROW = 640 // below this, the card alone: no room for the guide
const SHOW_FOR = 6000 // ms the guide stays by a control they're showing you

/** Where the guide stands by default: just left of the card, which sits in the window's bottom-right corner. */
export function homeOf(width: number): number {
  return width - MARGIN - Math.min(CARD, width - 2 * MARGIN) - 12 - BODY
}

/** Where the guide stands to show you a control: below it, kept clear of the card. */
export function standFor(rect: { left: number; width: number }, width: number): number {
  return Math.min(Math.max(rect.left + rect.width / 2, MARGIN + BODY), homeOf(width))
}

export function Tour() {
  const { setTour, setDrawer, selected, dialog } = useShell()
  const navigate = useNavigate()
  const location = useLocation()
  const reduced = useMemo(() => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false, [])
  const [kept, setKept] = useState<Kept>(() => {
    const k = keptQuests()
    return k && !k.over ? k : { done: [], small: false, over: false }
  })
  const [current, setCurrent] = useState<string | null>(null) // the quest picked, else the first left
  const [cheer, setCheer] = useState<string | null>(null) // just done: what the card says a moment
  const [just, setJust] = useState<string | null>(null) // the quest just done, for its tick
  const [showing, setShowing] = useState<Quest | null>(null) // "Show me" under way
  const [ring, setRing] = useState<DOMRect | null>(null) // the control being shown
  const [width, setWidth] = useState(window.innerWidth)
  const [loaded, setLoaded] = useState(false)
  const [torn, setTorn] = useState(false)
  const [glowing, setGlowing] = useState(false)
  const [leaving, setLeaving] = useState(false)
  const [where, setWhere] = useState<{ x: number; width: number; height: number } | null>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const guide = useRef<Guide | null>(null)
  const row = useRef<HTMLLIElement>(null)
  const calendar = useRef<HTMLDivElement>(null)
  const later = useRef<number[]>([])
  const left = QUESTS.filter((q) => !kept.done.includes(q.id))
  const quest = QUESTS.find((q) => q.id === current && !kept.done.includes(q.id)) ?? left[0] ?? null
  const finished = left.length === 0
  const roomy = width >= NARROW
  const card = Math.min(CARD, width - 2 * MARGIN)
  const save = (k: Kept) => (keep(k), setKept(k))
  // kept from the start, not only once one's done: Friday opened again before any, the quests come back with it
  useEffect(() => {
    if (!keptQuests()) keep(kept)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

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
    const timers = later.current
    return () => {
      gone = true
      timers.forEach(clearTimeout)
      guide.current?.dispose()
      guide.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // done: whatever you did that a quest counts
  const latest = useRef(kept)
  latest.current = kept
  const mark = (signal: Partial<Signal>) => {
    const was = latest.current
    const now = completes(signal, was.done)
    if (!now.length || was.over) return
    const next = { ...was, done: [...was.done, ...now] }
    latest.current = next
    save(next)
    setJust(now[0])
    setCheer(CHEERS[(next.done.length - 1) % CHEERS.length])
    setShowing(null)
    setRing(null)
    if (next.done.length < QUESTS.length) guide.current?.celebrate()
  }
  useEffect(() => {
    const ran = (e: Event) => mark({ command: (e as CustomEvent<{ name: string }>).detail.name })
    window.addEventListener("friday:command", ran)
    return () => window.removeEventListener("friday:command", ran)
  })
  useEffect(() => mark({ page: location.pathname }), [location.pathname]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (selected?.key.startsWith("T")) mark({ picked: true })
  }, [selected?.key]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (dialog) mark({ dialog })
  }, [dialog]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!cheer) return
    const t = setTimeout(() => (setCheer(null), setJust(null)), 2200)
    return () => clearTimeout(t)
  }, [cheer])

  // following the window, the control being shown, and the guide (for a poke)
  useLayoutEffect(() => {
    let frame = 0
    const measure = () => {
      frame = requestAnimationFrame(measure)
      if (window.innerWidth !== width) {
        setWidth(window.innerWidth)
        guide.current?.resize(window.innerWidth)
      }
      const at = guide.current?.box()
      if (at) setWhere((was) => (was && Math.abs(was.x - at.x) < 2 && was.height === at.height ? was : at))
      if (showing) {
        const r = find(showing.target)?.getBoundingClientRect() ?? null
        setRing((was) => (r && was && Math.abs(was.left - r.left) < 1 && Math.abs(was.top - r.top) < 1 ? was : r))
      }
    }
    measure()
    return () => cancelAnimationFrame(frame)
  }, [width, showing])

  // where the guide is and what they're doing: showing you something, or by the card pointing at your next quest
  useEffect(() => {
    const g = guide.current
    if (!g || leaving || finished) return
    if (kept.small || !roomy) return g.leave()
    if (showing && ring) {
      g.cue({ x: standFor(ring, width), gesture: showing.gesture, aim: { x: ring.left + ring.width / 2, y: ring.top + ring.height / 2 }, jump: ring.top < window.innerHeight * 0.25 })
      return
    }
    const r = row.current?.getBoundingClientRect()
    const first = !kept.done.length
    g.cue({ x: homeOf(width), gesture: first ? "wave" : "point", aim: r ? { x: r.left + 20, y: r.top + r.height / 2 } : null, jump: first, cheer: first })
  }, [loaded, kept.small, kept.done.length, showing, ring, width, roomy, quest?.id, finished, leaving])

  // back by the card after showing you something a while
  useEffect(() => {
    if (!showing) return
    const t = setTimeout(() => (setShowing(null), setRing(null)), SHOW_FOR)
    return () => clearTimeout(t)
  }, [showing])

  // all six done: Friday torn off the calendar, a jump for joy, sunglasses, a dance; Done sends them off to the weekend
  useEffect(() => {
    const g = guide.current
    if (!finished || !g || leaving || kept.small || !roomy) return
    const page = calendar.current?.getBoundingClientRect()
    g.onArrive = () => {
      g.onArrive = null
      later.current.forEach(clearTimeout)
      const at = (ms: number, then: () => void) => later.current.push(window.setTimeout(then, reduced ? 0 : ms))
      at(500, () => setTorn(true))
      at(900, () => g.hop(true))
      at(1700, () => g.act("dance", { shades: true }))
    }
    setTorn(false)
    g.cue({ x: page ? page.left - BODY - 30 : homeOf(width), gesture: "point", aim: page ? { x: page.left + page.width / 2, y: page.top + page.height / 2 } : null })
  }, [finished, loaded, kept.small, width]) // eslint-disable-line react-hooks/exhaustive-deps

  const show = (q: Quest) => {
    setCurrent(q.id)
    if (q.page && !(q.page === "/" ? location.pathname === "/" : location.pathname.startsWith(q.page))) navigate(q.page)
    if (q.drawer) setDrawer(q.drawer === "open")
    setShowing(q)
  }
  const close = (end: boolean) => {
    save({ ...kept, over: true })
    const g = guide.current
    if (!g || !roomy || kept.small) return setTour(false)
    setLeaving(true)
    g.onGone = () => setTour(false)
    if (end) setGlowing(true)
    g.leave(end)
    later.current.push(window.setTimeout(() => setTour(false), 4000))
  }
  const tuck = (small: boolean) => save({ ...kept, small })

  const sign = finished && !kept.small && roomy
  return (
    <div className="gd-quests" data-leaving={leaving ? "" : undefined}>
      {ring && showing && <div className="gd-ring" style={{ left: ring.left - 6, top: ring.top - 6, width: ring.width + 12, height: ring.height + 12 }} />}
      {sign && (
        <>
          <div className="gd-cal" ref={calendar} aria-hidden="true" style={{ right: card + MARGIN + 200 }}>
            <span className="gd-cal-under">
              Sat
              <b />
            </span>
            <span className="gd-cal-page" data-torn={torn ? "" : undefined}>
              Fri
            </span>
          </div>
          <div className="gd-sign" data-lit={glowing ? "" : undefined} aria-hidden="true" style={{ right: card + MARGIN + 24 }}>
            <span>Weekend →</span>
            <i />
          </div>
        </>
      )}
      <canvas ref={canvas} className="gd-strip" aria-hidden="true" style={{ height: STRIP, display: roomy ? undefined : "none" }} />
      {where && loaded && roomy && !leaving && !kept.small && (
        // a click on the guide: a twirl (poke them three times and they get dizzy)
        <button className="gd-poke" tabIndex={-1} aria-label="Poke the guide" onClick={() => guide.current?.poke()} style={{ left: where.x - where.width / 2, width: where.width, height: where.height }} />
      )}
      {!leaving &&
        (kept.small ? (
          <button className="gd-pill" onClick={() => tuck(false)} aria-label={`Quests, ${kept.done.length} of ${QUESTS.length} done: open`}>
            <span>Quests</span>
            <b>
              {kept.done.length}/{QUESTS.length}
            </b>
          </button>
        ) : (
          <section className="gd-card" aria-label="Quests: getting to know Friday" style={{ width: card }}>
            <header className="gd-card-head">
              <span className="gd-where" aria-live="polite">
                {finished ? "All done" : (cheer ?? "Quests")}
              </span>
              <span className="gd-count">
                {kept.done.length}/{QUESTS.length}
              </span>
              <button className="gd-icon" onClick={() => tuck(true)} aria-label="Tuck the quests away" title="Tuck away">
                –
              </button>
              <button className="gd-icon" onClick={() => close(false)} aria-label="Close the quests" title="Close">
                ×
              </button>
            </header>
            {finished ? (
              <div className="gd-end">
                <h2 className="gd-title">That’s Friday!</h2>
                <ul className="gd-body">
                  <li data-said="">You know your way round</li>
                  <li data-said="">The ? brings these back any time</li>
                  <li data-said="">Next stop: the weekend</li>
                </ul>
                <div className="gd-foot">
                  <span style={{ flex: 1 }} />
                  <button className="gd-go" onClick={() => close(true)} autoFocus>
                    Done
                    <i />
                  </button>
                </div>
              </div>
            ) : (
              <ol className="gd-list">
                {QUESTS.map((q) => {
                  const done = kept.done.includes(q.id)
                  const on = q.id === quest?.id
                  return (
                    <li key={q.id} ref={on ? row : undefined} data-done={done ? "" : undefined} data-on={on ? "" : undefined} data-just={just === q.id ? "" : undefined}>
                      <button className="gd-quest" onClick={() => !done && setCurrent(q.id)} disabled={done} aria-expanded={on}>
                        <i aria-hidden="true" />
                        <span>{q.title}</span>
                      </button>
                      {on && !done && (
                        <div className="gd-hint">
                          <span>{q.hint}</span>
                          <button className="gd-show" onClick={() => show(q)}>
                            Show me
                          </button>
                        </div>
                      )}
                    </li>
                  )
                })}
              </ol>
            )}
          </section>
        ))}
    </div>
  )
}

/** The quests the first time setup finishes (once: Friday remembers it offered them), and their pill again when
 * Friday opens with them under way on this device. */
export function FirstTour({ ready, toured }: { ready: boolean; toured: boolean | undefined }) {
  const { setTour } = useShell()
  const client = useQueryClient()
  useEffect(() => {
    if (!ready || toured === undefined) return
    if (!toured) {
      const timer = setTimeout(() => {
        try {
          localStorage.removeItem(KEY) // a new user's quests start from the beginning
        } catch {
          // no storage: they start fresh anyway
        }
        setTour(true)
        // offered: remembered by Friday, and known here at once, so it isn't offered again (or its progress wiped)
        // before the next read of setup
        client.setQueryData<Schemas["SetupOut"]>(["setup"], (was) => (was ? { ...was, toured: true } : was))
        command("tour_offered", {}).catch(() => {})
      }, 900)
      return () => clearTimeout(timer)
    }
    if (questsUnderway()) setTour(true)
  }, [ready, toured, setTour, client])
  return null
}
