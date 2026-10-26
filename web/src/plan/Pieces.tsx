// What sits in a day column (v22): blocks painted by kind in their area's colour, fixed items, ghosts of a plan
// being worked out, the wind-down band, the drop preview and the now line.

import { type CSSProperties, type ReactNode, useEffect, useLayoutEffect, useRef, useState } from "react"
import type { Block, Item } from "@/api/client"
import { Icon } from "@/components/fr/controls"
import { clock, dur, when } from "@/lib/format"
import { eventPaint, wash } from "@/lib/pigments"
import { type Placed, type Span, toMin } from "@/lib/time"
import { rangeText, readTimeRange } from "@/lib/timeRange"
import { useJustShoved } from "@/pops/shoved"
import { useLook } from "@/theme/LookProvider"
import type { Kind } from "@/theme/skin"

/** What if, as calendar apps draw tentative changes: an item a tried change makes is dashed, one it changes is
 * outlined, and one it deletes stays where it was, faded and struck through. */
export type TriedLook = "made" | "changed" | "gone"
const TRIED: Record<TriedLook, React.CSSProperties> = {
  made: { outline: "2px dashed var(--color-accent-300)", outlineOffset: -1 },
  changed: { outline: "2px solid color-mix(in srgb, var(--color-accent-300) 75%, transparent)", outlineOffset: -1 },
  gone: { opacity: 0.4, textDecoration: "line-through", background: "transparent", border: "1px dashed var(--color-neutral-500)" },
}

export const PX = 0.8 // per minute: 48 px an hour, as drawn

// A day column with a deadline lane (COMBINED.md 15) sets --lane to the lane's width; blocks share what's left.
function box(p: Placed<unknown>): CSSProperties {
  const share = 1 / p.columns
  const height = Math.max(p.height * PX - 2, 10) // a quarter hour is 12px: never taller, or it covers the next one
  return {
    position: "absolute",
    top: p.top * PX,
    height,
    left: `calc((100% - var(--lane, 0px)) * ${p.column * share} + 3px)`,
    width: `calc((100% - var(--lane, 0px)) * ${share} - 6px)`,
    // Under half an hour there's room for one line: the title, centred, its time beside it.
    ...(p.height < 30 ? { padding: "0 6px 0 9px", fontSize: 10.5, lineHeight: `${height - 2}px` } : { padding: "4px 7px 4px 9px", fontSize: 12, lineHeight: 1.3 }),
  }
}

const minutes = (b: { start: string; end: string }) => toMin(b.end) - toMin(b.start)

/** A fixed item as the selected "block" the popover reads. */
export function asBlock(item: Item & { start: string; end: string }): Block {
  return { key: `F${item.id}`, item_id: item.id, title: item.title, area: item.area, start: item.start, end: item.end }
}

/** Typing a box's time anew: `begin` when its time is double-clicked, `save` with what was typed. */
export interface Retime {
  begin: () => void
  save: (span: Span) => void
}

export function kindOf(b: Block): Kind {
  if (b.pinned === "locked") return "locked"
  if (b.pinned === "preferred") return "preferred"
  return b.tentative ? "tentative" : "planned"
}

interface BlockProps {
  p: Placed<Block>
  isCur: boolean
  selected: boolean
  done: boolean
  // A sitting you timed (drawn solid, when you worked), or a past block not done (a faint outline: Friday planned
  // it again). Neither moves or stretches.
  look?: "sitting" | "missed"
  movedFrom?: string
  tried?: TriedLook
  today: string
  onOpen: () => void
  onGrab: (e: React.PointerEvent) => void
  onResize: (e: React.PointerEvent) => void
  retime?: Retime
}

export function BlockBox({ p, isCur, selected, done, look, movedFrom, tried, today, onOpen, onGrab, onResize, retime }: BlockProps) {
  const b = p.item

  const { skinOf } = useLook()
  const kind = done ? "done" : look ? "planned" : kindOf(b)
  const s = skinOf(kind, b.area, { isCur, sel: selected }, b.preset)
  const tall = minutes(b) >= 45
  // A task that runs by itself (laundry): its first quarter hour needs you; the rest is it running, with other work on
  // top of it, so it's drawn faint and striped and isn't dragged (move it from the to-do instead).
  const running = !!b.background && !look && !done
  const fixedInPlace = done || !!look || running
  const missed = look === "missed"
  const [typing, setTyping] = useState(false)
  const time = retime && { typing, span: b, start: () => (setTyping(true), retime.begin()), save: retime.save, stop: () => setTyping(false) }
  return (
    <div
      role="button"
      tabIndex={0}
      data-block-key={b.key}
      onClick={onOpen}
      onKeyDown={(e) => e.key === "Enter" && onOpen()}
      onPointerDown={look || running ? undefined : onGrab}
      title={
        look === "sitting"
          ? `Timed ${b.title}: ${clock(b.start)}–${clock(b.end)} (${dur(minutes(b))})`
          : missed
            ? `${b.title} was planned ${clock(b.start)}–${clock(b.end)} and not done, so Friday planned it again. Click if you did it.`
            : running
              ? `${b.title}: start it at ${clock(b.start)}; it runs by itself until ${clock(b.end)}, with other work on top`
              : `${b.title} ${clock(b.start)}–${clock(b.end)}${b.tentative ? " (could fit here)" : ""}`
      }
      style={{
        ...box(p),
        touchAction: "none",
        userSelect: "none",
        borderRadius: 6,
        background: missed
          ? "transparent"
          : running
            ? `repeating-linear-gradient(135deg, color-mix(in srgb, ${s.stripe} 14%, transparent) 0 6px, transparent 6px 12px)`
            : s.bg,
        border: missed || running ? `1px dashed color-mix(in srgb, ${s.stripe} 55%, transparent)` : s.bd,
        ...(tried ? TRIED[tried] : {}),
        color: missed ? "var(--color-neutral-500)" : s.fg,
        opacity: missed ? 0.75 : running ? 0.85 : s.op,
        boxShadow: missed ? "none" : s.shadow,
        overflow: typing ? "visible" : "hidden",
        cursor: "pointer",
        zIndex: typing ? 5 : 1,
      }}
    >
      {!missed && <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 3, background: s.stripe }} />}
      <div style={{ display: "flex", alignItems: "center", gap: 4, fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden" }}>
        {b.pinned === "locked" && !look && <Icon name="lock-simple" fill size={11} />}
        {b.pinned === "preferred" && !look && <Icon name="push-pin" fill size={11} />}
        {done && <Icon name="check" size={11} />}
        {look === "sitting" && <Icon name="timer" size={11} />}
        <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{b.title}</span>
        {!tall && <Inline at={b.start} color={missed ? "var(--color-neutral-600)" : s.sub} time={look ? undefined : time} />}
      </div>
      {tall && (
        <TimeLine color={missed ? "var(--color-neutral-600)" : s.sub} time={look ? undefined : time}>
          {missed ? "Missed · planned again" : running ? `${clock(b.start)} start · runs by itself` : `${clock(b.start)}–${clock(b.end)}`}
          {look === "sitting" ? ` · ${dur(minutes(b))}` : b.estimated && !look ? ` · ~${dur(minutes(b))}` : ""}
        </TimeLine>
      )}
      {movedFrom && (
        <div style={{ fontSize: 10, color: "var(--color-accent-200)", whiteSpace: "nowrap" }}>moved from {when(movedFrom, today)}</div>
      )}
      {!fixedInPlace && (
        <div
          title="Drag to change length"
          onPointerDown={(e) => {
            e.stopPropagation()
            onResize(e)
          }}
          style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 7, cursor: "ns-resize" }}
        />
      )}
    </div>
  )
}

interface FixedProps {
  p: Placed<Item & { start: string; end: string }>
  onOpen: () => void
  onEdit?: () => void // a double-click on it, away from its time
  retime?: Retime
  tried?: TriedLook
}

export function FixedBox({ p, onOpen, onEdit, retime, tried }: FixedProps) {
  const it = p.item
  const { skinOf, light } = useLook()
  const base = skinOf(it.event_kind === "shove" ? "shove" : "fixed", it.area)
  // Painted as Chroma painted events: the pigment as a spine and an 11% wash over the page, the title in ink. Its
  // own pigment, else the one Chroma showed it in, else its category's, else its calendar's, else Chroma's
  // Unmarked slate (COMBINED.md 17). One left out of planning sits back, dashed.
  const paint = eventPaint(it, light)
  const painted = it.event_kind === "shove" ? base : { ...base, bg: wash(paint, light), stripe: paint, fg: "var(--color-text)", sub: "var(--color-neutral-400)" }
  const s = it.left_out ? { ...painted, bg: "transparent", bd: `1px dashed ${paint}`, fg: "var(--color-neutral-400)" } : painted
  const tall = minutes(it) >= 45
  const [typing, setTyping] = useState(false)
  const time = retime && { typing, span: it, start: () => (setTyping(true), retime.begin()), save: retime.save, stop: () => setTyping(false) }
  // Time you just shoved comes into view and glows, so you see it was taken back.
  const fresh = useJustShoved(it.id) && it.event_kind === "shove"
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (fresh) ref.current?.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" })
  }, [fresh])
  return (
    <div
      ref={ref}
      role="button"
      tabIndex={0}
      data-block-key={`F${it.id}`}
      className={fresh ? "fr-just-shoved" : undefined}
      onClick={onOpen}
      onDoubleClick={onEdit}
      onKeyDown={(e) => e.key === "Enter" && onOpen()}
      style={{
        ...box(p),
        borderRadius: 6,
        background: s.bg,
        border: s.bd,
        ...(tried ? TRIED[tried] : {}),
        color: s.fg,
        overflow: typing ? "visible" : "hidden",
        userSelect: "none",
        cursor: "pointer",
        ...(typing ? { zIndex: 5 } : {}),
      }}
    >
      <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 3, background: s.stripe }} />
      <div style={{ display: "flex", alignItems: "center", gap: 4, fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden" }}>
        {it.series_id != null && <Icon name="repeat" size={11} />}
        <span style={{ overflow: "hidden", textOverflow: "ellipsis" }} title={it.left_out ? `${it.title} — not counted as busy (${LEFT_OUT[it.left_out] ?? it.left_out})` : undefined}>
          {it.event_kind === "shove" ? "Your time" : it.title}
        </span>
        {!tall && <Inline at={it.start} color={s.sub} time={time} />}
      </div>
      {tall && (
        <TimeLine color={s.sub} time={time}>
          {clock(it.start)}–{clock(it.end)}
        </TimeLine>
      )}
    </div>
  )
}

/** A box's time, while it can be typed anew: whether it is being typed, and what to do. */
interface Timing {
  typing: boolean
  span: Span
  start: () => void
  save: (span: Span) => void
  stop: () => void
}

/** A short piece's time, on its one line after the title. */
function Inline({ at, color, time }: { at: string; color: string; time?: Timing }) {
  if (time?.typing) return <TimeField time={time} />
  return (
    <span className="tnum" onDoubleClick={retype(time)} title={time && "Double-click to change the time"} style={{ flex: "none", fontWeight: 400, color }}>
      {clock(at)}
    </span>
  )
}

/** A taller piece's time, on its own line under the title. */
function TimeLine({ color, time, children }: { color: string; time?: Timing; children: ReactNode }) {
  if (time?.typing) return <TimeField time={time} />
  return (
    <div className="tnum" style={{ fontSize: 11, color, whiteSpace: "nowrap" }}>
      <span onDoubleClick={retype(time)} title={time && "Double-click to change the time"}>
        {children}
      </span>
    </div>
  )
}

/** A double-click on a time opens it for typing, and not the event behind it. */
function retype(time?: Timing) {
  return time && ((e: React.MouseEvent) => (e.stopPropagation(), time.start()))
}

/** The time as text to type over: "10–11:30", "2pm-3pm", or a start alone that keeps the length. Return saves;
 * Escape or clicking away leaves it as it was. Red while it can't be read. */
function TimeField({ time }: { time: Timing }) {
  const [text, setText] = useState(() => rangeText(time.span))
  const typed = readTimeRange(text, time.span)
  const field = useRef<HTMLInputElement>(null)
  useLayoutEffect(() => {
    field.current?.focus()
    field.current?.select()
  }, [])
  const stop = (e: React.SyntheticEvent) => e.stopPropagation() // the box's own click, drag and Return
  return (
    <input
      ref={field}
      className="tnum"
      value={text}
      onChange={(e) => setText(e.target.value)}
      onPointerDown={stop}
      onClick={stop}
      onDoubleClick={stop}
      onBlur={time.stop}
      onKeyDown={(e) => {
        e.stopPropagation()
        if (e.key === "Escape") time.stop()
        if (e.key !== "Enter" || !typed) return
        time.stop()
        if (typed.start !== time.span.start || typed.end !== time.span.end) time.save(typed)
      }}
      aria-label="Time"
      aria-invalid={!typed}
      title="Type a time, like 10–11:30 or 3pm; Return saves, Escape doesn't"
      style={{
        display: "block",
        flex: "none",
        width: 150,
        maxWidth: "100%",
        height: 18,
        margin: "1px 0",
        padding: "0 5px",
        border: "none",
        borderRadius: 4,
        outline: `1.5px solid ${typed ? "var(--color-accent)" : "var(--fr-due)"}`,
        background: "var(--color-surface)",
        color: "var(--color-text)",
        font: "inherit",
        fontSize: 11,
        fontWeight: 400,
        lineHeight: "18px",
        userSelect: "text",
      }}
    />
  )
}

export const LEFT_OUT: Record<string, string> = {
  calendar: "its calendar isn't counted",
  reminder: "a reminder that something is due",
  free: "marked free",
  filtered: "the filter's office hours",
}

export function GhostBox({ p }: { p: Placed<Block> }) {
  const { skinOf } = useLook()
  const s = skinOf("ghost", p.item.area, undefined, p.item.preset)
  return (
    <div
      style={{
        ...box(p),
        pointerEvents: "none",
        padding: "4px 7px 4px 9px",
        borderRadius: 6,
        background: s.bg,
        border: s.bd,
        color: s.fg,
        opacity: s.op,
        fontSize: 12,
        fontWeight: 500,
        overflow: "hidden",
        whiteSpace: "nowrap",
      }}
    >
      {p.item.title}
    </div>
  )
}

/** A new or moved event, drafted in the drawer: dashed until it is saved. */
export function DraftBox({ p, title }: { p: Placed<unknown>; title: string }) {
  return (
    <div
      style={{
        ...box(p),
        pointerEvents: "none",
        zIndex: 3,
        padding: "4px 8px",
        borderRadius: 6,
        fontSize: 12,
        fontWeight: 500,
        color: "var(--color-text)",
        background: "color-mix(in srgb, var(--color-accent) 8%, var(--color-surface))",
        border: "1.5px dashed var(--color-accent)",
        overflow: "hidden",
      }}
    >
      {title || "New event"}
    </div>
  )
}

/** Where a dragged block or a selection would land. */
export function DropPreview({ p, label, locked }: { p: Placed<unknown>; label: string; locked: boolean }) {
  return (
    <div
      style={{
        ...box(p),
        pointerEvents: "none",
        zIndex: 3,
        padding: "3px 8px",
        borderRadius: 6,
        fontSize: 11,
        color: "var(--color-accent-200)",
        background: "color-mix(in srgb, var(--color-accent) 12%, transparent)",
        border: `1px ${locked ? "solid" : "dashed"} var(--color-accent)`,
      }}
    >
      {label}
    </div>
  )
}

/** The evening's wind-down (the sleep margin) and the core of the night. */
export function SleepBand({ p, core }: { p: Placed<unknown>; core: boolean }) {
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        top: p.top * PX,
        height: p.height * PX,
        pointerEvents: "none",
        background: core
          ? "color-mix(in srgb, var(--color-bg) 55%, transparent)"
          : "color-mix(in srgb, var(--color-accent) 7%, transparent)",
        display: "flex",
        alignItems: "flex-end",
        padding: "3px 8px",
        fontSize: 10,
        color: "var(--color-accent-500)",
      }}
    >
      {!core && p.height >= 20 && "only if due"}
    </div>
  )
}

export function NowLine({ top, today }: { top: number; today: boolean }) {
  if (!today) {
    return <div style={{ position: "absolute", left: 0, right: 0, top, height: 1, background: "color-mix(in srgb, var(--fr-now) 22%, transparent)", pointerEvents: "none" }} />
  }
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        top,
        height: 2,
        background: "var(--fr-now)",
        boxShadow: "0 0 calc(10px * var(--g-now)) calc(1px * var(--g-now)) var(--fr-now)",
        zIndex: 2,
        pointerEvents: "none",
      }}
    >
      <div style={{ position: "absolute", left: -4, top: -3, width: 8, height: 8, borderRadius: "50%", background: "var(--fr-now)" }} />
    </div>
  )
}
