// The week and day grid (v22 Plan): day headers with the date, pace, dues and overload; hour lines; blocks, fixed
// items, ghosts and the wind-down; what you timed, when you did it, over the right of the column; drag to move,
// resize or select time. Settings → Appearance chooses the hours shown and whether a day's dues are header chips or
// a lane down its column (COMBINED.md 14, 15).

import { useQueryClient } from "@tanstack/react-query"
import { useEffect, useLayoutEffect, useRef, useState } from "react"
import type { Block, Item, Schemas } from "@/api/client"
import { type Drag, justDragged, minuteAt, selectionFrom, useDragging } from "@/components/calendar/useDrag"
import { useToast } from "@/components/Toasts"
import { useClock, useElapsed } from "@/hooks/useClock"
import { runCommand } from "@/hooks/useCommand"
import { moveBlock, retimeEvent } from "@/hooks/useDrop"
import { useGhosts, useItems, useNow, useStatus } from "@/hooks/queries"
import { movedSince } from "@/lib/drag"
import { clock, hms, weekday, when } from "@/lib/format"
import { type Axis, addDays, fitAxis, fromMin, hourMarks, layout, type Placed, type Span, toMin } from "@/lib/time"
import { useShell } from "@/shell/ShellContext"
import { useLook } from "@/theme/LookProvider"
import { draftAt, draftOf } from "@/shell/EventPane"
import { DueLane } from "./DueLane"
import { useGlide } from "./glide"
import { type TrialPlan, useWhatIf, whatIf } from "@/whatif/store"
import { asBlock, BlockBox, DraftBox, DropPreview, FixedBox, GhostBox, NowLine, PX, SleepBand, type TriedLook } from "./Pieces"
import { inARow, type Pick, pickOfBlock, pickOfEvent, picks, shifted, usePicks } from "./picks"

interface Props {
  dates: string[]
  calendar: Schemas["CalendarOut"]
  plan: Schemas["PlanOut"]
  marginRight: number // room for the day view's aside or the to-do drawer
}

export function Grid({ dates, calendar, plan, marginRight }: Props) {
  const { drag, begin } = useDragging()
  const { today, selected, select, drawer, event, setEvent } = useShell()
  const ghosts = useGhosts().data ?? []
  const nowData = useNow().data
  const current = nowData?.current?.key
  const timer = useStatus().data?.timer
  const elapsed = useElapsed(timer?.elapsed_s)
  const open = new Set((useItems().data ?? []).map((i) => i.id))
  const moved = useMoved(plan)
  // What if: what the tried changes made, changed or deleted, and blocks' moves against your real plan.
  const tried = (plan as TrialPlan).tried
  const trying = useWhatIf().on
  const lookOf = (id: number): TriedLook | undefined =>
    !tried ? undefined : tried.gone.has(id) ? "gone" : tried.made.has(id) ? "made" : tried.changed.has(id) ? "changed" : undefined
  const bringBack = (id: number) => {
    const at = whatIf.get().changes.findIndex((c) => (c.command === "drop" || c.command === "skip") && (c.input as { id?: number }).id === id)
    if (at >= 0) whatIf.remove(at)
  }
  const retime = useRetime()
  const stays = (f: Item) => !!f.gives_way_to || lookOf(f.id) === "gone"
  const letGo = (f: Item) => selected?.key === `F${f.id}` && select(null) // its popover would act on where it was
  // Several picked with ⌘ or Shift (plan/picks.ts): drawn as selected, and dragged together.
  const picked = usePicks()
  const pickedKeys = new Set(picked.map((p) => p.key))
  const multi = (e?: React.MouseEvent) => !!e && (e.metaKey || e.ctrlKey || e.shiftKey)
  const now = useClock()
  const { look } = useLook()
  const allDay24 = look.hours === "All day"
  // The lanes step aside while the to-do drawer is out, as personal's did: the full list is showing.
  const lanes = look.deadlines === "Lanes" && !drawer
  const timed = plan.fixed.filter((f): f is Item & { start: string; end: string } => !!f.start && !!f.end)
  // A birthday or holiday spans whole days: it goes with the day's dues at the top, not as a column-high block.
  const allDay = timed.filter((f) => f.start.endsWith("T00:00") && f.end.endsWith("T00:00") && f.end > f.start)
  const fixed = timed.filter((f) => !allDay.includes(f)) // what you toggled off is already gone (plan/shown.ts)
  // An optional event the plan gives to work is one you're skipping: it sits behind, full width, out of the way of
  // the events beside it, rather than take a column from them (27 Oct).
  const isSkipped = (f: Item) => !!f.gives_way_to || f.left_out === "skipped" // or one you're not going to
  const going = fixed.filter((f) => !isSkipped(f))
  const skipped = fixed.filter(isSkipped)
  // An event whose time is for a task, by the task: its blocks in that time are drawn inside it (planner/holds.py).
  const holders = new Map(fixed.filter((f) => f.holds).map((f) => [(f.holds as { id: number }).id, f]))
  const holderOf = (b: Block) => {
    const event = holders.get(b.item_id)
    return event && b.start < event.end && b.end > event.start ? event.title : undefined
  }
  // What was selected, picked too on the first ⌘-click, as the to-do list does.
  const selectedPick = (): Pick | null => {
    const found = selected?.key.startsWith("F") ? fixed.find((f) => f.id === selected.item_id) : undefined
    return found ? pickOfEvent(found) : selected?.key.startsWith("T") ? pickOfBlock(selected) : null
  }
  // From the wake time to core sleep, stretched for anything earlier or later on these days.
  // The past as it went: a block a timer sitting covers gives way to the sitting, and a deleted item's goes; blocks
  // and sittings are laid out together, side by side where they overlap, rather than one drawn over the other.
  const sessions = plan.sessions ?? []
  const shown = plan.blocks.filter((b) => b.state !== "timed" && b.state !== "gone")
  const axis: Axis = allDay24 ? { startMin: 0, endMin: 1440 } : fitAxis({ startMin: calendar.axis_start_min, endMin: calendar.axis_end_min }, [...fixed, ...plan.blocks, ...sessions], dates)
  const panel = useRef<HTMLDivElement>(null)
  const head = useRef<HTMLDivElement>(null)
  const headHeight = useHeight(head)
  useGlide(panel, plan, dates.join())
  // All 24 hours open at the wake time, as a paper calendar opens at the morning.
  useLayoutEffect(() => {
    if (allDay24 && panel.current) panel.current.scrollTop = Math.max(0, calendar.axis_start_min - 30) * PX
  }, [allDay24, calendar.axis_start_min])
  const height = (axis.endMin - axis.startMin) * PX
  const days = new Map(calendar.days.map((d) => [d.date, d]))
  const planned = new Set(plan.blocks.map((b) => b.key))
  const news = ghosts.filter((g) => !planned.has(g.key))
  // The same time of day in every column: strong on today, faint on the others.
  const nowAt = now - toMin(calendar.today) - axis.startMin
  const cols = `52px repeat(${dates.length}, minmax(0,1fr))`
  return (
    <div
      ref={panel}
      className="fr-panel"
      data-tour="calendar"
      // What if: the week framed in the accent while it shows changes not made, as Docs frames a suggestion.
      style={{ overflowY: "auto", position: "relative", marginRight, ...(trying ? { boxShadow: "inset 0 0 0 2px color-mix(in srgb, var(--color-accent) 55%, transparent)" } : {}) }}
    >
      <div ref={head} style={{ position: "sticky", top: 0, zIndex: 4, display: "grid", gridTemplateColumns: cols, background: "var(--color-surface)" }}>
        <div />
        {dates.map((date) => (
          <DayHead key={date} date={date} day={days.get(date)} hours={plan.day_hours[date] ?? 0} isToday={date === calendar.today} dues={lanes ? [] : calendar.dues} allDay={allDay} />
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: cols, padding: "10px 0 150px" }}>
        <div style={{ position: "relative", height }}>
          {hourMarks(axis).map((m) => (
            <div key={m.top} className="tnum" style={{ position: "absolute", right: 10, top: m.top * PX, transform: "translateY(-50%)", fontSize: 11, color: "var(--color-neutral-600)" }}>
              {m.label}
            </div>
          ))}
        </div>
        {dates.map((date) => {
          const dues = lanes ? calendar.dues.filter((d) => d.due.startsWith(date)) : []
          const lane = dues.length ? (dates.length === 1 ? "280px" : "44%") : "0px"
          // An event you're going to, under the work; one you're skipping (or that work takes), over it, at the side,
          // where it can still be clicked to go after all (30 Oct)
          const fixedBox = (p: Placed<Item & { start: string; end: string }>, aside = false) => (
            <FixedBox
              aside={aside}
              key={`f${p.item.id}`}
              p={p}
              tried={lookOf(p.item.id)}
              picked={pickedKeys.has(`F${p.item.id}`)}
              onOpen={(e) =>
                justDragged()
                  ? undefined
                  : multi(e) && !tried && p.item.event_kind !== "shove"
                  ? (picks.toggle(pickOfEvent(p.item), selectedPick()), select(null))
                  : (picks.clear(),
                    lookOf(p.item.id) === "gone"
                      ? bringBack(p.item.id)
                      : tried && whatIf.madeBy(p.item.id) !== null
                        ? (select(null), setEvent(draftOf(p.item)))
                        : select(asBlock(p.item)))
              }
              onEdit={p.item.event_kind === "shove" ? undefined : () => (select(null), setEvent(draftOf(p.item)))}
              retime={{ begin: () => select(null), save: (span) => retime.event(p.item, span) }}
              // It moves, and its edges stretch it, as a block's do (29 Oct); a picked one takes the others picked
              // with it. One skipped for work, or deleted in What if, stays put.
              onGrab={
                stays(p.item)
                  ? undefined
                  : (e) => (letGo(p.item), begin(e, { ...grabbedEvent(p.item, "move", minuteAt(e)), group: pickedKeys.has(`F${p.item.id}`) && picked.length > 1 }))
              }
              onResize={stays(p.item) ? undefined : (e, edge) => (letGo(p.item), begin(e, grabbedEvent(p.item, edge === "top" ? "resize-top" : "resize", minuteAt(e))))}
            />
          )
          return (
            <div
              key={date}
              data-top-min={toMin(date) + axis.startMin}
              onPointerDown={(e) => {
                if (e.target !== e.currentTarget) return
                begin(e, { ...selectionFrom(minuteAt(e)), itemId: null, blockKey: null, title: "" })
              }}
              onDoubleClick={(e) => {
                // Empty time, double-clicked: a new event there, drafted in the drawer (personal's way).
                if (e.target !== e.currentTarget) return
                const at = Math.floor(minuteAtMouse(e) / 15) * 15
                setEvent(draftAt(fromMin(at)))
              }}
              style={{
                position: "relative",
                height,
                touchAction: "none",
                backgroundImage: `repeating-linear-gradient(to bottom, color-mix(in srgb, var(--color-text) 5%, transparent) 0 1px, transparent 1px ${60 * PX}px)`,
                backgroundPositionY: `${((60 - (axis.startMin % 60)) % 60) * PX}px`,
                boxShadow: "inset 1px 0 0 color-mix(in srgb, var(--color-text) 5%, transparent)",
                ["--lane" as string]: lane,
              }}
            >
              {dues.length > 0 && <DueLane dues={dues} stickyTop={headHeight} narrow={dates.length > 1} />}
              <Nights date={date} days={days} axis={axis} />
              {layout(going, date, axis).map((p) => fixedBox(p))}
              {event && !event.allDay && layout([event], date, axis).map((p) => <DraftBox key="draft" p={p} title={event.title} />)}
              {layout([...shown, ...sessions], date, axis).map((p) => (
                <BlockBox
                  key={p.item.key}
                  p={p}
                  isCur={p.item.key === current}
                  selected={p.item.key === selected?.key || pickedKeys.has(p.item.key)}
                  done={p.item.state === "done" || (toMin(p.item.end) <= now && !open.has(p.item.item_id))}
                  look={p.item.key.startsWith("S") ? "sitting" : p.item.state === "missed" ? "missed" : undefined}
                  movedFrom={tried ? tried.moved.get(p.item.item_id) : moved.get(p.item.item_id)}
                  inside={holderOf(p.item)}
                  tried={lookOf(p.item.item_id)}
                  today={today}
                  onOpen={(e) => {
                    if (justDragged()) return
                    const pickable = p.item.key.startsWith("T") && p.item.state !== "missed" && p.item.state !== "done"
                    if (multi(e) && pickable) return (picks.toggle(pickOfBlock(p.item), selectedPick()), select(null))
                    picks.clear()
                    select(p.item)
                  }}
                  // A selected block let go of, as retyping its time does: its popover would act on where it was. A
                  // picked one takes the others picked with it.
                  onGrab={(e) => (p.item.key === selected?.key && select(null), begin(e, { ...grabbed(p.item, "move", minuteAt(e)), group: pickedKeys.has(p.item.key) && picked.length > 1 }))}
                  onResize={(e, edge) => (p.item.key === selected?.key && select(null), begin(e, grabbed(p.item, edge === "top" ? "resize-top" : "resize", minuteAt(e))))}
                  retime={{ begin: () => select(null), save: (span) => retime.block(p.item, span) }}
                />
              ))}
              {layout(skipped, date, axis).map((p) => fixedBox(p, true))}
              {layout(news, date, axis).map((p) => (
                <GhostBox key={`g${p.item.key}`} p={p} />
              ))}
              {drag?.moved && drag.at && drag.over === "calendar" && (drag.group || drag.rows ? <GroupPreview drag={drag} list={picked} date={date} axis={axis} /> : <Preview drag={drag} date={date} axis={axis} today={today} />)}
              {timer && date === calendar.today && nowData?.current_source === "timer" && (
                <TimerBox title={nowData.current?.title ?? ""} top={(now - elapsed / 60 - toMin(date) - axis.startMin) * PX} seconds={elapsed} />
              )}
              {nowAt >= 0 && nowAt <= axis.endMin - axis.startMin && <NowLine top={nowAt * PX} today={date === calendar.today} />}
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** An element's height, kept up to date (the sticky header's, which the lanes stick below). */
function useHeight(ref: React.RefObject<HTMLElement | null>): number {
  const [height, setHeight] = useState(0)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new ResizeObserver(() => setHeight(el.getBoundingClientRect().height))
    observer.observe(el)
    return () => observer.disconnect()
  }, [ref])
  return height
}

/** What you're timing, from when you started to now: drawn from the timer itself, so it shows even when the plan
 * has no quarter hour for it (a few minutes before class). */
function TimerBox({ title, top, seconds }: { title: string; top: number; seconds: number }) {
  const minutes = seconds / 60
  return (
    <div
      style={{
        position: "absolute",
        left: 3,
        right: 3,
        top,
        height: Math.max(15, minutes) * PX,
        zIndex: 1,
        pointerEvents: "none",
        borderRadius: 6,
        padding: "3px 8px",
        fontSize: 12,
        fontWeight: 500,
        overflow: "hidden",
        whiteSpace: "nowrap",
        color: "var(--color-accent-200)",
        background: "color-mix(in srgb, var(--color-accent) 16%, var(--color-surface))",
        boxShadow: "inset 0 0 0 1px color-mix(in srgb, var(--color-accent) 55%, transparent)",
      }}
    >
      ● {title} · {hms(seconds)}
    </div>
  )
}

function DayHead(props: {
  date: string
  day?: Schemas["CalendarDay"]
  hours: number
  isToday: boolean
  dues: Schemas["DueMarker"][]
  allDay: (Item & { start: string; end: string })[]
}) {
  const { date, day, hours, isToday, dues, allDay } = props
  const { select } = useShell()
  const { drag } = useDragging()
  const target = !!drag?.moved && drag.over === "day" && drag.day === date
  const [open, setOpen] = useState(false)
  const over = day ? hours - day.cap_hours : 0
  // A deadline a line, each cut to the column's width; two lines at most, the rest on a tap ("+2 more"): side by
  // side, the second was cut off mid-word and its "+1" hidden past the column's edge.
  const mine = dues.filter((d) => d.due.startsWith(date))
  const shown = open || mine.length <= 2 ? mine : mine.slice(0, 1)
  const line = { flex: "none", maxWidth: "100%", minWidth: 0, alignSelf: "flex-start" } as const
  const chip = { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0 } as const
  const big = { fontSize: 28, lineHeight: 0.95 }
  return (
    // The header is the day's all-day row: a task dropped here is due that day.
    <div data-drop-day={date} style={{ padding: "12px 10px 10px", display: "flex", flexDirection: "column", gap: 6, position: "relative", minWidth: 0, background: target ? "color-mix(in srgb, var(--color-accent) 12%, transparent)" : undefined }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, whiteSpace: "nowrap" }}>
        <span
          className="fr-h tnum"
          style={isToday ? { ...big, color: "var(--color-accent-200)", textShadow: "0 0 calc(18px * var(--g-today)) var(--color-accent)" } : big}
        >
          {Number(date.slice(8, 10))}
        </span>
        <span style={{ color: isToday ? "var(--color-accent-300)" : "var(--color-neutral-400)" }}>{weekday(date)}</span>
        {day?.pace && <span style={{ fontSize: 11, color: "var(--color-accent-300)" }}>{day.pace}</span>}
        {day && hours > 0 && (
          // Planned against the day's limit (COMBINED.md 67).
          <span className="tnum" title={`${hours.toFixed(1)} h planned of ${day.cap_hours} h`} style={{ marginLeft: "auto", fontSize: 10.5, color: over > 0.05 ? "var(--fr-warn)" : "var(--color-neutral-500)" }}>
            {hours.toFixed(hours < 10 ? 1 : 0)}/{day.cap_hours}h
          </span>
        )}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 3, minHeight: 18, minWidth: 0 }}>
        {over > 0.05 && (
          <span className="fr-tag warn" style={line}>
            <i className="ph ph-warning" style={{ fontSize: 11 }} />
            {over.toFixed(1)} h over
          </span>
        )}
        {allDay
          .filter((f) => f.start.slice(0, 10) <= date && date < f.end.slice(0, 10))
          .map((f) => (
            <button key={`a${f.id}`} className="fr-tag fr-plain" title={f.title} onClick={() => select(asBlock(f))} style={line}>
              <i className="ph ph-calendar-blank" style={{ fontSize: 11 }} />
              <span style={chip}>{f.title}</span>
            </button>
          ))}
        {shown.map((d) => (
          <button key={d.item_id} className="fr-tag due fr-plain" title={`${d.title}, ${clock(d.due)}`} onClick={() => select(dueBlock(d))} style={line}>
            <i className="ph ph-flag" style={{ fontSize: 11, flex: "none" }} />
            <span style={chip}>{d.title}</span>
            {!d.due.endsWith("T23:59") && <span className="tnum" style={{ flex: "none" }}>{clock(d.due)}</span>}
          </button>
        ))}
        {mine.length > 2 && (
          <button className="fr-tag fr-plain" onClick={() => setOpen(!open)} style={{ ...line, color: "var(--color-neutral-400)" }}>
            {open ? "Show less" : `+${mine.length - 1} more due`}
          </button>
        )}
      </div>
      {isToday && (
        <div
          style={{
            position: "absolute",
            left: 10,
            right: 10,
            bottom: 0,
            height: 2,
            borderRadius: 1,
            background: "var(--color-accent)",
            boxShadow: "0 0 calc(12px * var(--g-today)) calc(1px * var(--g-today)) var(--color-accent)",
          }}
        />
      )}
    </div>
  )
}

/** A due marker, as the selected "block" the popover reads. */
function dueBlock(d: Schemas["DueMarker"]): Block {
  return { key: `D${d.item_id}`, item_id: d.item_id, title: d.title, start: d.due, end: d.due }
}

function Nights({ date, days, axis }: { date: string; days: Map<string, Schemas["CalendarDay"]>; axis: Axis }) {
  const nights = [days.get(addDays(date, -1)), days.get(date)].filter((n) => n !== undefined)
  return (
    <>
      {layout(nights.map((n) => ({ start: n.bedtime, end: n.core })), date, axis).map((p) => (
        <SleepBand key={`m${p.top}`} p={p} core={false} />
      ))}
      {layout(nights.map((n) => ({ start: n.core, end: n.wake })), date, axis).map((p) => (
        <SleepBand key={`c${p.top}`} p={p} core />
      ))}
    </>
  )
}

/** The minute under a mouse event, as `minuteAt` reads a pointer event. */
function minuteAtMouse(e: React.MouseEvent): number {
  const top = Number((e.currentTarget as HTMLElement).dataset.topMin)
  return top + (e.clientY - e.currentTarget.getBoundingClientRect().top) / PX
}

function grabbedEvent(event: Item & { start: string; end: string }, kind: "move" | "resize" | "resize-top", minute: number) {
  const start = toMin(event.start)
  return { kind, start, end: toMin(event.end), grab: minute - start, itemId: event.id, blockKey: null, title: event.title, event: true }
}

function grabbed(block: Block, kind: "move" | "resize" | "resize-top", minute: number) {
  const start = toMin(block.start)
  return { kind, start, end: toMin(block.end), grab: minute - start, itemId: block.item_id, blockKey: block.key, title: block.title }
}

function Preview({ drag, date, axis, today }: { drag: Drag; date: string; axis: Axis; today: string }) {
  if (!drag.at) return null
  const span = { start: fromMin(drag.at.start), end: fromMin(drag.at.end) }
  const locked = drag.locked && !drag.event // an event isn't pinned: Shift changes nothing
  const label = `${drag.title} ${when(span.start, today)}–${clock(span.end)}${locked ? " · locked" : ""}`
  return (
    <>
      {layout([span], date, axis).map((p) => (
        <DropPreview key={p.top} p={p} label={label} locked={locked} />
      ))}
    </>
  )
}

/** Where each picked block and event would land, dragged together. */
function GroupPreview({ drag, list, date, axis }: { drag: Drag; list: Pick[]; date: string; axis: Axis }) {
  if (!drag.at) return null
  const spans = drag.rows ? inARow(drag.rows, drag.at.start) : shifted(list, drag.at.start - drag.start)
  return (
    <>
      {spans.flatMap((s) =>
        layout([s], date, axis).map((p) => <DropPreview key={`${s.key}${p.top}`} p={p} label={`${s.title} ${clock(s.start)}–${clock(s.end)}`} locked={drag.locked} />),
      )}
    </>
  )
}

/** A time typed over a box on the grid (Pieces' TimeField). An event is saved as the drawer saves it: this time only,
 * for a repeat, and back to its calendar if it saves there. A block is pinned there as dragging it there pins it,
 * and a new length changes a fixed-length item's length, as resizing it does. */
function useRetime() {
  const client = useQueryClient()
  const toast = useToast()
  return {
    event: (item: Item, span: Span) => retimeEvent(client, toast, item.id, item.title, span),
    block: async (block: Block, span: Span) => {
      const { start, end } = span
      const kind = block.pinned === "locked" ? "locked" : "preferred"
      const by = toMin(end) - toMin(start) - (toMin(block.end) - toMin(block.start))
      const item = client.getQueryData<Item[]>(["items"])?.find((i) => i.id === block.item_id)
      if (by && item?.amount === "fixed" && item.duration_min != null) {
        await runCommand(client, toast, "edit", { id: block.item_id, duration_min: Math.max(15, item.duration_min + by) })
      }
      runCommand(client, toast, "pin", { id: block.item_id, start, end, kind, from_start: block.start, from_end: block.end }, { optimistic: (c) => moveBlock(c, block.key, start, end, kind) })
    },
  }
}

/** Items whose first block moved in the latest plan, with where it was, for ten seconds. */
function useMoved(plan: Schemas["PlanOut"]): Map<number, string> {
  const seen = useRef<{ planId: number | null; firsts: Map<number, string> } | null>(null)
  const [moved, setMoved] = useState(new Map<number, string>())
  useEffect(() => {
    const firsts = new Map<number, string>()
    for (const b of plan.blocks) if (!firsts.has(b.item_id)) firsts.set(b.item_id, b.start)
    const before = seen.current
    seen.current = { planId: plan.plan_id, firsts }
    if (!before || before.planId === plan.plan_id) return
    setMoved(movedSince(before.firsts, firsts))
    const timer = setTimeout(() => setMoved(new Map()), 10_000)
    return () => clearTimeout(timer)
  }, [plan])
  return moved
}
