// What sits in a day column (v22): blocks painted by kind in their area's colour, fixed items, ghosts of a plan
// being worked out, the wind-down band, the drop preview and the now line.

import type { CSSProperties } from "react"
import type { Block, Item } from "@/api/client"
import { Icon } from "@/components/fr/controls"
import { clock, dur, when } from "@/lib/format"
import { pigment } from "@/lib/pigments"
import { type Placed, toMin } from "@/lib/time"
import { useLook } from "@/theme/LookProvider"
import type { Kind } from "@/theme/skin"

export const PX = 0.8 // per minute: 48 px an hour, as drawn

// A day column with a deadline lane (COMBINED.md 15) sets --lane to the lane's width; blocks share what's left.
function box(p: Placed<unknown>): CSSProperties {
  const share = 1 / p.columns
  return {
    position: "absolute",
    top: p.top * PX,
    height: Math.max(p.height * PX - 2, 14),
    left: `calc((100% - var(--lane, 0px)) * ${p.column * share} + 3px)`,
    width: `calc((100% - var(--lane, 0px)) * ${share} - 6px)`,
  }
}

const minutes = (b: { start: string; end: string }) => toMin(b.end) - toMin(b.start)

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
  movedFrom?: string
  today: string
  onOpen: () => void
  onGrab: (e: React.PointerEvent) => void
  onResize: (e: React.PointerEvent) => void
}

export function BlockBox({ p, isCur, selected, done, movedFrom, today, onOpen, onGrab, onResize }: BlockProps) {
  const b = p.item
  const { skinOf } = useLook()
  const kind = done ? "done" : kindOf(b)
  const s = skinOf(kind, b.area, { isCur, sel: selected })
  const tall = minutes(b) >= 45
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => e.key === "Enter" && onOpen()}
      onPointerDown={onGrab}
      title={`${b.title} ${clock(b.start)}–${clock(b.end)}${b.tentative ? " (could fit here)" : ""}`}
      style={{
        ...box(p),
        touchAction: "none",
        userSelect: "none",
        padding: "4px 7px 4px 9px",
        borderRadius: 6,
        background: s.bg,
        border: s.bd,
        color: s.fg,
        opacity: s.op,
        boxShadow: s.shadow,
        overflow: "hidden",
        cursor: "pointer",
        fontSize: 12,
        lineHeight: 1.3,
        zIndex: 1,
      }}
    >
      <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 3, background: s.stripe }} />
      <div style={{ display: "flex", alignItems: "center", gap: 4, fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden" }}>
        {b.pinned === "locked" && <Icon name="lock-simple" fill size={11} />}
        {b.pinned === "preferred" && <Icon name="push-pin" fill size={11} />}
        {done && <Icon name="check" size={11} />}
        <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{b.title}</span>
      </div>
      {tall && (
        <div className="tnum" style={{ fontSize: 11, color: s.sub, whiteSpace: "nowrap" }}>
          {clock(b.start)}–{clock(b.end)}
          {b.estimated ? ` · ~${dur(minutes(b))}` : ""}
        </div>
      )}
      {movedFrom && (
        <div style={{ fontSize: 10, color: "var(--color-accent-200)", whiteSpace: "nowrap" }}>moved from {when(movedFrom, today)}</div>
      )}
      {!done && (
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

export function FixedBox({ p, onOpen }: { p: Placed<Item & { start: string; end: string }>; onOpen: () => void }) {
  const it = p.item
  const { skinOf, light } = useLook()
  const base = skinOf(it.event_kind === "shove" ? "shove" : "fixed", it.area)
  // Painted as personal painted events, the pigment on its spine and a wash of it: its own pigment, else its
  // category's, else its calendar's (COMBINED.md 17). One left out of planning sits back, dashed.
  const paint = pigment(it.color, light) ?? pigment(it.category_color, light) ?? pigment(it.calendar_color, light)
  const painted = paint ? { ...base, bg: `color-mix(in srgb, ${paint} 16%, var(--color-surface))`, stripe: paint, fg: "var(--color-text)", sub: "var(--color-neutral-400)" } : base
  const s = it.left_out ? { ...painted, bg: "transparent", bd: `1px dashed ${paint ?? "var(--fr-rule)"}`, fg: "var(--color-neutral-400)" } : painted
  const tall = minutes(it) >= 45
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => e.key === "Enter" && onOpen()}
      style={{
        ...box(p),
        padding: "4px 7px 4px 9px",
        borderRadius: 6,
        background: s.bg,
        border: s.bd,
        color: s.fg,
        overflow: "hidden",
        cursor: "pointer",
        fontSize: 12,
        lineHeight: 1.3,
      }}
    >
      <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 3, background: s.stripe }} />
      <div style={{ display: "flex", alignItems: "center", gap: 4, fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden" }}>
        {it.series_id != null && <Icon name="repeat" size={11} />}
        <span style={{ overflow: "hidden", textOverflow: "ellipsis" }} title={it.left_out ? `${it.title} — not counted as busy (${LEFT_OUT[it.left_out] ?? it.left_out})` : undefined}>
          {it.event_kind === "shove" ? "Your time" : it.title}
        </span>
      </div>
      {tall && (
        <div className="tnum" style={{ fontSize: 11, color: s.sub, whiteSpace: "nowrap" }}>
          {clock(it.start)}–{clock(it.end)}
        </div>
      )}
    </div>
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
  const s = skinOf("ghost", p.item.area)
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
