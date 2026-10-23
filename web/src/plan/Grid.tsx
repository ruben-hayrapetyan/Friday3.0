// The week and day grid (v22 Plan): day headers with the date, pace, dues and overload; hour lines; blocks, fixed
// items, ghosts and the wind-down; drag to move, resize or select time. Settings → Appearance chooses the hours
// shown and whether a day's dues are header chips or a lane down its column (COMBINED.md 14, 15).

import { useEffect, useLayoutEffect, useRef, useState } from "react"
import type { Block, Item, Schemas } from "@/api/client"
import { type Drag, justDragged, minuteAt, selectionFrom, useDragging } from "@/components/calendar/useDrag"
import { useClock, useElapsed } from "@/hooks/useClock"
import { useGhosts, useItems, useNow, useStatus } from "@/hooks/queries"
import { movedSince } from "@/lib/drag"
import { clock, hms, weekday, when } from "@/lib/format"
import { type Axis, addDays, fromMin, hourMarks, layout, toMin } from "@/lib/time"
import { useShell } from "@/shell/ShellContext"
import { useLook } from "@/theme/LookProvider"
import { draftAt, draftOf } from "@/shell/EventPane"
import { DueLane } from "./DueLane"
import { BlockBox, DraftBox, DropPreview, FixedBox, GhostBox, NowLine, PX, SleepBand } from "./Pieces"

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
  const now = useClock()
  const { look } = useLook()
  const allDay24 = look.hours === "All day"
  // The lanes step aside while the to-do drawer is out, as personal's did: the full list is showing.
  const lanes = look.deadlines === "Lanes" && !drawer
  const axis: Axis = allDay24 ? { startMin: 0, endMin: 1440 } : { startMin: calendar.axis_start_min, endMin: calendar.axis_end_min }
  const panel = useRef<HTMLDivElement>(null)
  const head = useRef<HTMLDivElement>(null)
  const headHeight = useHeight(head)
  // All 24 hours open at the wake time, as a paper calendar opens at the morning.
  useLayoutEffect(() => {
    if (allDay24 && panel.current) panel.current.scrollTop = Math.max(0, calendar.axis_start_min - 30) * PX
  }, [allDay24, calendar.axis_start_min])
  const height = (axis.endMin - axis.startMin) * PX
  const days = new Map(calendar.days.map((d) => [d.date, d]))
  const planned = new Set(plan.blocks.map((b) => b.key))
  const news = ghosts.filter((g) => !planned.has(g.key))
  const timed = plan.fixed.filter((f): f is Item & { start: string; end: string } => !!f.start && !!f.end)
  // A birthday or holiday spans whole days: it goes with the day's dues at the top, not as a column-high block.
  const allDay = timed.filter((f) => f.start.endsWith("T00:00") && f.end.endsWith("T00:00") && f.end > f.start)
  const fixed = timed.filter((f) => !allDay.includes(f))
  // The same time of day in every column: strong on today, faint on the others.
  const nowAt = now - toMin(calendar.today) - axis.startMin
  const cols = `52px repeat(${dates.length}, minmax(0,1fr))`
  return (
    <div ref={panel} className="fr-panel" style={{ overflowY: "auto", position: "relative", marginRight }}>
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
              {layout(fixed, date, axis).map((p) => (
                <FixedBox key={`f${p.item.id}`} p={p} onOpen={() => (p.item.event_kind === "shove" ? select(asBlock(p.item)) : setEvent(draftOf(p.item)))} />
              ))}
              {event && !event.allDay && layout([event], date, axis).map((p) => <DraftBox key="draft" p={p} title={event.title} />)}
              {layout(plan.blocks, date, axis).map((p) => (
                <BlockBox
                  key={p.item.key}
                  p={p}
                  isCur={p.item.key === current}
                  selected={p.item.key === selected?.key}
                  done={toMin(p.item.end) <= now && !open.has(p.item.item_id)}
                  movedFrom={moved.get(p.item.item_id)}
                  today={today}
                  onOpen={() => !justDragged() && select(p.item)}
                  onGrab={(e) => begin(e, grabbed(p.item, "move", minuteAt(e)))}
                  onResize={(e) => begin(e, grabbed(p.item, "resize", minuteAt(e)))}
                />
              ))}
              {layout(news, date, axis).map((p) => (
                <GhostBox key={`g${p.item.key}`} p={p} />
              ))}
              {drag?.moved && drag.at && drag.over === "calendar" && <Preview drag={drag} date={date} axis={axis} today={today} />}
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
  // One line, two deadlines, the rest on a tap: five wrapped chips a day made the header half the screen.
  const mine = dues.filter((d) => d.due.startsWith(date))
  const shown = open ? mine : mine.slice(0, 2)
  const chip = { maxWidth: 150, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "block" } as const
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
      </div>
      <div style={{ display: "flex", flexWrap: open ? "wrap" : "nowrap", gap: 4, minHeight: 18, overflow: "hidden" }}>
        {over > 0.05 && (
          <span className="fr-tag warn">
            <i className="ph ph-warning" style={{ fontSize: 11 }} />
            {over.toFixed(1)} h over
          </span>
        )}
        {allDay
          .filter((f) => f.start.slice(0, 10) <= date && date < f.end.slice(0, 10))
          .map((f) => (
            <button key={`a${f.id}`} className="fr-tag fr-plain" title={f.title} onClick={() => select(asBlock(f))} style={{ flex: "none" }}>
              <i className="ph ph-calendar-blank" style={{ fontSize: 11 }} />
              <span style={chip}>{f.title}</span>
            </button>
          ))}
        {shown.map((d) => (
          <button key={d.item_id} className="fr-tag due fr-plain" title={`${d.title}, ${clock(d.due)}`} onClick={() => select(dueBlock(d))} style={{ flex: "none" }}>
            <i className="ph ph-flag" style={{ fontSize: 11 }} />
            <span style={chip}>{d.title}</span>
            {!d.due.endsWith("T23:59") && <span className="tnum">{clock(d.due)}</span>}
          </button>
        ))}
        {mine.length > 2 && (
          <button className="fr-tag fr-plain" onClick={() => setOpen(!open)} style={{ flex: "none", color: "var(--color-neutral-400)" }}>
            {open ? "less" : `+${mine.length - 2}`}
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

/** A fixed item or a due marker, as the selected "block" the popover reads. */
function asBlock(item: Item & { start: string; end: string }): Block {
  return { key: `F${item.id}`, item_id: item.id, title: item.title, area: item.area, start: item.start, end: item.end }
}

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

function grabbed(block: Block, kind: "move" | "resize", minute: number) {
  const start = toMin(block.start)
  return { kind, start, end: toMin(block.end), grab: minute - start, itemId: block.item_id, blockKey: block.key, title: block.title }
}

function Preview({ drag, date, axis, today }: { drag: Drag; date: string; axis: Axis; today: string }) {
  if (!drag.at) return null
  const span = { start: fromMin(drag.at.start), end: fromMin(drag.at.end) }
  const label = `${drag.title} ${when(span.start, today)}–${clock(span.end)}${drag.locked ? " · locked" : ""}`
  return (
    <>
      {layout([span], date, axis).map((p) => (
        <DropPreview key={p.top} p={p} label={label} locked={drag.locked} />
      ))}
    </>
  )
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
