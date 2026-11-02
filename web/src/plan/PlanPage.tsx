// The Plan page (v22): the header (range, views, Shove, Pace, search, notifications, brief, to-do drawer) over the
// week, three days, day or month view (COMBINED.md 13 had no three days; you asked for them).

import { useAi } from "@/settings/AiConnect"
import { useShownPlan } from "@/plan/shown"
import { useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router"
import { useOffline } from "@/api/offline"
import { Dropdown, MenuRow } from "@/components/fr/Dropdown"
import { Icon, Seg, Switch } from "@/components/fr/controls"
import { useKeys } from "@/hooks/useKeys"
import { followServer } from "@/hooks/useClock"
import { useCalendar, usePaces, useSettings, useStatus } from "@/hooks/queries"
import { pigment } from "@/lib/pigments"
import { useLook } from "@/theme/LookProvider"
import { lateBy, weekday, when } from "@/lib/format"
import { addDays, dayRange, fromMin, pageStart, toMin } from "@/lib/time"
import { useQueryClient } from "@tanstack/react-query"
import { useToast } from "@/components/Toasts"
import { runCommand } from "@/hooks/useCommand"
import { inOrder, moveBlock, moveGroup } from "@/hooks/useDrop"
import { shiftMonth } from "@/shell/host"
import { useShell, type View } from "@/shell/ShellContext"
import { DayAside } from "./DayAside"
import { Grid } from "./Grid"
import { pending } from "./pending"
import { PickBar } from "./PickBar"
import { picks, usePicks } from "./picks"
import { MonthView, monthStart } from "./MonthView"
import { useWhatIf, whatIf } from "@/whatif/store"
import { WhatIfBar } from "@/whatif/WhatIfPanel"
import { DecisionsButton } from "@/inbox/Decisions"

export type { View }

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
const VIEWS = [
  { value: 1 as View, label: "Day" },
  { value: 3 as View, label: "3 days" },
  { value: 7 as View, label: "Week" },
  { value: "month" as View, label: "Month" },
]

export function PlanPage() {
  const { today, drawer, event, drawerWidth, place, setPlace, layout, drawerOver } = useShell()
  const view: View = place.view === 7 && !layout.weekFits ? 1 : place.view // a week too narrow to read shows its day
  const first = place.first
  // A week is Monday to Sunday and three days a fixed three, whichever day is today or was picked (lib/time.ts).
  const shown = view === "month" ? (first ?? monthStart(today)) : pageStart(first ?? today, view)
  const setView = (v: View) => setPlace({ view: v, first: v === "month" ? monthStart(shown) : first })
  const setFirst = (f: string | null) => setPlace({ view: place.view, first: f }) // keeps the week you chose, even while it shows a day
  const step = (by: number) => setFirst(view === "month" ? shiftMonth(shown, by) : addDays(shown, by * view))
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
  const pick = (v: View) => setPlace({ view: v, first: null })
  const { on: whatIfOn, panel: whatIfPanel } = useWhatIf()
  useEffect(() => {
    whatIf.here(true) // What if stages changes made here, and only here
    return () => whatIf.here(false)
  }, [])
  return (
    <>
      <Header view={view} first={shown} onView={pick} onStep={step} onToday={() => setFirst(null)} />
      {view === "month" ? <MonthView first={shown} onDay={(d) => setPlace({ view: 1, first: d })} /> : <Days first={shown} view={view} drawer={(drawer || !!event || (whatIfOn && whatIfPanel)) && !drawerOver ? drawerWidth : 0} aside={layout.dayAside} />}
    </>
  )
}

/** ↑ and ↓ move the selected block 15 minutes, pinned there, or all those picked; Enter opens its item (COMBINED.md
 * 66). */
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
  const { today, setDialog, drawer, setDrawer, layout } = useShell()
  const days = view === "month" ? 1 : view
  const views = layout.weekFits ? VIEWS : VIEWS.filter((v) => v.value !== 7)
  return (
    <div style={{ display: "flex", alignItems: "center", gap: layout.tight ? 4 : 8, padding: "0 12px 0 var(--fr-head-inset)", minWidth: 0 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, minWidth: 48, flex: "0 1 auto", overflow: "hidden" }}>
        <span className="fr-h" style={{ fontSize: layout.tight ? 18 : 24, lineHeight: 1.1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {rangeTitle(first, view, layout.main < 900)}
        </span>
        {!layout.tight && (
          <button className="fr-plain fr-hover-text" style={{ color: "var(--color-neutral-500)", whiteSpace: "nowrap" }} onClick={onToday} title="Back to today">
            {subTitle(first, days, today, view)}
          </button>
        )}
      </div>
      <div style={{ display: "flex", gap: 0, flex: "none" }}>
        <button className="btn btn-icon btn-ghost" onClick={() => onStep(-1)} aria-label="Previous" style={{ width: 26, height: 28, color: "var(--color-neutral-300)" }}>
          <Icon name="caret-left" />
        </button>
        <button className="btn btn-icon btn-ghost" onClick={() => onStep(1)} aria-label="Next" style={{ width: 26, height: 28, color: "var(--color-neutral-300)" }}>
          <Icon name="caret-right" />
        </button>
      </div>
      <Attention first={first} days={view === "month" ? 7 : view} />
      <div style={{ flex: 1, minWidth: 0 }} />
      {!layout.tight && (
        <span data-tour="views" style={{ flex: "none", display: "flex" }}>
          <Seg options={views} value={view} onPick={onView} label="View" />
        </span>
      )}
      <WhatIfBar tight={layout.tight} />
      <ShowMenu />
      <PlanMenu views={layout.tight ? { options: views, value: view, onPick: onView, onToday } : undefined} />
      <IconButton tour="search" icon="magnifying-glass" label="Search (⌘K)" onClick={() => setDialog("search")} />
      <DecisionsButton />
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
  )
}

function IconButton({ icon, label, onClick, tour }: { icon: string; label: string; onClick: () => void; tour?: string }) {
  return (
    <button className="btn btn-icon btn-ghost" data-tour={tour} onClick={onClick} aria-label={label} title={label} style={{ flex: "none", color: "var(--color-neutral-300)" }}>
      <Icon name={icon} size={17} />
    </button>
  )
}

/** Everything that changes the plan, in one menu: Ask Claude, other ways, shove, pace, the brief. */
function PlanMenu({ views }: { views?: { options: typeof VIEWS; value: View; onPick: (v: View) => void; onToday: () => void } }) {
  const { pop, setPop, setDialog, askClaude } = useShell()
  const ai = useAi()
  const paces = usePaces().data
  return (
    <Dropdown tour="plan-menu" icon="sparkle" label="Plan">
      {(close) => (
        <>
          {views && ( // in a narrow window the view and today live here, so the title row keeps the date
            <div style={{ display: "flex", gap: 6, alignItems: "center", padding: "6px 8px 8px" }}>
              <Seg options={views.options} value={views.value} onPick={(v) => (close(), views.onPick(v))} label="View" />
              <button className="btn btn-ghost" onClick={() => (close(), views.onToday())} style={{ fontSize: 12 }}>
                Today
              </button>
            </div>
          )}
          <MenuRow icon="sparkle" label={`Ask ${ai.name}`} note="Say what you want changed" onClick={() => (close(), askClaude())} />
          <MenuRow icon="shuffle" label="Other ways" note="Two more ways to plan the same work" onClick={() => (close(), setDialog("ways"))} />
          <MenuRow icon="hand-palm" label="Shove" note="Take back a stretch of time" onClick={() => (close(), setPop(pop === "shove" ? null : "shove"))} />
          <MenuRow icon="gauge" label="Pace" note={paces ? paceLabel(paces) : "Push harder or ease off"} onClick={() => (close(), setPop(pop === "pace" ? null : "pace"))} />
          <MenuRow icon="sun-horizon" label="Morning brief" note="Today at a glance" onClick={() => (close(), setDialog("brief"))} />
        </>
      )}
    </Dropdown>
  )
}

/** personal's title-row toggles (COMBINED.md 19), in one menu: the calendars you gave a button and what the filter
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
              {filter.label}
            </label>
          )}
          {toolbar.map((name, i) => (
            <label key={name} className="fr-hover" style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 10px", borderRadius: "var(--radius-md)" }}>
              <Switch on={look.showing.includes(name)} onToggle={() => flip(name)} label={`Show ${name}`} />
              <span className="fr-swatch" style={{ borderRadius: "50%", background: pigment(colors[name], light) ?? "var(--color-neutral-500)" }} />
              <span style={{ flex: 1 }}>{name}</span>
              <span className="fr-kicker">⌥⌘{i + 1}</span>
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
  const over = calendar?.days.map((d) => ({ date: d.date, by: (plan?.day_hours[d.date] ?? 0) - d.cap_hours })).find((d) => d.by > 0.05)
  if (over) notes.push({ tone: "mark", icon: "warning", text: `${FULL_DAY[weekday(over.date)]} is ${over.by.toFixed(1)} h over`, action: { label: "See options", run: () => setDialog("triage") } })
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
  if (!lead) return solving ? <Replanning /> : null
  const color = lead.tone === "now" ? "var(--fr-due)" : lead.tone === "mark" ? "var(--fr-warn)" : "var(--color-neutral-300)"
  const bg = lead.tone === "now" ? "color-mix(in srgb, var(--fr-now) 14%, transparent)" : lead.tone === "mark" ? "color-mix(in srgb, var(--fr-mark) 16%, transparent)" : "color-mix(in srgb, var(--color-text) 6%, transparent)"
  return (
    <span ref={box} style={{ position: "relative", minWidth: 0, flex: "0 1 auto", display: "flex", alignItems: "center", gap: 6 }}>
      <button className="fr-pill" data-tour="attention" onClick={() => setOpen(!open)} aria-expanded={open} title={notes.map((n) => n.text).join("\n")} style={{ background: bg, color, cursor: "pointer", minWidth: 0, maxWidth: "100%" }}>
        <Icon name={lead.icon} size={13} />
        {!layout.tight && <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{lead.text}</span>}
        {notes.length > 1 && <span className="tnum" style={{ color: "var(--color-neutral-400)", flex: "none" }}>{layout.tight ? notes.length : `+${notes.length - 1}`}</span>}
      </button>
      {solving && <Replanning />}
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

function Replanning() {
  return <span title="Replanning…" style={{ width: 7, height: 7, flex: "none", borderRadius: "50%", background: "var(--color-accent)", animation: "fr-pulse 1.2s ease-in-out infinite" }} />
}

const FULL_DAY: Record<string, string> = { Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday", Thu: "Thursday", Fri: "Friday", Sat: "Saturday", Sun: "Sunday" }

function paceLabel(p: { now_label: string; period_end: string | null }): string {
  return p.period_end ? `${p.now_label} · to ${weekday(p.period_end.slice(0, 10))}` : p.now_label
}

function rangeTitle(first: string, view: View, short = false): string {
  const month = (d: string) => (short ? MONTHS[Number(d.slice(5, 7)) - 1].slice(0, 3) : MONTHS[Number(d.slice(5, 7)) - 1])
  const day = (d: string) => Number(d.slice(8, 10))
  if (view === "month") return `${month(first)} ${first.slice(0, 4)}`
  if (view === 1) return `${short ? weekday(first) : FULL_DAY[weekday(first)]} ${day(first)} ${month(first)}`
  const last = addDays(first, view - 1)
  return month(first) === month(last) ? `${day(first)} – ${day(last)} ${month(last)}` : `${day(first)} ${month(first).slice(0, 3)} – ${day(last)} ${month(last)}`
}

function subTitle(first: string, days: number, today: string, view: View): string {
  if (view === "month") return today.slice(0, 7) === first.slice(0, 7) ? "This month" : "Today"
  if (first <= today && today < addDays(first, days)) return view === 1 ? "Today" : view === 3 ? "Next 3 days" : "This week"
  return "Today"
}

