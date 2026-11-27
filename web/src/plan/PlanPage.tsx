// The Plan page (v22): the header (range, views, Shove, Pace, search, notifications, brief, to-do drawer) over the
// week, three days, day or month view (had no three days; you asked for them).

import { useAi } from "@/settings/AiConnect"
import { useShownPlan } from "@/plan/shown"
import { useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router"
import { useOffline } from "@/api/offline"
import { Dropdown, MenuRow } from "@/components/fr/Dropdown"
import { Icon, Seg, Switch } from "@/components/fr/controls"
import { useKeys } from "@/hooks/useKeys"
import { followServer, useDate } from "@/hooks/useClock"
import { useCalendar, usePaces, useSettings, useStatus } from "@/hooks/queries"
import { pigment } from "@/lib/pigments"
import { useLook } from "@/theme/LookProvider"
import { lateBy, weekday, when } from "@/lib/format"
import { addDays, dayRange, fromMin, pageStart, toMin } from "@/lib/time"
import { useQueryClient } from "@tanstack/react-query"
import { useToast } from "@/components/Toasts"
import { runCommand } from "@/hooks/useCommand"
import { inOrder, moveBlock, moveGroup } from "@/hooks/useDrop"
import { shiftMonth, switchView } from "@/shell/host"
import { useShell, type View } from "@/shell/ShellContext"
import { DayAside } from "./DayAside"
import { Grid } from "./Grid"
import { pending } from "./pending"
import { PickBar } from "./PickBar"
import { picks, usePicks } from "./picks"
import { MonthView, monthStart } from "./MonthView"
import { useWhatIf, whatIf } from "@/whatif/store"
import { WhatIfBar } from "@/whatif/WhatIfPanel"
import { BreaksButton } from "@/breaks/BreaksButton"
import { LightenDialog } from "@/dialogs/Dialogs"
import { overSentence } from "@/lib/load"

export type { View }

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
const VIEWS = [
  { value: 1 as View, label: "Day" },
  { value: 3 as View, label: "3 days" },
  { value: 7 as View, label: "Week" },
  { value: "month" as View, label: "Month" },
]

export function PlanPage() {
  const { drawer, event, drawerWidth, place, setPlace, layout, drawerOver, breakDay } = useShell()
  const today = useDate() // the calendar's pages center on its date, which turns at midnight (15 Nov)
  const view: View = place.view === 7 && !layout.weekFits ? 1 : place.view // a week too narrow to read shows its day
  const first = place.first
  // A week or three days are centered on the day picked, or today (lib/time.ts); `first` holds that center.
  const center = first ?? today
  const shown = view === "month" ? (first ?? monthStart(today)) : pageStart(center, view)
  // The keys and the View buttons alike keep the day you're looking at (shell/host.ts switchView)
  const setView = (v: View) => setPlace(switchView(place, v, today))
  const setFirst = (f: string | null) => setPlace({ view: place.view, first: f }) // keeps the week you chose, even while it shows a day
  const step = (by: number) => setFirst(view === "month" ? shiftMonth(shown, by) : addDays(center, by * view))
  const nudge = useNudge()
  // Only with a block selected, or several picked, do the arrows move them, not the page. Both hooks every render:
  // `selected || usePicks()` skipped the second when a block was selected, and React, finding a hook fewer than the
  // render before, threw and left the window black (27 Oct, "f.getSnapshot").
  const selectedBlock = !!useShell().selected?.key.startsWith("T")
  const picking = usePicks().length > 0
  const block = selectedBlock || picking
  useKeys({
    day: () => setView(1),
    three: () => setView(3),
    week: () => setView(7),
    month: () => setView("month"),
    previous: () => step(-1),
    next: () => step(1),
    earlier: block ? () => nudge(-15) : undefined,
    later: block ? () => nudge(15) : undefined,
    open: block ? () => nudge(0) : undefined,
  })
  const { on: whatIfOn, panel: whatIfPanel } = useWhatIf()
  useEffect(() => {
    whatIf.here(true) // What if stages changes made here, and only here
    return () => whatIf.here(false)
  }, [])
  return (
    <>
      <Header view={view} first={shown} onView={setView} onStep={step} onToday={() => setFirst(null)} />
      {view === "month" ? <MonthView first={shown} onDay={(d) => setPlace({ view: 1, first: d })} /> : <Days first={shown} view={view} drawer={(drawer || !!event || !!breakDay || (whatIfOn && whatIfPanel)) && !drawerOver ? drawerWidth : 0} aside={layout.dayAside} />}
    </>
  )
}

/** ↑ and ↓ move the selected block 15 minutes, pinned there, or all those picked; Enter opens its item. */
function useNudge(): (by: number) => void {
  const { selected, select } = useShell()
  const client = useQueryClient()
  const toast = useToast()
  const navigate = useNavigate()
  return (by: number) => {
    if (picks.get().length) return void (by && moveGroup(client, toast, picks.get(), by))
    if (!selected || !selected.key.startsWith("T")) return
    if (by === 0) return navigate(`/todo?item=${selected.item_id}`)
    const start = fromMin(toMin(selected.start) + by)
    const end = fromMin(toMin(selected.end) + by)
    const key = selected.key
    const kind = selected.pinned === "locked" ? "locked" : "preferred"
    const drawn = pending.collect(() => moveBlock(client, key, start, end, kind)) // at once, though sent after the moves before it
    inOrder(async () => {
      const out = await runCommand(client, toast, "pin", { id: selected.item_id, start, end, kind, from_start: selected.start, from_end: selected.end }, { label: () => `Moved ${by < 0 ? "earlier" : "later"}` })
      if (out) pending.settle(drawn, (out as { generation?: number | null }).generation ?? 0)
      else (pending.drop(drawn), select(null)) // it snapped back: the card would show a time it isn't at
    })
    select({ ...selected, key: `T${selected.item_id}@${start}`, start, end })
  }
}

function Days({ first, view, drawer, aside }: { first: string; view: 1 | 3 | 7; drawer: number; aside: boolean }) {
  const calendar = useCalendar(addDays(first, -1), view + 1).data
  const plan = useShownPlan(`${first}T00:00`, `${addDays(first, view + 1)}T12:00`).data
  useEffect(() => {
    if (calendar) followServer(calendar.now)
  }, [calendar])
  const w = useWhatIf()
  const trying = w.on
  if (!calendar || !plan) return <div className="fr-panel" />
  const margin = drawer ? drawer + 24 : view === 1 && aside ? 364 : 12
  return (
    <>
      <Grid dates={dayRange(first, view)} calendar={calendar} plan={plan} marginRight={margin} />
      <PickBar plan={plan} />
      {view === 1 && !drawer && aside && !trying && <DayAside date={first} calendar={calendar} plan={plan} />}
    </>
  )
}

function Header(props: { view: View; first: string; onView: (v: View) => void; onStep: (by: number) => void; onToday: () => void }) {
  const { view, first, onView, onStep, onToday } = props
  const { setDialog, drawer, setDrawer, layout } = useShell()
  const today = useDate()
  const days = view === "month" ? 1 : view
  const views = layout.weekFits ? VIEWS : VIEWS.filter((v) => v.value !== 7)
  // What if's bar takes the view buttons' room: with it on, they're the Plan menu's first line, as on a phone, and
  // narrower still the bar says less (20 Nov, the user's screenshot: the row ran out and "Replanning…" lay over them)
  const trying = useWhatIf().on
  const folded = layout.tight || (trying && layout.main < WHAT_IF_ROOM)
  // a phone's row has no room for it at all (20 Nov, 320px: it ran 77px off the screen): its own line under the row,
  // Discard and Keep in reach
  const below = layout.tight && trying
  return (
    <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
      <div className="fr-plan-head" style={{ display: "flex", alignItems: "center", gap: layout.tight ? 3 : 8, padding: "0 12px 0 var(--fr-head-inset)", minWidth: 0, height: 60 }}>
        {/* Before the date, not after it: a date's length moved them, so clicking ahead many times missed (5 Nov). */}
        <div data-testid="day-arrows" style={{ display: "flex", gap: 0, flex: "none" }}>
          <button className="btn btn-icon btn-ghost" onClick={() => onStep(-1)} aria-label="Previous" style={{ width: 26, height: 28, color: "var(--color-neutral-300)" }}>
            <Icon name="caret-left" />
          </button>
          <button className="btn btn-icon btn-ghost" onClick={() => onStep(1)} aria-label="Next" style={{ width: 26, height: 28, color: "var(--color-neutral-300)" }}>
            <Icon name="caret-right" />
          </button>
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, minWidth: layout.tight ? 40 : 48, flex: "0 1 auto", overflow: "hidden" }}>
          <span className="fr-h" style={{ fontSize: layout.tight ? 18 : 24, lineHeight: 1.1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {rangeTitle(first, view, layout.main < 900, layout.tight)}
          </span>
          {layout.main >= BREAKS_WORD_MIN && ( // narrower, "back to today" is in the Plan menu (19 Nov: 700px cut it)
            <button className="fr-plain fr-hover-text" style={{ color: "var(--color-neutral-500)", whiteSpace: "nowrap" }} onClick={onToday} title="Back to today">
              {subTitle(first, days, today, view)}
            </button>
          )}
        </div>
        <div style={{ flex: 1, minWidth: 0 }} />
        <Attention first={first} days={view === "month" ? 7 : view} />
        {!folded && (
          <span data-tour="views" style={{ flex: "none", display: "flex" }}>
            <Seg options={views} value={view} onPick={onView} label="View" />
          </span>
        )}
        {!below && <WhatIfBar tight={layout.tight || layout.main < WHAT_IF_FULL} />}
        <ShowMenu />
        <PlanMenu views={folded ? { options: views, value: view, onPick: onView, onToday } : undefined} breaks={layout.main < BREAKS_BUTTON_MIN} search={layout.main < SEARCH_BUTTON_MIN} today={!layout.tight && layout.main < BREAKS_WORD_MIN ? onToday : undefined} />
        {layout.main >= SEARCH_BUTTON_MIN && <IconButton tour="search" icon="magnifying-glass" label="Search (⌘K)" onClick={() => setDialog("search")} />}
        {layout.main >= BREAKS_BUTTON_MIN && <BreaksButton square={layout.main < BREAKS_WORD_MIN} />}
        <button
          className="btn btn-icon btn-secondary"
          data-tour="drawer"
          onClick={() => setDrawer(!drawer)}
          aria-label="To-do list"
          title="To-do list (T)"
          style={{ flex: "none", color: drawer ? "var(--color-accent-200)" : undefined, background: drawer ? "color-mix(in srgb, var(--color-accent) 14%, transparent)" : undefined }}
        >
          <Icon name="list-checks" size={16} />
        </button>
      </div>
      {below && (
        <div style={{ display: "flex", padding: "0 12px 8px", minWidth: 0 }}>
          <WhatIfBar tight />
        </div>
      )}
    </div>
  )
}

// The title row's room with What if on and a change being tried, measured 20 Nov (Grace's late work, Breaks): about
// 1,110px with the view buttons, 890px without; below the first they fold into the Plan menu, below this one the bar
// drops its words
const WHAT_IF_ROOM = 1200
const WHAT_IF_FULL = 1000

function IconButton({ icon, label, onClick, tour }: { icon: string; label: string; onClick: () => void; tour?: string }) {
  return (
    <button className="btn btn-icon btn-ghost" data-tour={tour} onClick={onClick} aria-label={label} title={label} style={{ flex: "none", color: "var(--color-neutral-300)" }}>
      <Icon name={icon} size={17} />
    </button>
  )
}

/** Everything that changes the plan, in one menu: What if, Ask your AI, other ways, shove, pace, the brief and what
 * changed. Seven at most (3 Nov, the CS 2112 UI lecture's rule of seven; plan/menus.test.ts holds it). */
// Below this width the title row has no room for the Breaks button: it's the Plan menu's first row instead, as the views
// are in a narrow window (19 Nov: "make sure that all of the buttons at the top collapse nicely")
const BREAKS_BUTTON_MIN = 400 // the row needs 384px with it and the lateness note (20 Nov: at 380 and 390 the To-do button ran past the edge)
// and below this one it's a square the size of the Inbox's tray it replaced, so the row fits as it did, whatever the
// lateness note beside it says (19 Nov: the word made a phone's To-do button run off the edge, and a 700px row cut
// "This month")
const BREAKS_WORD_MIN = 760
// and the smallest phones (320px) have no room for Search's button either, with the lateness note showing
const SEARCH_BUTTON_MIN = 360

function PlanMenu(props: { views?: { options: typeof VIEWS; value: View; onPick: (v: View) => void; onToday: () => void }; breaks?: boolean; search?: boolean; today?: () => void }) {
  const { views, breaks, search, today } = props
  const { pop, setPop, setDialog, askClaude, setBreakEdit } = useShell()
  const ai = useAi()
  const paces = usePaces().data
  return (
    <Dropdown tour="plan-menu" icon="sparkle" label="Plan">
      {(close) => (
        <>
          {(views || today || search || breaks) && ( // in a narrow window what the title row has no room for lives here, in
            // one line above the menu's seven rows: the view and today, and on a phone Search and Breaks (19 Nov)
            <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap", padding: "6px 8px 8px" }}>
              {views && <Seg options={views.options} value={views.value} onPick={(v) => (close(), views.onPick(v))} label="View" />}
              {(views || today) && (
                <button className="btn btn-ghost" onClick={() => (close(), (views?.onToday ?? today)?.())} style={{ fontSize: 12 }}>
                  Today
                </button>
              )}
              {search && (
                <button className="btn btn-ghost" onClick={() => (close(), setDialog("search"))} style={{ fontSize: 12 }}>
                  Search
                </button>
              )}
              {breaks && (
                <button className="btn btn-ghost" onClick={() => (close(), setBreakEdit({ pickDays: true }))} style={{ fontSize: 12 }}>
                  Breaks…
                </button>
              )}
            </div>
          )}
          <MenuRow icon="flask" label="What if" note="Try changes and see what they cost, kept only if you say" onClick={() => (close(), whatIf.start())} />
          <MenuRow icon="sparkle" label={`Ask ${ai.name}`} note="Say what you want changed" onClick={() => (close(), askClaude())} />
          <MenuRow icon="shuffle" label="Other ways" note="Two more ways to plan the same work" onClick={() => (close(), setDialog("ways"))} />
          <MenuRow icon="hand-palm" label="Shove" note="Take back a stretch of time" onClick={() => (close(), setPop(pop === "shove" ? null : "shove"))} />
          <MenuRow icon="gauge" label="Pace" note={paces ? `${paceLabel(paces)} · or take a break` : "Push harder, ease off, or take a break"} onClick={() => (close(), setPop(pop === "pace" ? null : "pace"))} />
          <MenuRow icon="sun-horizon" label="Morning brief" note="Today at a glance" onClick={() => (close(), setDialog("brief"))} />
          <MenuRow icon="clock-counter-clockwise" label="What changed" note="What the last replan moved, and why" onClick={() => (close(), setDialog("changes"))} />
        </>
      )}
    </Dropdown>
  )
}

/** personal's title-row toggles, in one menu: the calendars you gave a button and what the filter
 * matches (office hours) stay off the calendar until switched on here. They change what's drawn, not what's planned. */
function ShowMenu() {
  const settings = useSettings().data as Record<string, unknown> | undefined
  const { look, light, setLook } = useLook()
  const toolbar = ((settings?.calendar_look as { toolbar?: string[] } | undefined)?.toolbar ?? []).slice(0, 9)
  const colors = (settings?.calendar_look as { colors?: Record<string, string> } | undefined)?.colors ?? {}
  const filter = (settings?.categories as { filter?: { label: string } | null } | undefined)?.filter
  const calendarLook = settings?.calendar_look as Record<string, unknown> | undefined
  const showPastPlan = (calendarLook?.show_past_plan as boolean | undefined) ?? true
  const client = useQueryClient()
  const toast = useToast()
  const flipPastPlan = () => {
    const value = { ...calendarLook, show_past_plan: !showPastPlan }
    runCommand(client, toast, "settings_set", { key: "calendar_look", value }, {
      label: () => (showPastPlan ? "Past days show when you worked" : "Friday's past plan shown"),
      // at once: the calendar redraws before the server answers
      optimistic: (c) => c.setQueryData(["settings"], (was: Record<string, unknown> | undefined) => (was ? { ...was, calendar_look: value } : was)),
    })
  }
  const flip = (name: string) => setLook({ showing: look.showing.includes(name) ? look.showing.filter((h) => h !== name) : [...look.showing, name] })
  useEffect(() => {
    // ⌥⌘1–9 show or hide the calendars with buttons, in order, as in personal.
    const press = (e: KeyboardEvent) => {
      if (!(e.altKey && (e.metaKey || e.ctrlKey))) return
      const name = toolbar[Number(e.code.replace("Digit", "")) - 1]
      if (!name) return
      e.preventDefault()
      flip(name)
    }
    window.addEventListener("keydown", press)
    return () => window.removeEventListener("keydown", press)
  })
  const on = toolbar.filter((t) => look.showing.includes(t)).length + (filter && look.showFiltered ? 1 : 0) + (showPastPlan ? 1 : 0)
  return (
    <Dropdown tour="show" icon={on ? "eye" : "eye-slash"} label="Show">
      {() => (
        <>
          <span className="fr-kicker" style={{ padding: "6px 10px 4px" }}>
            What the calendar draws. It never changes the plan.
          </span>
          <label className="fr-hover" style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 10px", borderRadius: "var(--radius-md)" }}>
            <Switch on={showPastPlan} onToggle={flipPastPlan} label="Show Friday's past plan" />
            <span style={{ flex: 1 }}>Friday's past plan</span>
            <span className="fr-kicker">off: when you worked</span>
          </label>
          {filter && (
            <label className="fr-hover" style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 10px", borderRadius: "var(--radius-md)" }}>
              <Switch on={look.showFiltered} onToggle={() => setLook({ showFiltered: !look.showFiltered })} label={`Show ${filter.label}`} />
              <span title={filter.label} style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{filter.label}</span>
            </label>
          )}
          {toolbar.map((name, i) => (
            <label key={name} className="fr-hover" style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 10px", borderRadius: "var(--radius-md)" }}>
              <Switch on={look.showing.includes(name)} onToggle={() => flip(name)} label={`Show ${name}`} />
              <span className="fr-swatch" style={{ borderRadius: "50%", background: pigment(colors[name], light) ?? "var(--color-neutral-500)" }} />
              {/* a long name ends in "…" on its line, whole on hover (27 Nov, a user's notes: "anonymous.dragon.888@gmail.com"
                  ran out of the menu over its shortcut) */}
              <span title={name} style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{name}</span>
              <span className="fr-kicker" style={{ flex: "none" }}>⌥⌘{i + 1}</span>
            </label>
          ))}
        </>
      )}
    </Dropdown>
  )
}

interface Note {
  tone: "now" | "mark" | "plain"
  icon: string
  text: string
  action?: { label: string; run: () => void }
  list?: { key: number; title: string; sub: string; onOpen: () => void }[] // what it's about, one line each
}

/** What needs you, in one pill (late work, a day over its limit, a lock that can't hold, the server's problems,
 * being offline), opening to the whole list with what to do about each. The plan's notes and the events not counted
 * as busy were here too: long, rarely anything to do, and taking the top bar (27 Oct); the calendar shows a skipped
 * event as skipped, and Settings → Calendars says what isn't counted. */
function Attention({ first, days }: { first: string; days: number }) {
  const { setDialog, layout, today } = useShell()
  const navigate = useNavigate()
  const offline = useOffline()
  const status = useStatus().data
  const calendar = useCalendar(first, days).data
  const plan = useShownPlan(`${first}T00:00`, `${addDays(first, days)}T00:00`).data
  const solving = !!status && status.plan_generation !== null && status.plan_generation < status.generation
  const notes: Note[] = []
  if (offline) notes.push({ tone: "plain", icon: "wifi-slash", text: "Offline: showing the last plan. Changes wait until you're back." })
  for (const p of status?.problems ?? []) notes.push({ tone: "now", icon: "warning-circle", text: p })
  const late = status?.late_items ?? []
  if (late.length) {
    const text = late.length === 1 ? `${late[0].title} will be late` : `${late.length} things will be late`
    const list = late.map((i) => ({ key: i.item_id, title: i.title, sub: `${i.due ? `due ${when(i.due, today)} · ` : ""}about ${lateBy(i.hours)} late`, onOpen: () => navigate(`/todo?item=${i.item_id}`) }))
    notes.push({ tone: "now", icon: "warning", text, action: { label: "See options", run: () => setDialog("triage") }, list })
  }
  // Soft deadlines slipping, and work due soon with no time for it: less urgent than late work, still said.
  const slipping = status?.slipping ?? []
  if (slipping.length) {
    const unplanned = slipping.filter((i) => i.planned === false).length
    const text =
      slipping.length === 1
        ? `${slipping[0].title} ${slipping[0].planned === false ? "isn't planned before it's due" : "is planned after it's due"}`
        : `${slipping.length} to-dos past their due${unplanned ? `, ${unplanned} not planned` : ""}`
    const list = slipping.map((i) => ({
      key: i.item_id,
      title: i.title,
      sub: `${i.due ? `due ${when(i.due, today)} · ` : ""}${i.planned === false ? "not planned" : `planned about ${lateBy(i.hours)} late`}`,
      onOpen: () => navigate(`/todo?item=${i.item_id}`),
    }))
    notes.push({ tone: "mark", icon: "clock-countdown", text, action: { label: "See options", run: () => setDialog("triage") }, list })
  }
  // A day past its most isn't late work: said plainly, as the Load ahead says a week, with ways to lighten it (15 Nov:
  // its "See options" opened what gives when work is late, which said everything fits).
  const over = calendar?.days.map((d) => ({ date: d.date, planned: plan?.day_hours[d.date] ?? 0, usual: d.cap_hours })).find((d) => d.planned - d.usual > 0.05)
  const [lighten, setLighten] = useState(false)
  if (over) notes.push({ tone: "mark", icon: "warning", text: overSentence(FULL_DAY[weekday(over.date)], over.planned, over.usual, late.length), action: { label: "Lighten that day", run: () => setLighten(true) } })
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLSpanElement>(null)
  useEffect(() => {
    if (!open) return
    // pointerdown: a block's press prevents the mousedown that would follow (the audit, 31 Oct)
    const away = (e: PointerEvent) => !box.current?.contains(e.target as Node) && setOpen(false)
    document.addEventListener("pointerdown", away)
    return () => document.removeEventListener("pointerdown", away)
  }, [open])
  // on a narrow window the list is moved left until it fits, rather than running off the right edge
  const pillAt = open ? box.current?.getBoundingClientRect() : undefined
  const shift = pillAt ? Math.min(0, window.innerWidth - 12 - (pillAt.left + Math.min(380, window.innerWidth - 24))) : 0
  const urgent = notes.filter((n) => n.tone !== "plain")
  const lead = urgent[0] ?? notes[0]
  if (!lead) return solving ? <Replanning tight={layout.tight} /> : null
  const color = lead.tone === "now" ? "var(--fr-due)" : lead.tone === "mark" ? "var(--fr-warn)" : "var(--color-neutral-300)"
  const bg = lead.tone === "now" ? "color-mix(in srgb, var(--fr-now) 14%, transparent)" : lead.tone === "mark" ? "color-mix(in srgb, var(--fr-mark) 16%, transparent)" : "color-mix(in srgb, var(--color-text) 6%, transparent)"
  return (
    // In a phone's width it's an icon and a count: it keeps them whole, and the title gives way (16 Nov: squeezed to 6px,
    // the pill sat under Show). Wider, its words give way to "Replanning…" beside it: .fr-pill doesn't shrink, and the
    // word was drawn over Day and 3 days (20 Nov, the user's screenshot, What if on)
    <span ref={box} style={{ position: "relative", minWidth: 0, flex: layout.tight ? "none" : "0 1 auto", display: "flex", alignItems: "center", gap: 6 }}>
      <button className="fr-pill" data-tour="attention" onClick={() => setOpen(!open)} aria-expanded={open} title={notes.map((n) => n.text).join("\n")} style={{ position: "relative", background: bg, color, cursor: "pointer", flex: "0 100 auto", minWidth: 0, maxWidth: "100%", ...(layout.tight ? { padding: "4px 6px" } : {}) }}>
        <Icon name={lead.icon} size={13} />
        {!layout.tight && <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{lead.text}</span>}
        {notes.length > 1 && <span className="tnum" style={{ color: "var(--color-neutral-400)", flex: "none" }}>{layout.tight ? notes.length : `+${notes.length - 1}`}</span>}
        {/* a phone's row has no room for one more thing: the dot sits on the note's corner */}
        {solving && layout.tight && <span aria-hidden style={{ ...DOT, position: "absolute", top: -2, right: -2 }} />}
      </button>
      {solving && (layout.tight ? <span role="status" className="sr-only">Replanning…</span> : <Replanning tight={false} />)}
      {over && lighten && <LightenDialog start={over.date} days={1} label={FULL_DAY[weekday(over.date)]} planned={over.planned} usual={over.usual} late={late.length} onClose={() => setLighten(false)} />}
      {open && (
        <div className="fr-float" style={{ position: "absolute", top: "calc(100% + 6px)", left: shift, zIndex: 20, width: "min(380px, calc(100vw - 24px))", maxHeight: "60vh", overflowY: "auto", padding: 8, display: "flex", flexDirection: "column", gap: 2 }}>
          {notes.map((n, i) => (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "18px minmax(0,1fr) auto", gap: 10, alignItems: "start", padding: "8px 8px" }}>
              <Icon name={n.icon} size={15} style={{ color: n.tone === "now" ? "var(--fr-due)" : n.tone === "mark" ? "var(--fr-warn)" : "var(--color-neutral-400)", marginTop: 2 }} />
              <span style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 0 }}>
                <span style={{ textWrap: "pretty" }}>{n.text}</span>
                {n.list?.map((l) => (
                  // Each thing that will be late: what, when it's due, roughly how late; a click opens it.
                  <button key={l.key} className="fr-plain fr-hover-text" onClick={() => (setOpen(false), l.onOpen())} style={{ display: "flex", flexDirection: "column", gap: 1, textAlign: "left", paddingLeft: 8, boxShadow: "inset 2px 0 0 var(--fr-due)" }}>
                    <span style={{ fontWeight: 500, fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{l.title}</span>
                    <span className="tnum" style={{ fontSize: 11, color: "var(--color-neutral-400)" }}>
                      {l.sub}
                    </span>
                  </button>
                ))}
              </span>
              {n.action && (
                <button className="btn btn-secondary" onClick={() => (setOpen(false), n.action?.run())} style={{ fontSize: 12, whiteSpace: "nowrap" }}>
                  {n.action.label}
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </span>
  )
}

/** Friday working out a new plan: the dot, and the word when there's room (3 Nov: "add the full replanning to the
 * blue dot if there is space for it"); a narrow window keeps just the dot. */
function Replanning({ tight }: { tight: boolean }) {
  // in a full row (What if on, a lateness note) the word gives way, down to the dot, after the note's words have: it
  // was drawn over Day and 3 days (20 Nov, the user's screenshot)
  return (
    <span role="status" title="Replanning…" style={{ flex: "0 1 auto", minWidth: 7, overflow: "hidden", display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--color-accent-200)", whiteSpace: "nowrap" }}>
      <span aria-hidden style={DOT} />
      {tight ? <span className="sr-only">Replanning…</span> : <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>Replanning…</span>}
    </span>
  )
}

const DOT = { width: 7, height: 7, flex: "none", borderRadius: "50%", background: "var(--color-accent)", animation: "fr-pulse 1.2s ease-in-out infinite" } as const

const FULL_DAY: Record<string, string> = { Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday", Thu: "Thursday", Fri: "Friday", Sat: "Saturday", Sun: "Sunday" }

function paceLabel(p: { now_label: string; period_end: string | null }): string {
  return p.period_end ? `${p.now_label} · to ${weekday(p.period_end.slice(0, 10))}` : p.now_label
}

export function rangeTitle(first: string, view: View, short = false, phone = false): string {
  const month = (d: string) => (short ? MONTHS[Number(d.slice(5, 7)) - 1].slice(0, 3) : MONTHS[Number(d.slice(5, 7)) - 1])
  if (phone && view !== "month") {
    // On a phone the title has room for a few letters, and each day's header says its date: the month alone
    // (10 Nov: "Thu 12 Nov" showed as "Thu …")
    const last = addDays(first, (view as number) - 1)
    return month(first) === month(last) ? month(first) : `${month(first)}–${month(last)}`
  }
  const day = (d: string) => Number(d.slice(8, 10))
  if (view === "month") return `${month(first)} ${first.slice(0, 4)}`
  if (view === 1) return `${short ? weekday(first) : FULL_DAY[weekday(first)]} ${day(first)} ${month(first)}`
  const last = addDays(first, view - 1)
  return month(first) === month(last) ? `${day(first)} – ${day(last)} ${month(last)}` : `${day(first)} ${month(first).slice(0, 3)} – ${day(last)} ${month(last)}`
}

function subTitle(first: string, days: number, today: string, view: View): string {
  if (view === "month") return today.slice(0, 7) === first.slice(0, 7) ? "This month" : "Today"
  if (first <= today && today < addDays(first, days)) return view === 1 ? "Today" : view === 3 ? "Around today" : "This week"
  return "Today"
}

