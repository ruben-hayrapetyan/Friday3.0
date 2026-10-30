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
import { useItem, useItems, useStatus, useWhy } from "@/hooks/queries"
import { spanOn } from "@/lib/ampm"
import { likelyTask, ranked } from "@/lib/holds"
import { clock, dur, sittings, weekday, when } from "@/lib/format"
import { eventPaint, PIGMENTS } from "@/lib/pigments"
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
  const timing = useStatus().data?.timer
  const pin = useCommand("pin", { label: () => `Pinned ${b?.title} here` })
  const unpin = useCommand("unpin", { label: () => `${b?.title}: Friday decides again` })
  const skip = useCommand("skip", { label: () => "Skipped this one" })
  const drop = useCommand("drop", { label: () => `Deleted ${b?.title}` })
  const deleteSeries = useCommand("series_delete", { label: (o) => o.result.message ?? "Deleted" })
  const repeat = useCommand("repeat", { label: (o) => `${b?.title} repeats ${o.result.description.replace(/^Every/, "every")}` })
  const keep = useCommand("event_keep", { label: (o) => o.result.message })
  // Not going to an event this time (30 Oct: "when i click an event (like salsa) it should give me the option to
  // skip"): it stays on your calendar, and its time is Friday's to plan; going after all gives it back
  const notGoing = useCommand("edit", { label: (o) => `Not going to ${o.result.item.title}: Friday can plan work over it` })
  const goingAfterAll = useCommand("edit", { label: (o) => `Going to ${o.result.item.title}` })
  const client = useQueryClient()
  const pattern = useSeriesPattern(detail?.item.series_id)
  const [asking, setAsking] = useState(false)
  const repeats = detail?.item.series_id != null
  useEffect(() => setAsking(false), [b?.key])
  useEffect(() => {
    if (!b) return
    const press = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLElement && e.target.closest("input, textarea, select")) return
      // Not before we know if it repeats; a sitting isn't deleted; and only on the plan, where Backspace means nothing else.
      if ((e.key !== "Delete" && e.key !== "Backspace") || !detail || b.key.startsWith("S") || pathname !== "/") return
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
      select(null)
    }
    window.addEventListener("pointerdown", press, true)
    return () => window.removeEventListener("pointerdown", press, true)
  }, [key, select])
  if (!b) return null
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
      <aside ref={card} className="fr-float" style={{ position: "absolute", right: 24, top: 72, width: 340, zIndex: 10, padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
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
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            {timing?.item_id === b.item_id ? (
              <BigButton icon="pause" label="Pause" note="Keeps the time for next time" onClick={run(() => stop({}))} />
            ) : (
              <BigButton icon="play" label={worked ? "Resume" : "Start"} note={startNote} onClick={run(() => start({ id: b.item_id }))} primary />
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
        {event && <EventFacts event={event} paint={dot} />}
        {event && event.event_kind !== "shove" && <HeldFor event={event} />}
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
          {event && event.event_kind !== "shove" && event.left_out === "skipped" && (
            <button className="btn btn-secondary" onClick={run(() => goingAfterAll({ id: event.id, blocks_time: true }))} title="Its time is yours again: work keeps off it">
              <Icon name="check" />
              Going after all
            </button>
          )}
          {event && event.event_kind !== "shove" && !event.left_out && !event.gives_way_to && (
            <button className="btn btn-secondary" onClick={run(() => notGoing({ id: event.id, blocks_time: false }))} title="Not going this time: it stays on your calendar, and Friday can plan work over it">
              <Icon name="skip-forward" />
              Skip it
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
          ) : sitting ? null : (
            <button className="btn btn-ghost" onClick={repeats ? () => setAsking(true) : run(() => drop({ id: b.item_id }))} title="Delete (⌫)" style={{ marginLeft: "auto", color: "var(--fr-due)" }}>
              <Icon name="trash" />
              Delete
            </button>
          )}
        </div>
        {flexible && !sitting && <Elsewhere block={b} onMoved={close} />}
        {event && <OptionalEvent flags={optionalFlags(client, event.id)} onKeep={(going) => (keep({ id: event.id, going }), close())} />}
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

function HeldFor({ event }: { event: Item }) {
  const hold = useCommand("event_hold", { label: (o) => o.result.message })
  const tasks = (useItems().data ?? []).filter((i) => i.when !== "fixed" && i.status === "todo")
  const [choosing, setChoosing] = useState(false)
  const [text, setText] = useState("")
  useEffect(() => (setChoosing(false), setText("")), [event.id])
  const held = event.holds as { id: number; title: string; loose?: boolean } | null | undefined
  const likely = held ? null : likelyTask(event.title, tasks)
  const found = ranked(event.title, tasks.filter((t) => t.title.toLowerCase().includes(text.trim().toLowerCase()))).slice(0, 6)
  const box = { display: "flex", flexDirection: "column", gap: 8, padding: 12, borderRadius: "var(--radius-md)", background: "var(--color-bg)" } as const
  if (choosing)
    return (
      <div style={box}>
        <span className="fr-kicker">Whose time is this? Friday plans that task here and keeps other work off it.</span>
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
            {held.loose ? "Planned here when it can: you let it move when holding it made work late. Yes again holds it." : "Planned here first; other work keeps off it."}
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
        <button className="btn btn-ghost" onClick={() => hold({ id: event.id })} style={{ fontSize: 12 }} title="An event like any other again: work keeps off it">
          Free it
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

type Flags = Pick<Item, "optional" | "going" | "gives_way_to">

/** What the plan says of an optional event (gym, climbing club): the calendar's plan has it (plan query). */
function optionalFlags(client: QueryClient, id: number): Flags | null {
  for (const [, plan] of client.getQueriesData<Schemas["PlanOut"]>({ queryKey: ["plan"] })) {
    const found = plan?.fixed?.find((f) => f.id === id)
    if (found?.optional) return found
  }
  return null
}

/** An optional event's say: skipped for work (go anyway), or one you're going to (let Friday decide again). */
function OptionalEvent({ flags, onKeep }: { flags: Flags | null; onKeep: (going: boolean) => void }) {
  if (!flags?.optional) return null
  const line = { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", fontSize: 12, color: "var(--color-neutral-300)" } as const
  if (flags.going)
    return (
      <div style={line}>
        <Icon name="check-circle" size={13} />
        <span style={{ flex: 1 }}>You're going: work keeps off it.</span>
        <button className="btn btn-ghost" onClick={() => onKeep(false)} style={{ fontSize: 12 }}>
          Let Friday decide
        </button>
      </div>
    )
  if (flags.gives_way_to)
    return (
      <div style={line}>
        <Icon name="skip-forward" size={13} />
        <span style={{ flex: 1 }}>Skipping it: {flags.gives_way_to} needs the time.</span>
        <button className="btn btn-secondary" onClick={() => onKeep(true)} style={{ fontSize: 12 }}>
          Go anyway
        </button>
      </div>
    )
  return (
    <div style={line}>
      <Icon name="question" size={13} />
      <span style={{ flex: 1 }}>Optional: Friday uses its time only if work needs it.</span>
      <button className="btn btn-ghost" onClick={() => onKeep(true)} style={{ fontSize: 12 }}>
        I'm going
      </button>
    </div>
  )
}
