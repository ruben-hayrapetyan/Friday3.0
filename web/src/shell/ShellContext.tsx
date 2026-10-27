// What the shell's overlays share: the open pop-up, the selected block, the to-do drawer and the dialogs. Pages
// open them; the shell draws them.

import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from "react"
import type { Block, Schemas } from "@/api/client"
import { drawerOver, type Layout, layoutFor, useWindowWidth } from "./layout"

export type Pop = "shove" | "pace" | "bell" | null
export type Dialog = "brief" | "search" | "triage" | "conflicts" | "ways" | "ask" | "setup" | null
export type View = 1 | 3 | 7 | "month"

/** An event open in the drawer (COMBINED.md 12): a new one being drafted (no id) or one being edited. */
export interface EventDraft {
  id: number | null
  title: string
  start: string // local "YYYY-MM-DDTHH:MM"; an all-day event runs from midnight to midnight
  end: string
  allDay: boolean
  color: string | null
  notes: string
  location: string // where it is; "" for nowhere in particular
  every: string | null // a new event's repeat, as `rrule:…`
  seriesId: number | null
  calendar: string | null // the calendar it came from
  saveTo?: string // a new event's calendar (its id, Google's or the Mac's), "" for only Friday; Settings' "New events go to" when unset
  savesToCalendar: boolean // changes here are saved back to it
  auto?: { color: string | null; from: string } // the colour it wears with no pigment of its own, and why
}

/** What the calendar shows: the view, and its first day (null follows today). The sidebar's mini month moves it. */
export interface CalendarPlace {
  view: View
  first: string | null
}

interface Shell {
  today: string
  pop: Pop
  setPop: (pop: Pop) => void
  selected: Block | null
  select: (block: Block | null) => void
  drawer: boolean
  setDrawer: (open: boolean) => void
  dialog: Dialog
  setDialog: (dialog: Dialog) => void
  place: CalendarPlace
  setPlace: (place: CalendarPlace) => void
  agendaDay: string | null // the day the sidebar's agenda shows; null is today
  setAgendaDay: (date: string | null) => void
  event: EventDraft | null
  setEvent: (event: EventDraft | null) => void
  drawerWidth: number
  setDrawerWidth: (width: number) => void
  way: Schemas["OtherWay"] | null // another way being previewed on the calendar
  setWay: (way: Schemas["OtherWay"] | null) => void
  ask: { text: string; purpose: "anything" | "rule"; now?: boolean } | null // what Ask Claude opens with
  askClaude: (text?: string, purpose?: "anything" | "rule", now?: boolean) => void // now: ask at once, no second ↩
  layout: Layout // for the window's width (shell/layout.ts)
  drawerOver: boolean // the drawer slides over the calendar rather than beside it
  navOpen: boolean // the sidebar, slid over the page in a narrow window
  setNavOpen: (open: boolean) => void
  tour: boolean // the tour of Friday is showing
  setTour: (on: boolean) => void
}

const Ctx = createContext<Shell | null>(null)

// The drawer's width, dragged by its left edge and kept for next time (personal's drawer: 320–760 px).
const WIDTH_KEY = "friday-drawer-width"
const MIN_WIDTH = 320
const MAX_WIDTH = 760

function loadWidth(): number {
  try {
    const saved = Number(localStorage.getItem(WIDTH_KEY))
    return saved >= MIN_WIDTH && saved <= MAX_WIDTH ? saved : 340
  } catch {
    return 340
  }
}

export function ShellProvider({ today, children }: { today: string; children: ReactNode }) {
  const [pop, setPop] = useState<Pop>(null)
  const [selected, select] = useState<Block | null>(null)
  const [drawer, setDrawer] = useState(false)
  const [dialog, setDialog] = useState<Dialog>(null)
  const [place, setPlace] = useState<CalendarPlace>({ view: 7, first: null })
  const [agendaDay, setAgendaDay] = useState<string | null>(null)
  const [event, setEvent] = useState<EventDraft | null>(null)
  const [way, setWay] = useState<Schemas["OtherWay"] | null>(null)
  const [ask, setAsk] = useState<{ text: string; purpose: "anything" | "rule"; now?: boolean } | null>(null)
  const askClaude = useCallback((text = "", purpose: "anything" | "rule" = "anything", now = false) => {
    setAsk({ text, purpose, now })
    setDialog("ask")
  }, [])
  const [drawerWidth, setWidth] = useState(loadWidth)
  const setDrawerWidth = useCallback((width: number) => {
    const kept = Math.round(Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, width)))
    setWidth(kept)
    try {
      localStorage.setItem(WIDTH_KEY, String(kept))
    } catch {
      // private mode: the width lasts this visit
    }
  }, [])
  const width = useWindowWidth()
  const layout = useMemo(() => layoutFor(width), [width])
  const [navOpen, setNavOpen] = useState(false)
  const [tour, setTour] = useState(false)
  const over = drawerOver(layout, drawerWidth)
  const value = useMemo(
    () => ({ today, pop, setPop, selected, select, drawer, setDrawer, dialog, setDialog, place, setPlace, agendaDay, setAgendaDay, event, setEvent, drawerWidth, setDrawerWidth, way, setWay, ask, askClaude, layout, drawerOver: over, navOpen, setNavOpen, tour, setTour }),
    [today, pop, selected, drawer, dialog, place, agendaDay, event, drawerWidth, setDrawerWidth, way, ask, askClaude, layout, over, navOpen, tour],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useShell(): Shell {
  const value = useContext(Ctx)
  if (!value) throw new Error("useShell outside ShellProvider")
  return value
}
