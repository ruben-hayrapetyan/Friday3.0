// The selected block (v22): what it is, when, why Friday put it there, its due and what's left, and what you can do
// with it: start, finish, pin or unpin, unlock, skip one occurrence, delete (Delete or Backspace too). The timer's
// buttons are personal's (COMBINED.md 32): large, on top, Start or Pause, and Done.

import { useEffect, useState } from "react"
import { useLocation } from "react-router"
import { Icon } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useItem, useStatus, useWhy } from "@/hooks/queries"
import { clock, dur, weekday, when } from "@/lib/format"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"
import { Elsewhere } from "./Elsewhere"
import { kindOf } from "./Pieces"

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
const KIND: Record<string, string> = {
  planned: "Planned · Friday decides",
  preferred: "Pinned here · resists moving",
  locked: "Locked · won’t move",
  tentative: "Tentative · could fit here",
  fixed: "Fixed time",
  due: "Due",
  done: "Done",
}
const FIRM: Record<string, string> = { hard: "Hard deadline", soft: "Soft deadline", none: "No deadline" }

function BigButton({ icon, label, note, onClick, primary }: { icon: string; label: string; note: string; onClick: () => void; primary?: boolean }) {
  return (
    <button
      className={`btn ${primary ? "btn-primary" : "btn-secondary"}`}
      onClick={onClick}
      style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 2, padding: "10px 12px", minHeight: 58 }}
    >
      <span style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 15 }}>
        <Icon name={icon} size={18} fill={icon === "play"} />
        {label}
      </span>
      <span style={{ fontSize: 10.5, opacity: 0.75, fontFamily: "var(--fr-body)" }}>{note}</span>
    </button>
  )
}

export function BlockPopover() {
  const { selected: b, select, today } = useShell()
  const { pathname } = useLocation()
  useEffect(() => select(null), [pathname, select]) // another page: the block isn't there to point at
  const { color } = useLook()
  const detail = useItem(b?.item_id ?? null).data
  const isBlock = !!b && b.key.startsWith("T")
  const why = useWhy(isBlock ? b.key : null).data
  const start = useCommand("start", { label: () => `Started ${b?.title}` })
  const done = useCommand("done", { label: () => `${b?.title}: done` })
  const stop = useCommand("stop", { label: (o) => o.result.message ?? "Paused" })
  const tentative = useCommand("edit", { label: (o) => (o.result.item.certainty === "tentative" ? "Might not happen: planned loosely" : "Planned as usual") })
  const timing = useStatus().data?.timer
  const pin = useCommand("pin", { label: () => `Pinned ${b?.title} here` })
  const unpin = useCommand("unpin", { label: () => `${b?.title}: Friday decides again` })
  const skip = useCommand("skip", { label: () => "Skipped this one" })
  const drop = useCommand("drop", { label: () => `Deleted ${b?.title}` })
  const deleteSeries = useCommand("series_delete", { label: (o) => o.result.message ?? "Deleted" })
  const [asking, setAsking] = useState(false)
  const repeats = detail?.item.series_id != null
  useEffect(() => setAsking(false), [b?.key])
  useEffect(() => {
    if (!b) return
    const press = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLElement && e.target.closest("input, textarea, select")) return
      if ((e.key !== "Delete" && e.key !== "Backspace") || !detail) return  // not before we know if it repeats
      e.preventDefault()
      if (repeats) setAsking(true)
      else (drop({ id: b.item_id }), select(null))
    }
    window.addEventListener("keydown", press)
    return () => window.removeEventListener("keydown", press)
  }, [b, detail, repeats, drop, select])
  if (!b) return null
  const item = detail?.item
  const close = () => select(null)
  const kind = b.key.startsWith("F") ? "fixed" : b.key.startsWith("D") ? "due" : kindOf(b)
  const flexible = kind !== "fixed" && kind !== "due"
  const date = b.start.slice(0, 10)
  const whenText = kind === "due" ? `Due ${when(b.start, today)}` : `${weekday(date)} ${Number(date.slice(8, 10))} ${MONTHS[Number(date.slice(5, 7)) - 1]} · ${clock(b.start)}–${clock(b.end)}`
  const run = (f: () => void) => () => (f(), close())
  return (
    <>
      <div onClick={close} style={{ position: "absolute", inset: 0, zIndex: 9 }} />
      <aside className="fr-float" style={{ position: "absolute", right: 24, top: 72, width: 340, zIndex: 10, padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 4 }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, color: "var(--color-neutral-400)" }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: color(b.area ?? item?.area), boxShadow: `0 0 calc(8px * var(--g-accent)) ${color(b.area ?? item?.area)}` }} />
              {[item?.area, item?.preset].filter(Boolean).join(", ") || "No tag"}
            </div>
            <div className="fr-h" style={{ fontSize: 28, lineHeight: 1.05 }}>
              {b.title}
            </div>
            <div className="tnum" style={{ color: "var(--color-neutral-300)" }}>
              {whenText}
            </div>
          </div>
          <button className="btn btn-icon btn-ghost" onClick={close} aria-label="Close" style={{ width: 28, height: 28, color: "var(--color-neutral-400)" }}>
            <Icon name="x" />
          </button>
        </div>
        {flexible && (
          // Large and first: what you came to the block for (personal's popover).
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            {timing?.item_id === b.item_id ? (
              <BigButton icon="pause" label="Pause" note="Keeps the time for next time" onClick={run(() => stop({}))} />
            ) : (
              <BigButton icon="play" label="Start" note={timing?.item_id ? "Pauses what's running" : "Times this sitting"} onClick={run(() => start({ id: b.item_id }))} primary />
            )}
            <BigButton icon="check" label="Done" note="Ticks it off" onClick={run(() => (timing?.item_id === b.item_id ? stop({ done: true }) : done({ id: b.item_id })))} />
          </div>
        )}
        <div style={{ fontSize: 12, color: "var(--color-accent-300)" }}>{KIND[kind]}</div>
        {why && (
          <div style={{ padding: 12, borderRadius: "var(--radius-md)", background: "color-mix(in srgb, var(--color-accent) 10%, var(--color-bg))", display: "flex", flexDirection: "column", gap: 4 }}>
            <div style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12, color: "var(--color-accent-300)" }}>
              <Icon name="sparkle" />
              Why this time
            </div>
            <div style={{ textWrap: "pretty" }}>{why.sentence}</div>
          </div>
        )}
        {item && (
          <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "6px 16px", fontSize: 12 }}>
            <span style={{ color: "var(--color-neutral-500)" }}>Due</span>
            <span>{item.due ? when(item.due, today) : "—"}</span>
            <span style={{ color: "var(--color-neutral-500)" }}>Deadline</span>
            <span>{FIRM[item.firmness] ?? "—"}</span>
            <span style={{ color: "var(--color-neutral-500)" }}>Remaining</span>
            <span>{item.remaining_min != null ? `${dur(item.remaining_min)} left${item.duration_min ? ` of ${dur(item.duration_min)}` : ""}` : "—"}</span>
          </div>
        )}
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {flexible && item && (
            <button
              className="btn btn-ghost"
              onClick={run(() => tentative({ id: b.item_id, certainty: item.certainty === "tentative" ? "planned" : "tentative" }))}
              title="Tentative work is planned loosely: Friday doesn't count on it happening"
            >
              <Icon name="cloud" />
              {item.certainty === "tentative" ? "It will happen" : "Might not happen"}
            </button>
          )}
          {flexible && kind !== "locked" && (
            <button
              className="btn btn-secondary"
              onClick={run(() => (kind === "preferred" ? unpin({ id: b.item_id }) : pin({ id: b.item_id, start: b.start, end: b.end, kind: "preferred", from_start: b.start, from_end: b.end })))}
            >
              <Icon name="push-pin" />
              {kind === "preferred" ? "Unpin" : "Pin here"}
            </button>
          )}
          {kind === "locked" && (
            <button className="btn btn-secondary" onClick={run(() => pin({ id: b.item_id, start: b.start, end: b.end, kind: "preferred", from_start: b.start, from_end: b.end }))}>
              <Icon name="lock-simple-open" />
              Unlock
            </button>
          )}
          {item?.series_id != null && !asking && (
            <button className="btn btn-ghost" onClick={run(() => skip({ id: b.item_id }))}>
              <Icon name="skip-forward" />
              Skip this one
            </button>
          )}
          {asking ? (
            <span style={{ marginLeft: "auto", display: "flex", gap: 6, alignItems: "center" }}>
              <button className="btn btn-ghost" onClick={run(() => skip({ id: b.item_id }))}>
                Just this one
              </button>
              <button className="btn btn-ghost" onClick={run(() => deleteSeries({ id: item?.series_id as number }))} style={{ color: "var(--fr-due)" }}>
                Every one
              </button>
            </span>
          ) : (
            <button className="btn btn-ghost" onClick={repeats ? () => setAsking(true) : run(() => drop({ id: b.item_id }))} title="Delete (⌫)" style={{ marginLeft: "auto", color: "var(--fr-due)" }}>
              <Icon name="trash" />
              Delete
            </button>
          )}
        </div>
        {flexible && <Elsewhere block={b} onMoved={close} />}
        {item?.series_id != null && (
          <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, color: "var(--color-neutral-400)" }}>
            <Icon name="repeat" size={13} />
            Repeats. Skipping leaves the others as they are.
          </div>
        )}
      </aside>
    </>
  )
}
