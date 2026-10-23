// The Plan page (v22): the header (range, views, Shove, Pace, search, notifications, brief, to-do drawer) over the
// week, day or month view (COMBINED.md 13: no 3-day view).

import { useEffect, useState } from "react"
import { useNavigate } from "react-router"
import { useOffline } from "@/api/offline"
import { Icon, Seg } from "@/components/fr/controls"
import { useKeys } from "@/hooks/useKeys"
import { followServer } from "@/hooks/useClock"
import { useCalendar, usePaces, usePlan, useSettings, useStatus } from "@/hooks/queries"
import { useCommand } from "@/hooks/useCommand"
import { pigment } from "@/lib/pigments"
import { useLook } from "@/theme/LookProvider"
import { LEFT_OUT } from "./Pieces"
import { weekday } from "@/lib/format"
import { addDays, dayRange, fromMin, toMin } from "@/lib/time"
import { useQueryClient } from "@tanstack/react-query"
import { useToast } from "@/components/Toasts"
import { runCommand } from "@/hooks/useCommand"
import { moveBlock } from "@/hooks/useDrop"
import { useShell, type View } from "@/shell/ShellContext"
import { DayAside } from "./DayAside"
import { Grid } from "./Grid"
import { MonthView, monthStart } from "./MonthView"

export type { View }

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
const VIEWS = [
  { value: 1 as View, label: "Day" },
  { value: 7 as View, label: "Week" },
  { value: "month" as View, label: "Month" },
]

export function PlanPage() {
  const { today, drawer, event, drawerWidth, place, setPlace } = useShell()
  const { view, first } = place
  const shown = first ?? (view === "month" ? monthStart(today) : today)
  const setView = (v: View) => setPlace({ view: v, first: v === "month" ? monthStart(shown) : first })
  const setFirst = (f: string | null) => setPlace({ view, first: f })
  const step = (by: number) => setFirst(view === "month" ? shiftMonth(shown, by) : addDays(shown, by * view))
  const nudge = useNudge()
  const block = !!useShell().selected?.key.startsWith("T") // only then do the arrows move it, not the page
  useKeys({
    day: () => setView(1),
    week: () => setView(7),
    month: () => setView("month"),
    previous: () => step(-1),
    next: () => step(1),
    earlier: block ? () => nudge(-15) : undefined,
    later: block ? () => nudge(15) : undefined,
    open: block ? () => nudge(0) : undefined,
  })
  const pick = (v: View) => setPlace({ view: v, first: null })
  return (
    <>
      <Header view={view} first={shown} onView={pick} onStep={step} onToday={() => setFirst(null)} />
      {view === "month" ? <MonthView first={shown} onDay={(d) => setPlace({ view: 1, first: d })} /> : <Days first={shown} view={view} drawer={drawer || !!event ? drawerWidth : 0} />}
    </>
  )
}

/** ↑ and ↓ move the selected block 15 minutes, pinned there; Enter opens its item (COMBINED.md 66). */
function useNudge(): (by: number) => void {
  const { selected, select } = useShell()
  const client = useQueryClient()
  const toast = useToast()
  const navigate = useNavigate()
  return (by: number) => {
    if (!selected || !selected.key.startsWith("T")) return
    if (by === 0) return navigate(`/todo?item=${selected.item_id}`)
    const start = fromMin(toMin(selected.start) + by)
    const end = fromMin(toMin(selected.end) + by)
    const key = selected.key
    runCommand(
      client,
      toast,
      "pin",
      { id: selected.item_id, start, end, kind: selected.pinned === "locked" ? "locked" : "preferred", from_start: selected.start, from_end: selected.end },
      { optimistic: (c) => moveBlock(c, key, start, end, selected.pinned === "locked" ? "locked" : "preferred"), label: () => `Moved ${by < 0 ? "earlier" : "later"}` },
    )
    select({ ...selected, key: `T${selected.item_id}@${start}`, start, end })
  }
}

function Days({ first, view, drawer }: { first: string; view: 1 | 7; drawer: number }) {
  const calendar = useCalendar(addDays(first, -1), view + 1).data
  const plan = usePlan(`${first}T00:00`, `${addDays(first, view + 1)}T12:00`).data
  useEffect(() => {
    if (calendar) followServer(calendar.now)
  }, [calendar])
  if (!calendar || !plan) return <div className="fr-panel" />
  const margin = drawer ? drawer + 24 : view === 1 ? 364 : 12
  return (
    <>
      <Grid dates={dayRange(first, view)} calendar={calendar} plan={plan} marginRight={margin} />
      {view === 1 && !drawer && <DayAside date={first} calendar={calendar} plan={plan} />}
    </>
  )
}

function Header(props: { view: View; first: string; onView: (v: View) => void; onStep: (by: number) => void; onToday: () => void }) {
  const { view, first, onView, onStep, onToday } = props
  const { today, pop, setPop, setDialog, drawer, setDrawer, askClaude } = useShell()
  const paces = usePaces().data
  const days = view === "month" ? 1 : view
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "0 20px 0 12px", minWidth: 0 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, flex: "none", whiteSpace: "nowrap" }}>
        <span className="fr-h" style={{ fontSize: 26, lineHeight: 1 }}>
          {rangeTitle(first, view)}
        </span>
        <button className="fr-plain fr-hover-text" style={{ color: "var(--color-neutral-500)" }} onClick={onToday} title="Back to today (T)">
          {subTitle(first, days, today, view)}
        </button>
      </div>
      <div style={{ display: "flex", gap: 2, marginLeft: 6, flex: "none" }}>
        <button className="btn btn-icon btn-ghost" onClick={() => onStep(-1)} aria-label="Previous" style={{ width: 28, height: 28, color: "var(--color-neutral-300)" }}>
          <Icon name="caret-left" />
        </button>
        <button className="btn btn-icon btn-ghost" onClick={() => onStep(1)} aria-label="Next" style={{ width: 28, height: 28, color: "var(--color-neutral-300)" }}>
          <Icon name="caret-right" />
        </button>
      </div>
      <Pills first={first} days={view === "month" ? 7 : view} />
      <div style={{ flex: 1, minWidth: 0 }} />
      <CalendarButtons />
      <Seg options={VIEWS} value={view} onPick={onView} label="View" />
      <IconButton icon="magnifying-glass" label="Search (⌘K)" onClick={() => setDialog("search")} />
      <IconButton icon="bell" label="Notifications" onClick={() => setPop(pop === "bell" ? null : "bell")} />
      <IconButton icon="sun-horizon" label="Morning brief" onClick={() => setDialog("brief")} />
      <IconButton icon="sparkle" label="Ask Claude" onClick={() => askClaude()} />
      <button className="btn btn-secondary" onClick={() => setDialog("ways")} title="Two more ways to plan the same work" style={{ flex: "none", whiteSpace: "nowrap" }}>
        <Icon name="shuffle" size={15} />
        Other ways
      </button>
      <button className="btn btn-secondary" onClick={() => setPop(pop === "shove" ? null : "shove")} style={{ flex: "none", whiteSpace: "nowrap" }}>
        <Icon name="hand-palm" size={15} />
        Shove
      </button>
      <button className="btn btn-primary" onClick={() => setPop(pop === "pace" ? null : "pace")} style={{ flex: "none", whiteSpace: "nowrap" }}>
        <Icon name="gauge" size={15} />
        {paces ? paceLabel(paces) : "Pace"}
      </button>
      <button
        className="btn btn-icon btn-secondary"
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

function IconButton({ icon, label, onClick }: { icon: string; label: string; onClick: () => void }) {
  return (
    <button className="btn btn-icon btn-ghost" onClick={onClick} aria-label={label} title={label} style={{ flex: "none", color: "var(--color-neutral-300)" }}>
      <Icon name={icon} size={17} />
    </button>
  )
}

/** personal's title-row buttons (COMBINED.md 19): each calendar you gave a button shows or hides it, and the filter
 * shows or hides what it matches (office hours). They change what's drawn, not what's planned. */
function CalendarButtons() {
  const settings = useSettings().data as Record<string, unknown> | undefined
  const { look, light, setLook } = useLook()
  const toolbar = ((settings?.calendar_look as { toolbar?: string[] } | undefined)?.toolbar ?? []).slice(0, 9)
  const colors = (settings?.calendar_look as { colors?: Record<string, string> } | undefined)?.colors ?? {}
  const filter = (settings?.categories as { filter?: { label: string } | null } | undefined)?.filter
  useEffect(() => {
    // ⌥⌘1–9 show or hide the calendars with buttons, in order, as in personal.
    const press = (e: KeyboardEvent) => {
      if (!(e.altKey && (e.metaKey || e.ctrlKey))) return
      const n = Number(e.code.replace("Digit", ""))
      const name = toolbar[n - 1]
      if (!name) return
      e.preventDefault()
      setLook({ hidden: look.hidden.includes(name) ? look.hidden.filter((h) => h !== name) : [...look.hidden, name] })
    }
    window.addEventListener("keydown", press)
    return () => window.removeEventListener("keydown", press)
  }, [toolbar, look.hidden, setLook])
  if (!toolbar.length && !filter) return null
  return (
    <div style={{ display: "flex", gap: 4, flex: "none" }}>
      {filter && (
        <button
          className="fr-chip"
          aria-pressed={!look.hideFiltered}
          onClick={() => setLook({ hideFiltered: !look.hideFiltered })}
          title={`${look.hideFiltered ? "Show" : "Hide"} ${filter.label}`}
        >
          <i className={`ph ph-${look.hideFiltered ? "eye-slash" : "eye"}`} />
          {filter.label}
        </button>
      )}
      {toolbar.map((name, i) => {
        const hidden = look.hidden.includes(name)
        return (
          <button
            key={name}
            className="fr-chip"
            aria-pressed={!hidden}
            onClick={() => setLook({ hidden: hidden ? look.hidden.filter((h) => h !== name) : [...look.hidden, name] })}
            title={`${hidden ? "Show" : "Hide"} ${name} (⌥⌘${i + 1})`}
            style={{ opacity: hidden ? 0.55 : 1 }}
          >
            <span className="fr-swatch" style={{ borderRadius: "50%", background: pigment(colors[name], light) ?? "var(--color-neutral-500)" }} />
            {name}
          </button>
        )
      })}
    </div>
  )
}

/** Events Friday isn't planning around this week, by why, each a chip that counts them after all (COMBINED.md 28:
 * personal's "Planning around"). */
function NotCounted({ first, days }: { first: string; days: number }) {
  const plan = usePlan(`${first}T00:00`, `${addDays(first, days)}T00:00`).data
  const settings = useSettings().data as Record<string, unknown> | undefined
  const save = useCommand("settings_set", { label: () => "Planning around it now" })
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const out = (plan?.fixed ?? []).filter((f) => f.left_out)
  if (!out.length || !settings) return null
  const busy = settings.busy as { calendars: Record<string, boolean> } & Record<string, unknown>
  const by = new Map<string, number>()
  for (const f of out) by.set(f.left_out as string, (by.get(f.left_out as string) ?? 0) + 1)
  const count = (reason: string) => {
    const calendars = Object.fromEntries(out.filter((f) => f.left_out === "calendar" && f.calendar).map((f) => [f.calendar as string, true]))
    const flag = { reminder: "count_reminders", free: "count_free", filtered: "count_filtered" }[reason]
    save({ key: "busy", value: flag ? { ...busy, [flag]: true } : { ...busy, calendars: { ...busy.calendars, ...calendars } } })
  }
  return (
    <span style={{ position: "relative" }}>
      <button className="fr-pill" onClick={() => setOpen(!open)} title="Events on your calendar that Friday plans through" style={{ background: "color-mix(in srgb, var(--color-text) 6%, transparent)", color: "var(--color-neutral-300)", cursor: "pointer" }}>
        <Icon name="calendar-x" size={13} />
        {out.length} not counted as busy
      </button>
      {open && (
        <div className="fr-float" style={{ position: "absolute", top: "calc(100% + 6px)", left: 0, zIndex: 20, width: 300, padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
          <span className="fr-kicker">Friday plans through these. Click one to plan around it after all.</span>
          {[...by.entries()].map(([reason, n]) => (
            <button key={reason} className="fr-chip" onClick={() => (count(reason), setOpen(false))} style={{ justifyContent: "space-between" }}>
              <span>{LEFT_OUT[reason] ?? reason}</span>
              <span className="tnum">{n}</span>
            </button>
          ))}
          <button className="fr-link" onClick={() => navigate("/settings/calendars")} style={{ alignSelf: "flex-start", fontSize: 12 }}>
            Calendars settings
          </button>
        </div>
      )}
    </span>
  )
}

/** Offline, a day that's over its limit, and a plan being worked out. */
function Pills({ first, days }: { first: string; days: number }) {
  const { setDialog } = useShell()
  const offline = useOffline()
  const status = useStatus().data
  const calendar = useCalendar(first, days).data
  const plan = usePlan(`${first}T00:00`, `${addDays(first, days)}T00:00`).data
  const solving = !!status && status.plan_generation !== null && status.plan_generation < status.generation
  const late = Object.entries(status?.late ?? {})
  const over = calendar?.days
    .map((d) => ({ date: d.date, by: (plan?.day_hours[d.date] ?? 0) - d.cap_hours }))
    .find((d) => d.by > 0.05)
  return (
    <>
      {offline && (
        <div className="fr-pill" title="Showing the last plan Friday sent. Changes wait until you're back online." style={{ background: "color-mix(in srgb, var(--color-text) 8%, transparent)", color: "var(--color-neutral-200)" }}>
          <Icon name="wifi-slash" size={13} />
          Offline
        </div>
      )}
      {over && (
        <button className="fr-pill" onClick={() => setDialog("triage")} style={{ background: "color-mix(in srgb, var(--fr-mark) 16%, transparent)", color: "var(--fr-warn)", cursor: "pointer" }}>
          <Icon name="warning" size={13} />
          {FULL_DAY[weekday(over.date)]} is {over.by.toFixed(1)} h over
          <span style={{ color: "var(--color-text)" }}>See options</span>
        </button>
      )}
      {late.length > 0 && (
        <button className="fr-pill" onClick={() => setDialog("triage")} title={late.map(([t, h]) => `${t}: ${h.toFixed(1)} h late`).join("\n")} style={{ background: "color-mix(in srgb, var(--fr-now) 14%, transparent)", color: "var(--fr-due)", cursor: "pointer" }}>
          <Icon name="warning" size={13} />
          {late.length === 1 ? `${late[0][0]} will be late` : `${late.length} things will be late`}
          <span style={{ color: "var(--color-text)" }}>See options</span>
        </button>
      )}
      {(status?.notices ?? []).slice(0, 1).map((n) => (
        <div key={n} className="fr-pill" title={(status?.notices ?? []).join("\n")} style={{ background: "color-mix(in srgb, var(--fr-mark) 16%, transparent)", color: "var(--fr-warn)", maxWidth: 360, overflow: "hidden" }}>
          <Icon name="info" size={13} />
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{n}</span>
          {(status?.notices ?? []).length > 1 && <span style={{ color: "var(--color-neutral-400)" }}>+{(status?.notices ?? []).length - 1}</span>}
        </div>
      ))}
      {(status?.problems ?? []).slice(0, 1).map((p) => (
        <div key={p} className="fr-pill" title={(status?.problems ?? []).join("\n")} style={{ background: "color-mix(in srgb, var(--fr-now) 14%, transparent)", color: "var(--fr-due)", maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis" }}>
          <Icon name="warning-circle" size={13} />
          <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{p}</span>
        </div>
      ))}
      {!!status?.conflicts?.length && (
        <button className="fr-pill" onClick={() => setDialog("conflicts")} style={{ background: "color-mix(in srgb, var(--fr-mark) 16%, transparent)", color: "var(--fr-warn)", cursor: "pointer" }}>
          <Icon name="lock-simple" size={13} />
          A lock can't hold
          <span style={{ color: "var(--color-text)" }}>Decide</span>
        </button>
      )}
      <NotCounted first={first} days={days} />
      {solving && (
        <div className="fr-pill" style={{ background: "color-mix(in srgb, var(--color-accent) 14%, transparent)", color: "var(--color-accent-200)" }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--color-accent)", boxShadow: "0 0 calc(10px * var(--g-accent)) calc(2px * var(--g-accent)) var(--color-accent)" }} />
          Replanning…
        </div>
      )}
    </>
  )
}

const FULL_DAY: Record<string, string> = { Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday", Thu: "Thursday", Fri: "Friday", Sat: "Saturday", Sun: "Sunday" }

function paceLabel(p: { now_label: string; period_end: string | null }): string {
  return p.period_end ? `${p.now_label} · to ${weekday(p.period_end.slice(0, 10))}` : p.now_label
}

function rangeTitle(first: string, view: View): string {
  const month = (d: string) => MONTHS[Number(d.slice(5, 7)) - 1]
  const day = (d: string) => Number(d.slice(8, 10))
  if (view === "month") return `${month(first)} ${first.slice(0, 4)}`
  if (view === 1) return `${FULL_DAY[weekday(first)]} ${day(first)} ${month(first)}`
  const last = addDays(first, view - 1)
  return month(first) === month(last) ? `${day(first)} – ${day(last)} ${month(last)}` : `${day(first)} ${month(first).slice(0, 3)} – ${day(last)} ${month(last)}`
}

function subTitle(first: string, days: number, today: string, view: View): string {
  if (view === "month") return today.slice(0, 7) === first.slice(0, 7) ? "This month" : "Today"
  if (first <= today && today < addDays(first, days)) return view === 1 ? "Today" : "This week"
  return "Today"
}

function shiftMonth(first: string, by: number): string {
  const y = Number(first.slice(0, 4))
  const m = Number(first.slice(5, 7)) - 1 + by
  const date = new Date(Date.UTC(y, m, 1))
  return date.toISOString().slice(0, 10)
}
