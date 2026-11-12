// The selected block (v22): what it is, when, why Friday put it there, its due and what's left, and what you can do
// with it: start, finish, pin or unpin, unlock, skip one occurrence, delete (Delete or Backspace too). The timer's
// buttons are personal's (COMBINED.md 32): large, on top, Start or Pause, and Done; Resume once some of it is done,
// with how much, and that day's timed sittings below. A selected event shows its calendar, colour and notes, with
// Edit to open it in the drawer.

import { type QueryClient, useQueryClient } from "@tanstack/react-query"
import { useEffect, useRef, useState } from "react"
import { useLocation } from "react-router"
import type { Item, Schemas } from "@/api/client"
import { EstimateNudge } from "@/components/EstimateNudge"
import { TimeInput } from "@/components/fr/TimeInput"
import { Icon, Menu } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useItem, useItems, useSettings, useStatus, useWhy } from "@/hooks/queries"
import { whose } from "@/lib/aiName"
import { spanOn } from "@/lib/ampm"
import { likelyTask, ranked } from "@/lib/holds"
import { clock, dur, sittings, weekday, when } from "@/lib/format"
import { eventPaint, PIGMENTS } from "@/lib/pigments"
import { useAi } from "@/settings/AiConnect"
import { useLook } from "@/theme/LookProvider"
import { draftOf, useSeriesPattern } from "@/shell/EventPane"
import { repeatChoices } from "@/shell/repeats"
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
  timed: "Timed · when you worked on it",
  missed: "Missed · Friday planned it again",
  counted: "Past · counted as done",
}
const FIRM: Record<string, string> = { hard: "Hard deadline", soft: "Soft deadline", none: "No deadline" }

function BigButton({ icon, label, note, onClick, primary, tight, hint }: { icon: string; label: string; note: string; onClick: () => void; primary?: boolean; tight?: boolean; hint?: string }) {
  return (
    <button
      className={`btn ${primary ? "btn-primary" : "btn-secondary"}`}
      onClick={onClick}
      title={hint}
      style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 2, padding: tight ? "9px 8px" : "10px 12px", minHeight: 58, minWidth: 0 }}
    >
      <span style={{ display: "flex", gap: tight ? 5 : 8, alignItems: "center", fontSize: tight ? 13 : 15, whiteSpace: "nowrap" }}>
        <Icon name={icon} size={tight ? 15 : 18} fill={icon === "play"} />
        {label}
      </span>
      <span title={note} style={{ fontSize: 11.5, opacity: 0.75, fontFamily: "var(--fr-body)", maxWidth: "100%", textAlign: "left", lineHeight: 1.25, ...(tight ? {} : { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }) }}>
        {note}
      </span>
    </button>
  )
}

export function BlockPopover() {
  const { selected: b, select, today, setEvent } = useShell()
  const { pathname } = useLocation()
  useEffect(() => {
    if (pathname !== "/") select(null) // another page: the block isn't there to point at ("See on plan" selects on the way in)
  }, [pathname, select])
  const { color, light } = useLook()
  const card = useRef<HTMLElement>(null)
  const detail = useItem(b?.item_id ?? null).data
  const isBlock = !!b && b.key.startsWith("T")
  const why = useWhy(isBlock ? b.key : null).data
  const start = useCommand("start", { label: () => `Started ${b?.title}` })
  const done = useCommand("done", { label: () => `${b?.title}: done` })
  const reopen = useCommand("reopen", { label: () => `${b?.title}: open again` })
  const settle = useCommand("settle", { label: (o) => o.result.message })
  const stop = useCommand("stop", { label: (o) => o.result.message ?? "Paused" })
  const tentative = useCommand("edit", { label: (o) => (o.result.item.certainty === "tentative" ? "Might not happen: planned loosely" : "Planned as usual") })
  const status = useStatus().data
  const timing = status?.timer
  const pin = useCommand("pin", { label: () => `Pinned ${b?.title} here` })
  const unpin = useCommand("unpin", { label: () => `${b?.title}: Friday decides again` })
  const skip = useCommand("skip", { label: () => "Skipped this one" })
  const drop = useCommand("drop", { label: () => `Deleted ${b?.title}` })
  const giveBack = useCommand("unshove", { label: () => "That time is for work again" })
  const deleteSeries = useCommand("series_delete", { label: (o) => o.result.message ?? "Deleted" })
  const repeat = useCommand("repeat", { label: (o) => `${b?.title} repeats ${o.result.description.replace(/^Every/, "every")}` })
  const client = useQueryClient()
  const pattern = useSeriesPattern(detail?.item.series_id)
  const [asking, setAsking] = useState(false)
  const repeats = detail?.item.series_id != null
  useEffect(() => setAsking(false), [b?.key])
  useEffect(() => {
    if (!b) return
    const press = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLElement && e.target.closest("input, textarea, select")) return
      // Not before we know if it repeats; a sitting, or a past block missed or counted done, isn't deleted (no Delete
      // button shows for them either); and only on the plan, where Backspace means nothing else.
      const past = b.key.startsWith("S") || (!/^[FD]/.test(b.key) && (b.state === "missed" || b.state === "done"))
      if ((e.key !== "Delete" && e.key !== "Backspace") || !detail || past || pathname !== "/") return
      e.preventDefault()
      if (repeats) setAsking(true)
      else (drop({ id: b.item_id }), select(null))
    }
    window.addEventListener("keydown", press)
    return () => window.removeEventListener("keydown", press)
  }, [b, detail, repeats, drop, select, pathname])
  // A press anywhere else closes it, and goes on to what was pressed: another block opens in its place, and a second
  // click on this one's time can open the time for typing (Pieces' TimeField).
  const key = b?.key
  useEffect(() => {
    if (!key) return
    const press = (e: PointerEvent) => {
      const target = e.target instanceof Element ? e.target : null
      if (target && (card.current?.contains(target) || target.closest(`[data-block-key="${CSS.escape(key)}"]`))) return
      // ⌘-click on another block picks this one with it (the grid reads what's selected): let go of it after that
      // (12 Nov: let go of here first, the first ⌘-click picked only the block clicked)
      if (target?.closest("[data-block-key]") && (e.metaKey || e.ctrlKey || e.shiftKey)) return
      select(null)
    }
    window.addEventListener("pointerdown", press, true)
    return () => window.removeEventListener("pointerdown", press, true)
  }, [key, select])
  if (!b) return null
  const timedNow = timing?.item_id === b.item_id || !!status?.alongside?.some((t) => t.item_id === b.item_id)
  // Something else is being timed: Start would switch, so it says so, and Alongside keeps it going (2 Nov)
  const other = timing && !timedNow ? (timing.title ?? "what you're timing") : null
  const item = detail?.item
  const close = () => select(null)
  // A past block: what became of it (the server says), as a sitting you timed, a block missed, or one counted done.
  const kind = b.key.startsWith("F") ? "fixed" : b.key.startsWith("D") ? "due" : b.key.startsWith("S") ? "timed" : b.state === "missed" ? "missed" : b.state === "done" ? "counted" : kindOf(b)
  const sitting = kind === "timed" || kind === "missed" || kind === "counted" // what happened: nothing to move or pin
  const flexible = kind !== "fixed" && kind !== "due"
  const event = kind === "fixed" ? item : undefined
  const dot = event ? eventPaint(event, light) : color(b.area ?? item?.area)
  const date = b.start.slice(0, 10)
  const whenText = kind === "due" ? `Due ${when(b.start, today)}` : `${weekday(date)} ${Number(date.slice(8, 10))} ${MONTHS[Number(date.slice(5, 7)) - 1]} · ${clock(b.start)}–${clock(b.end)}`
  const run = (f: () => void) => () => (f(), close())
  const worked = item?.done_min ?? 0
  const timed = sittings(detail?.progress ?? [], date)
  const startNote = timing?.item_id ? "Pauses what's running" : worked ? `${dur(worked)} done${item?.remaining_min ? ` · ${dur(item.remaining_min)} left` : ""}` : "Times this sitting"
  return (
    <>
      <aside ref={card} className="fr-float fr-block-card" style={{ position: "absolute", right: 24, top: 72, width: 340, maxWidth: "calc(100% - 48px)", maxHeight: "calc(100% - 96px)", overflowY: "auto", zIndex: 10, padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 4 }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, color: "var(--color-neutral-400)" }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: dot, boxShadow: `0 0 calc(8px * var(--g-accent)) ${dot}` }} />
              {event ? [event.calendar ?? "Event", event.area].filter(Boolean).join(", ") : [item?.area, item?.preset].filter(Boolean).join(", ") || "No tag"}
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
        {event && event.event_kind !== "shove" && (!event.left_out || event.left_out === "skipped" || event.left_out === "through") && (
          <EventChoice event={event} flags={optionalFlags(client, event.id)} onClose={close} />
        )}
        {flexible && item?.status === "done" && (
          // Finished: nothing to start; it says so, and can be opened again.
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ display: "flex", gap: 6, alignItems: "center", color: "var(--color-accent-300)" }}>
              <Icon name="check-circle" size={16} fill />
              Done{worked ? ` · ${dur(worked)} in all` : ""}
            </span>
            <button className="btn btn-ghost" onClick={run(() => reopen({ id: b.item_id }))} style={{ marginLeft: "auto", fontSize: 12 }}>
              Open again
            </button>
          </div>
        )}
        {kind === "missed" && item?.status !== "done" && (
          // Not done in its time, so planned again; if you did it after all, one click counts it.
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <BigButton icon="check" label="I did it" note="Counts it; comes off the new plan" onClick={run(() => settle({ block_key: b.key, status: "done", until: b.end }))} primary />
            <BigButton icon="play" label={worked ? "Resume" : "Start"} note="Times it now" onClick={run(() => start({ id: b.item_id }))} />
          </div>
        )}
        {kind === "counted" && item?.status !== "done" && (
          <button className="fr-link" onClick={run(() => settle({ block_key: b.key, status: "not_done", until: b.end }))} style={{ alignSelf: "flex-start", fontSize: 12 }}>
            Didn’t do it? Plan it again
          </button>
        )}
        {flexible && item?.status !== "done" && kind !== "missed" && kind !== "counted" && (
          // Large and first: what you came to the block for (personal's popover).
          <div style={{ display: "grid", gridTemplateColumns: other ? "1fr 1.3fr 1fr" : "1fr 1fr", gap: 8 }}>
            {timedNow ? (
              <BigButton icon="pause" label="Pause" note="Keeps the time for next time" onClick={run(() => stop({ id: b.item_id }))} />
            ) : (
              <BigButton icon="play" label={other ? "Switch" : worked ? "Resume" : "Start"} note={other ? "Stops what's on" : startNote} hint={other ? `Times this instead: ${other} stops` : undefined} tight={!!other} onClick={run(() => start({ id: b.item_id }))} primary />
            )}
            {other && (
              // Two things at once (2 Nov): this one too, and what you're timing goes on.
              <BigButton icon="plus" label="Alongside" note="Both at once" hint={`Times this too: ${other} keeps going`} tight onClick={run(() => start({ id: b.item_id, alongside: true }))} />
            )}
            <BigButton icon="check" label="Done" note="Ticks it off" tight={!!other} onClick={run(() => (timedNow ? stop({ id: b.item_id, done: true }) : done({ id: b.item_id })))} />
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
        {event && <EventFacts event={event} paint={dot} />}
        {event && event.event_kind !== "shove" && event.left_out && event.left_out !== "skipped" && event.left_out !== "through" && <HeldFor event={event} />}
        {item && !event && (
          <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "6px 16px", fontSize: 12 }}>
            <span style={{ color: "var(--color-neutral-500)" }}>Due</span>
            <span>{item.due ? when(item.due, today) : "—"}</span>
            <span style={{ color: "var(--color-neutral-500)" }}>Deadline</span>
            <span>{FIRM[item.firmness] ?? "—"}</span>
            <span style={{ color: "var(--color-neutral-500)" }}>{item.amount === "fixed" && item.duration_min != null ? "Expected" : "Remaining"}</span>
            {item.amount === "fixed" && item.duration_min != null ? (
              <EstimateNudge itemId={item.id} runningMin={timing?.item_id === item.id ? (timing.elapsed_s ?? 0) / 60 : 0} />
            ) : (
              <span>{item.remaining_min != null ? `${dur(item.remaining_min)} left${item.duration_min ? ` of ${dur(item.duration_min)}` : ""}` : "—"}</span>
            )}
            {worked > 0 && (
              <>
                <span style={{ color: "var(--color-neutral-500)" }}>Done so far</span>
                <span style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <span>{dur(worked)}</span>
                  {item.duration_min ? (
                    <span style={{ height: 4, borderRadius: 2, background: "color-mix(in srgb, var(--color-text) 10%, transparent)", overflow: "hidden" }}>
                      <span style={{ display: "block", height: "100%", width: `${Math.min(100, (worked / item.duration_min) * 100)}%`, background: dot }} />
                    </span>
                  ) : null}
                </span>
              </>
            )}
            {timed && (
              <>
                <span style={{ color: "var(--color-neutral-500)" }}>Timed</span>
                <span className="tnum">{timed}</span>
              </>
            )}
          </div>
        )}
        {kind === "timed" && b.item_id != null && <SittingTimes itemId={b.item_id} start={b.start} end={b.end} onDone={close} />}
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {event && event.event_kind !== "shove" && (
            <button className="btn btn-secondary" onClick={run(() => setEvent(draftOf(event)))} title="Open it in the drawer: title, day, times, colour, notes">
              <Icon name="pencil-simple" />
              Edit
            </button>
          )}
          {flexible && item && !sitting && (
            <button
              className="btn btn-ghost"
              onClick={run(() => tentative({ id: b.item_id, certainty: item.certainty === "tentative" ? "planned" : "tentative" }))}
              title="Tentative work is planned loosely: Friday doesn't count on it happening"
            >
              <Icon name="cloud" />
              {item.certainty === "tentative" ? "It will happen" : "Might not happen"}
            </button>
          )}
          {flexible && !sitting && kind !== "locked" && (
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
          {item?.series_id != null && !event && !asking && (
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
          ) : sitting ? null : event?.event_kind === "shove" ? (
            // Time you shoved, given back to the plan (3 Nov: `unshove` had no button; ⌘Z only took back the last)
            <button className="btn btn-secondary" onClick={run(() => giveBack({ id: event.id }))} title="Friday may plan work here again" style={{ marginLeft: "auto" }}>
              <Icon name="arrow-counter-clockwise" />
              Give it back
            </button>
          ) : (
            <button className="btn btn-ghost" onClick={repeats ? () => setAsking(true) : run(() => drop({ id: b.item_id }))} title="Delete (⌫)" style={{ marginLeft: "auto", color: "var(--fr-due)" }}>
              <Icon name="trash" />
              Delete
            </button>
          )}
        </div>
        {flexible && !sitting && <Elsewhere block={b} onMoved={close} />}
        {item?.series_id != null ? (
          <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, color: "var(--color-neutral-400)" }}>
            <Icon name="repeat" size={13} />
            {pattern ? `Repeats ${pattern.replace(/^Every/, "every")}.` : "Repeats."} Skipping leaves the others as they are.
          </div>
        ) : (
          // One click to make it repeat, the choices named with its own day, as a calendar app's event card has
          // them (27 Oct); one from your calendar repeats there.
          event &&
          event.event_kind !== "shove" &&
          !event.calendar && (
            <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, color: "var(--color-neutral-400)" }}>
              <Icon name="repeat" size={13} />
              <Menu options={repeatChoices(b.start)} value="" onPick={(every) => every && (repeat({ id: b.item_id, every }), close())} label="Repeats" />
            </div>
          )
        )}
        {(event || (flexible && !sitting)) && <span className="fr-kicker">Double-click its time on the calendar to type a new one</span>}
      </aside>
    </>
  )
}

/** An event's calendar, colour and notes, as the drawer has them. */
/** What an event's time is for (planner/holds.py): a task you'll do in it ("A4dd" is when you write "CS A4 Design
 * Doc"), or nothing, as for any event. The task is planned there, and other work keeps off it. When a task's title is
 * clearly in the event's, Friday asks about that one; any other is a search away. */
/** A timed sitting's times, to put right (28 Oct: "what if i forgot to turn the timer off"): when you really started
 * and stopped, or take it away. The time counted as done, and what Friday learns of how long it takes, follow. */
function SittingTimes({ itemId, start, end, onDone }: { itemId: number; start: string; end: string; onDone: () => void }) {
  const [open, setOpen] = useState(false)
  const [from, setFrom] = useState(start.slice(11, 16))
  const [to, setTo] = useState(end.slice(11, 16))
  const edit = useCommand("sitting_edit", { label: () => "Sitting changed" })
  const remove = useCommand("sitting_delete", { label: (o) => o.result.message ?? "Sitting removed" })
  const span = { id: itemId, start, end }
  if (!open)
    return (
      <div style={{ display: "flex", gap: 12, fontSize: 12 }}>
        <button className="fr-link" onClick={() => setOpen(true)}>
          Change when you worked
        </button>
        <button className="fr-link" onClick={async () => (await remove(span)) && onDone()} style={{ color: "var(--fr-due)" }}>
          Remove this sitting
        </button>
      </div>
    )
  const typed = spanOn(start.slice(0, 10), from, to)
  const save = async () => {
    if (await edit({ ...span, new_start: typed.start, new_end: typed.end })) onDone()
  }
  return (
    <div role="group" aria-label="When you worked" onKeyDown={(e) => e.key === "Enter" && save()} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <span style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>When you really worked on it (a timer left running counts only this):</span>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <TimeInput value={from} onChange={(t) => t && setFrom(t)} label="Started" expect={{ near: from }} style={{ width: 96, padding: "4px 8px", minHeight: 0, fontSize: 13 }} />
        <span style={{ color: "var(--color-neutral-500)" }}>–</span>
        <TimeInput value={to} onChange={(t) => t && setTo(t)} label="Stopped" expect={{ after: from }} style={{ width: 96, padding: "4px 8px", minHeight: 0, fontSize: 13 }} />
        <span className="tnum" style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>
          {dur(Math.max(0, (Date.parse(`${typed.end}:00Z`) - Date.parse(`${typed.start}:00Z`)) / 60000))}
        </span>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn btn-primary fr-press" onClick={save} style={{ fontSize: 12 }}>
          <Icon name="check" />
          Save
        </button>
        <button className="btn btn-ghost" onClick={() => setOpen(false)} style={{ fontSize: 12 }}>
          Cancel
        </button>
      </div>
    </div>
  )
}

/** One of an event's two choices (12 Nov: the buttons were "very poorly formatted": a label running off the edge,
 * the two of different heights, the chosen one only outlined): a radio card like "How new to-dos arrive", the same
 * height as its neighbour, its words from the top left, the chosen one filled with its dot. */
function ChoiceCard({ label, note, on, onClick }: { label: string; note: string; on: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={on}
      onClick={onClick}
      className="fr-plain"
      style={{
        display: "grid",
        gridTemplateColumns: "14px minmax(0, 1fr)",
        alignContent: "start",
        columnGap: 8,
        rowGap: 3,
        minWidth: 0,
        padding: "10px 11px",
        textAlign: "left",
        borderRadius: "var(--radius-md)",
        background: on ? "color-mix(in srgb, var(--color-accent) 14%, var(--color-surface))" : "var(--color-surface)",
        boxShadow: on ? "inset 0 0 0 1.5px var(--color-accent)" : "inset 0 0 0 1px color-mix(in srgb, var(--color-text) 10%, transparent)",
      }}
    >
      <span aria-hidden="true" style={{ width: 14, height: 14, marginTop: 2, borderRadius: "50%", boxSizing: "border-box", border: on ? "4px solid var(--color-accent)" : "1.5px solid color-mix(in srgb, var(--color-text) 35%, transparent)" }} />
      <span style={{ fontWeight: 500, fontSize: 13.5, lineHeight: 1.3, whiteSpace: "nowrap" }}>{label}</span>
      <span className="fr-kicker" style={{ gridColumn: 2, lineHeight: 1.35, textWrap: "pretty" }}>
        {note}
      </span>
    </button>
  )
}

/** The task an event's time is for. `only` "work": under Work through it, where a to-do is optional (it's there first,
 * any work has the rest); "likely": only the question whether it's for the task its name suggests. */
function HeldFor({ event, only, open = event.left_out === "skipped" || event.left_out === "through" }: { event: Item; only?: "work" | "likely"; open?: boolean }) {
  const saveHold = useCommand("event_hold", { label: (o) => o.result.message })
  const tasks = (useItems().data ?? []).filter((i) => i.when !== "fixed" && i.status === "todo")
  const [choosing, setChoosing] = useState(false)
  const [text, setText] = useState("")
  // what you just picked shows at once, before the event comes back with it
  const [picked, setPicked] = useState<{ id: number; title: string } | null | undefined>(undefined)
  useEffect(() => (setChoosing(false), setText(""), setPicked(undefined)), [event.id])
  const hold = ({ id, task_id }: { id: number; task_id?: number }) => {
    const task = task_id == null ? null : tasks.find((t) => t.id === task_id)
    setPicked(task ? { id: task.id, title: task.title } : task_id == null ? null : undefined)
    saveHold(task_id == null ? { id } : { id, task_id })
  }
  const held = (picked !== undefined ? picked : event.holds) as { id: number; title: string; loose?: boolean } | null | undefined
  const likely = held ? null : likelyTask(event.title, tasks)
  const found = ranked(event.title, tasks.filter((t) => t.title.toLowerCase().includes(text.trim().toLowerCase()))).slice(0, 6)
  const box = { display: "flex", flexDirection: "column", gap: 8, padding: 12, borderRadius: "var(--radius-md)", background: "var(--color-bg)" } as const
  // `open`: worked through, so any work may have what the to-do doesn't use
  if (only === "likely" && (held || !likely)) return null
  if (choosing)
    return (
      <div style={box}>
        <span className="fr-kicker">{open ? "Which to-do first? Friday plans it here; any work can have the rest." : "Whose time is this? Friday plans that task here and keeps other work off it."}</span>
        <input className="input" autoFocus value={text} onChange={(e) => setText(e.target.value)} placeholder="Find a task" aria-label="Find a task" style={{ fontSize: 13 }} />
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {found.map((t) => (
            <button key={t.id} className="fr-plain fr-hover" onClick={() => (hold({ id: event.id, task_id: t.id }), setChoosing(false))} style={{ display: "flex", justifyContent: "space-between", gap: 8, padding: "6px 8px", borderRadius: "var(--radius-sm)", textAlign: "left" }}>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.title}</span>
              {t.remaining_min ? <span className="tnum fr-kicker">{dur(t.remaining_min)} left</span> : null}
            </button>
          ))}
          {!found.length && <span className="fr-kicker">No task by that name.</span>}
        </div>
        <button className="btn btn-ghost" onClick={() => setChoosing(false)} style={{ alignSelf: "flex-start", fontSize: 12 }}>
          Cancel
        </button>
      </div>
    )
  if (held)
    return (
      <div style={{ ...box, flexDirection: "row", alignItems: "center", flexWrap: "wrap" }}>
        <Icon name="tray-arrow-down" size={16} style={{ color: "var(--color-accent-300)" }} />
        <span style={{ flex: "1 1 160px", display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
          <span>Time for {held.title}</span>
          <span className="fr-kicker">
            {held.loose ? "Planned here when it can: you let it move when holding it made work late. Yes again holds it." : open ? "Planned here first; any work can have the rest." : "Planned here first; other work keeps off it."}
          </span>
        </span>
        {held.loose && (
          <button className="btn btn-ghost" onClick={() => hold({ id: event.id, task_id: held.id })} style={{ fontSize: 12 }}>
            Hold it
          </button>
        )}
        <button className="btn btn-ghost" onClick={() => setChoosing(true)} style={{ fontSize: 12 }}>
          Change
        </button>
        <button className="btn btn-ghost" onClick={() => hold({ id: event.id })} style={{ fontSize: 12 }} title={open ? "No to-do first: any work Friday picks" : "An event like any other again: work keeps off it"}>
          {open ? "Any work" : "Free it"}
        </button>
      </div>
    )
  return likely ? (
    <div style={{ ...box, flexDirection: "row", alignItems: "center", flexWrap: "wrap" }}>
      <Icon name="tray-arrow-down" size={16} style={{ color: "var(--color-accent-300)" }} />
      <span style={{ flex: "1 1 160px", minWidth: 0 }}>Is this time for {likely.title}?</span>
      <button className="btn btn-primary" onClick={() => hold({ id: event.id, task_id: likely.id })} style={{ fontSize: 12 }}>
        Yes
      </button>
      <button className="btn btn-ghost" onClick={() => setChoosing(true)} style={{ fontSize: 12 }}>
        Another task
      </button>
    </div>
  ) : only === "work" ? (
    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", fontSize: 12, color: "var(--color-neutral-300)" }}>
      <Icon name="briefcase" size={13} />
      <span style={{ flex: 1 }}>Any work Friday picks.</span>
      <button className="btn btn-ghost" onClick={() => setChoosing(true)} style={{ fontSize: 12 }} title="Optional: a to-do gets this time first">
        Pick a to-do
      </button>
    </div>
  ) : (
    <button className="btn btn-ghost" onClick={() => setChoosing(true)} style={{ alignSelf: "flex-start", fontSize: 12 }} title="Time set aside on your calendar for a task: Friday plans the task here">
      <Icon name="tray-arrow-down" />
      Use this time for a task
    </button>
  )
}

function EventFacts({ event, paint }: { event: Item; paint: string }) {
  const own = [event.color, event.chroma_color, event.category_color, event.calendar_color].find((c) => PIGMENTS.some((p) => p.id === c))
  const name = own ? PIGMENTS.find((p) => p.id === own)?.name : "Unmarked"
  // Where an automatic colour came from, as the drawer says it.
  const from = event.color ? null : event.chroma_color ? "as in Chroma" : event.category_color ? (event.category ?? "its category") : event.calendar_color ? (event.calendar ?? "its calendar") : null
  return (
    <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "6px 16px", fontSize: 12 }}>
      {event.location && (
        <>
          <span style={{ color: "var(--color-neutral-500)" }}>Where</span>
          <span style={{ display: "flex", gap: 6, alignItems: "center", overflowWrap: "anywhere" }}>
            <Icon name="map-pin" size={12} style={{ flex: "none" }} />
            {event.location}
          </span>
        </>
      )}
      <CategoryRow event={event} />
      <span style={{ color: "var(--color-neutral-500)" }}>Calendar</span>
      <span style={{ display: "flex", gap: 6, alignItems: "center" }}>
        {event.calendar ?? "Friday"}
        {event.calendar && <Icon name={event.saves_to_calendar ? "cloud-check" : "lock-simple"} size={12} />}
      </span>
      <span style={{ color: "var(--color-neutral-500)" }}>Colour</span>
      <span style={{ display: "flex", gap: 6, alignItems: "center" }}>
        <span style={{ width: 10, height: 10, borderRadius: 3, background: paint, flex: "none" }} />
        {name}
        {from && <span style={{ color: "var(--color-neutral-500)" }}>{from}</span>}
      </span>
      <span style={{ color: "var(--color-neutral-500)" }}>Notes</span>
      <span style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxHeight: 120, overflowY: "auto", color: event.notes ? undefined : "var(--color-neutral-500)" }}>{event.notes || "—"}</span>
    </div>
  )
}

const AUTO = "__auto"
const NONE = "__none"
// "claude" is how the server records an AI's pick, whichever AI it was: said by the AI you have (3 Nov)
const SAID: Record<string, string> = { you: "your choice", always: "your words" }

/** The event's category, who said, and yours to change: kept for every event with its title, and the events like it
 * follow (31 Oct: categories by word lists were "a very fragile way to do this"). An unsure guess is offered, not
 * painted. */
function CategoryRow({ event }: { event: Item }) {
  const settings = useSettings().data as { categories?: { categories?: { name: string }[] } } | undefined
  const choose = useCommand("event_category", { label: (o) => o.result.message ?? "Saved" })
  const ai = useAi().name
  const names = [...new Set((settings?.categories?.categories ?? []).map((c) => c.name))]
  if (!names.length) return null
  const by = event.category_by ?? ""
  const why = by === "similar" ? (event.category_like ? `like ${event.category_like}` : "like events you know") : by === "claude" ? `${whose(ai)} guess` : SAID[by]
  const options = [
    ...names.map((n) => ({ value: n, label: n })),
    { value: NONE, label: "None" },
    ...(by === "you" ? [{ value: AUTO, label: "Let Friday decide" }] : []),
  ]
  const pick = (value: string) => choose({ id: event.id, category: value === AUTO ? null : value === NONE ? "" : value })
  return (
    <>
      <span style={{ color: "var(--color-neutral-500)", alignSelf: "center" }}>Category</span>
      <span style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", minWidth: 0 }}>
        <Menu options={options} value={event.category ?? NONE} onPick={pick} label={`Category of ${event.title}`} />
        {why && <span style={{ color: "var(--color-neutral-500)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0 }}>{why}</span>}
        {!event.category && event.category_hint && (
          <button className="fr-link" onClick={() => pick(event.category_hint as string)} title="Friday's guess from events like it: not sure enough to colour it" style={{ fontSize: 12 }}>
            {event.category_hint}?
          </button>
        )}
      </span>
    </>
  )
}

type Flags = Pick<Item, "optional" | "going" | "gives_way_to">

/** What the plan says of an optional event (gym, climbing club): the calendar's plan has it (plan query). */
function optionalFlags(client: QueryClient, id: number): Flags | null {
  for (const [, plan] of client.getQueriesData<Schemas["PlanOut"]>({ queryKey: ["plan"] })) {
    const found = plan?.fixed?.find((f) => f.id === id)
    if (found?.optional) return found
  }
  return null
}

/** What you'll do in an event's time, as two big choices (11 Nov: "make the UI for choosing an event or whether to
 * work through it nicer"): go, and work keeps off it; or work through it, its time Friday's for any work (it stays on
 * your calendar). Working through it, a to-do can have the time first, if you like: none is needed. An optional event
 * (gym) is Friday's to give to work until you choose; one Friday would skip for a to-do says which. */
function EventChoice({ event, flags, onClose }: { event: Item; flags: Flags | null; onClose: () => void }) {
  const choose = useCommand("event_choice", { label: (o) => o.result.message })
  const keep = useCommand("event_keep", { label: (o) => o.result.message })
  type Choice = "going" | "through" | "skip"
  const [said, setSaid] = useState<Choice | null>(null)
  useEffect(() => setSaid(null), [event.id])
  const optional = !!flags?.optional
  const going = optional ? !!flags?.going : true
  const proposed = !going ? (flags?.gives_way_to ?? event.gives_way_to ?? null) : null
  const was: Choice | null = event.left_out === "skipped" ? "skip" : event.left_out === "through" || event.holds ? "through" : optional && !going ? null : "going"
  const now = said ?? was
  const pick = (choice: Choice) => {
    if (choice === now) return
    setSaid(choice)
    // an optional event (gym): going keeps it; otherwise it's back to Friday's to give
    if (optional && choice === "going" && !going) keep({ id: event.id, going: true })
    if (optional && choice !== "going" && flags?.going) keep({ id: event.id, going: false })
    choose({ id: event.id, choice })
    if (choice !== "through") onClose() // working through it, a to-do can be picked for its time next
  }
  const line = { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", fontSize: 12, color: "var(--color-neutral-300)" } as const
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {/* 12 Nov: "the work through it button should not be the same as the skip button": three, one under another */}
      <div role="radiogroup" aria-label="What you'll do in its time" style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: 6 }}>
        <ChoiceCard label="I'm going" note={proposed ? "Go anyway: work keeps off it" : "Work keeps off its time"} on={now === "going"} onClick={() => pick("going")} />
        <ChoiceCard label="Work through it" note="You're there, and Friday plans work in its time" on={now === "through"} onClick={() => pick("through")} />
        <ChoiceCard label="Skip it" note="You're not going: crossed out, its time free" on={now === "skip"} onClick={() => pick("skip")} />
      </div>
      {now === null && (
        <div style={line}>
          <Icon name="question" size={13} />
          <span style={{ flex: 1 }}>{proposed ? `Friday would skip it: ${proposed} needs the time.` : "Optional: Friday uses its time only if work needs it."}</span>
        </div>
      )}
      {now === "going" && optional && !said && (
        <div style={line}>
          <Icon name="check-circle" size={13} />
          <span style={{ flex: 1 }}>You're going: work keeps off it.</span>
          <button className="btn btn-ghost" onClick={() => (keep({ id: event.id, going: false }), onClose())} style={{ fontSize: 12 }}>
            Let Friday decide
          </button>
        </div>
      )}
      {now === "going" && !said && <HeldFor event={event} only="likely" />}
      {/* open: its time is work's (worked through), so a to-do has it first and any work the rest; an event you
          said is a to-do's time keeps the rest of it free of other work, and Free it lets it go */}
      {now === "through" && <HeldFor event={event} only="work" open={said === "through" || event.left_out === "through"} />}
    </div>
  )
}
