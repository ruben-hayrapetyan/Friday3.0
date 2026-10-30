// The Inbox: everything waiting for you, one message each (29 Oct: "there are too many subcategories of inbox,
// simplify it and make everything just a message the user needs to deal with in inbox"). One list, most pressing
// first (messages.ts), and the message you're on opened beside it, the way mail is read: what only you can decide,
// the planned time Friday can't account for, sleep taps you missed, what came in from mail, calendars and syllabi,
// copies of a task, a go-over you started, repeating events to import. A message you deal with leaves the list at once
// and the next opens; ↑/↓ (or J/K) move between them. A suggestion shows the item it would make, each field with the
// words it came from, and the source with those words highlighted; nothing reaches the plan until you accept it (A),
// edit it (E) or reject it (R).

import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router"
import { query, type Schemas } from "@/api/client"
import { Chip, H, Icon } from "@/components/fr/controls"
import { DateTimeInput } from "@/components/fr/TimeInput"
import { useToast } from "@/components/Toasts"
import { useAreas } from "@/hooks/queries"
import { undoAll, useCommand } from "@/hooks/useCommand"
import { clock, dur, lateBy, when } from "@/lib/format"
import { useNotes } from "@/settings/AboutYou"
import { useShell } from "@/shell/ShellContext"
import { useLook } from "@/theme/LookProvider"
import { usePresets } from "@/todo/AddBox"
import { LengthInput } from "@/todo/Pickers"
import { useAllItems } from "@/todo/TodoPage"
import { GapPane, SleepPane } from "./DayPanes"
import { DecisionPane } from "./Decisions"
import { type Message, nextAfter, rowOf, waitingCount } from "./messages"
import { Actions, Pane } from "./Pane"
import { useDuplicates, useInbox, useInboxMessages, useToReview } from "./queries"
import { AgainPane, CopiesPane } from "./TaskPanes"

export { useInbox } from "./queries"

type Suggestion = Schemas["SuggestionOut"]
interface Resolved {
  s: Suggestion
  accepted: boolean
  commandId: number | null
}
type Done = (sent?: Promise<unknown>) => void

const FIELDS: [string, string][] = [
  ["title", "Title"],
  ["preset", "Kind"],
  ["area", "Tag"],
  ["due", "Due"],
  ["start", "Starts"],
  ["end", "Ends"],
  ["location", "Where"],
  ["duration_min", "Length"],
  ["every", "Repeats"],
]

const typing = (e: KeyboardEvent) => e.target instanceof HTMLElement && !!e.target.closest("input, textarea, select, [contenteditable]")

export function InboxPage() {
  const [resolved, setResolved] = useState<Resolved[]>([])
  const answered = useMemo(() => resolved.map((r) => r.s), [resolved])
  const messages = useInboxMessages(answered)
  const inbox = useInbox().data
  const copies = useDuplicates().data
  const going = useToReview().data
  const goOver = useCommand("review_again", { label: (o) => o.result.message ?? "Ready" })
  // Dealt with here: gone from the list at once, before the server says so; back if the command fails.
  const [gone, setGone] = useState<string[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const list = messages.filter((m) => !gone.includes(m.key))
  const live = (m: Message) => !(m.kind === "suggestion" && m.answered)
  const current = list.find((m) => m.key === selected) ?? list.find(live) ?? null
  const count = waitingCount(list)
  const tight = useShell().layout.tight // a narrow window: the list, then one message with a way back
  const [reading, setReading] = useState(false)
  const showList = !tight || !reading
  const showPane = !tight || reading
  useEffect(() => setGone((was) => was.filter((k) => messages.some((m) => m.key === k))), [messages])
  useEffect(() => {
    const press = (e: KeyboardEvent) => {
      if (typing(e) || e.metaKey || e.ctrlKey || e.altKey) return
      const step = ({ ArrowDown: 1, j: 1, ArrowUp: -1, k: -1 } as Record<string, number>)[e.key]
      if (!step || !current) return
      const at = list.findIndex((m) => m.key === current.key)
      const next = list[Math.max(0, Math.min(list.length - 1, at + step))]
      if (!next) return
      e.preventDefault()
      setSelected(next.key)
    }
    window.addEventListener("keydown", press)
    return () => window.removeEventListener("keydown", press)
  })
  /** Dealt with: the next opens, and it's back if the command fails. */
  const deal =
    (...keys: string[]): Done =>
    (sent) => {
      const without = new Set([...gone, ...keys])
      setSelected(nextAfter(list, keys[0], without))
      setGone((was) => [...was, ...keys])
      sent?.then((out) => out === undefined && setGone((was) => was.filter((k) => !keys.includes(k))))
    }
  const resolve = (rs: Resolved[]) => {
    const without = new Set([...gone, ...rs.map((r) => `s:${r.s.id}`)])
    if (current) setSelected(nextAfter(list, current.key, without))
    setResolved((all) => [...all.filter((r) => !rs.some((x) => x.s.id === r.s.id)), ...rs])
  }
  const open = (key: string) => (setSelected(key), setReading(true))
  const pane = (m: Message) => {
    switch (m.kind) {
      case "decision":
        return <DecisionPane key={m.key} decision={m.decision} onDone={deal(m.key)} />
      case "gap":
        return <GapPane key={m.key} date={m.date} gap={m.gap} onDone={deal(m.key)} />
      case "sleep":
        return <SleepPane key={m.key} ask={m.ask} onDone={deal(m.key)} />
      case "suggestion": {
        const waiting = list.filter((x): x is Extract<Message, { kind: "suggestion" }> => x.kind === "suggestion" && !x.answered && x.s.source === m.s.source).map((x) => x.s)
        return (
          <Detail
            key={m.key}
            s={m.s}
            all={list.flatMap((x) => (x.kind === "suggestion" ? [x.s] : []))}
            waiting={waiting}
            resolved={resolved.find((r) => r.s.id === m.s.id) ?? null}
            onResolved={resolve}
            onReopen={() => setResolved((all) => all.filter((r) => r.s.id !== m.s.id))}
          />
        )
      }
      case "copies": {
        const all = copies?.groups ?? [m.group]
        return <CopiesPane key={m.key} group={m.group} from={m.from} all={all} onDone={deal(m.key)} onAllDone={deal(...all.map((g) => `copies:${g.key}`))} />
      }
      case "again": {
        const all = going?.items ?? [m.item]
        return <AgainPane key={m.key} item={m.item} from={m.from} all={all} onDone={deal(m.key)} onAllDone={deal(...all.map((i) => `again:${i.id}`))} />
      }
      case "repeats":
        return <RepeatsPane key={m.key} n={m.n} />
    }
  }
  return (
    <>
      <div className="fr-page-head">
        <span className="fr-h fr-title">Inbox</span>
        <span className="tnum" style={{ color: "var(--color-neutral-500)" }}>
          {count ? `${count} to deal with` : "All clear"}
        </span>
        <div style={{ flex: 1 }} />
        {!going?.items.length && (
          <button className="fr-plain fr-link fr-head-note" onClick={() => goOver({})} title="Every open task Friday brought in from your calendars and mail, a message each, to keep or take off your list" style={{ fontSize: 12 }}>
            Go over everything again
          </button>
        )}
      </div>
      <div className="fr-panel" style={{ display: "grid", gridTemplateColumns: tight ? "minmax(0,1fr)" : "320px minmax(0,1fr)", overflow: "hidden" }}>
        {showList && (
          <div role="list" aria-label="Waiting for you" style={{ overflowY: "auto", minHeight: 0, padding: "10px 8px 40px", boxShadow: "inset -1px 0 0 color-mix(in srgb, var(--color-text) 7%, transparent)", display: "flex", flexDirection: "column", gap: 2 }}>
            {list.map((m) => (
              <Row key={m.key} m={m} on={m.key === current?.key} answered={resolved.find((r) => m.kind === "suggestion" && r.s.id === m.s.id)} onClick={() => open(m.key)} />
            ))}
            {!list.length && <span style={{ padding: 10, color: "var(--color-neutral-500)" }}>Nothing waiting.</span>}
            {!!inbox?.set_aside?.length && <SetAside items={inbox.set_aside} />}
          </div>
        )}
        {showPane && (
          <div style={{ display: "grid", gridTemplateRows: tight ? "auto minmax(0,1fr)" : "minmax(0,1fr)", minHeight: 0, minWidth: 0 }}>
            {tight && (
              <button className="fr-plain fr-link" onClick={() => setReading(false)} style={{ justifySelf: "start", padding: "12px 16px 0", fontSize: 13 }}>
                ← All {count}
              </button>
            )}
            {current ? (
              pane(current)
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "60px 40px", maxWidth: 460 }}>
                <Icon name="tray" size={28} style={{ color: "var(--color-neutral-400)" }} />
                <H size={26}>Inbox is clear</H>
                <span style={{ color: "var(--color-neutral-400)" }}>What needs you lands here, a message each: what only you can decide, planned time Friday can't account for, and what it finds in your mail, calendars and syllabi.</span>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  )
}

/** A message in the list: what kind it is, what it's about in a line, and when or where it's from. */
function Row({ m, on, answered, onClick }: { m: Message; on: boolean; answered?: Resolved; onClick: () => void }) {
  const { today } = useShell()
  const r = rowOf(m, today)
  return (
    <button
      role="listitem"
      aria-current={on || undefined}
      className="fr-plain fr-hover"
      onClick={onClick}
      style={{
        display: "grid",
        gridTemplateColumns: "18px minmax(0,1fr) auto",
        gap: 10,
        alignItems: "start",
        padding: "9px 10px",
        borderRadius: "var(--radius-md)",
        textAlign: "left",
        background: on ? "color-mix(in srgb, var(--color-accent) 13%, transparent)" : undefined,
        boxShadow: r.warn ? "inset 2px 0 0 var(--fr-warn)" : undefined,
        opacity: answered ? 0.5 : 1,
      }}
    >
      <Icon name={r.icon} size={15} style={{ color: r.warn ? "var(--fr-warn)" : "var(--color-neutral-400)", marginTop: 2 }} />
      <span style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
        <span style={{ fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", textDecoration: answered && !answered.accepted ? "line-through" : undefined }}>{r.title}</span>
        <span className="tnum" style={{ fontSize: 12, color: "var(--color-neutral-500)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {r.line}
        </span>
      </span>
      <span style={{ fontSize: 11, color: answered ? "var(--color-accent-300)" : "var(--color-neutral-500)", whiteSpace: "nowrap", maxWidth: 96, overflow: "hidden", textOverflow: "ellipsis", paddingTop: 2 }}>
        {answered ? (answered.accepted ? "Accepted" : "Rejected") : r.meta}
      </span>
    </button>
  )
}

/** Repeating events from your calendars not brought in yet: Settings → Repeating does that. */
function RepeatsPane({ n }: { n: number }) {
  const navigate = useNavigate()
  return (
    <Pane icon="repeat" kicker="From your calendars" title={`${n} repeating ${n === 1 ? "event" : "events"} to bring in`}>
      <span style={{ color: "var(--color-neutral-300)", textWrap: "pretty" }}>
        Weekly classes and other repeating events on your calendars that Friday doesn't plan around as repeats yet. Bring them in as repeating, or leave them out.
      </span>
      <Actions>
        <button className="btn btn-primary" onClick={() => navigate("/settings/repeating")}>
          <Icon name="repeat" />
          Open Repeating
        </button>
      </Actions>
    </Pane>
  )
}

/** What Friday didn't ask because you have it already (27 Oct: "please scan for duplicates before proposing things to
 * me"), folded under the list: each with why, and a way to ask it after all. */
function SetAside({ items }: { items: { id: number; title: string; why: string }[] }) {
  const [open, setOpen] = useState(false)
  const restore = useCommand("suggestion_restore", { label: (o) => o.result.message ?? "Back in your inbox" })
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, paddingTop: 10 }}>
      <button className="fr-plain fr-hover" onClick={() => setOpen(!open)} style={{ display: "flex", gap: 8, alignItems: "center", padding: "6px 8px", borderRadius: "var(--radius-sm)", fontSize: 12, color: "var(--color-neutral-400)" }} aria-expanded={open}>
        <Icon name={open ? "caret-down" : "caret-right"} size={11} />
        Set aside: {items.length} you have already
      </button>
      {open &&
        items.map((s) => (
          <div key={s.id} style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", gap: 8, alignItems: "center", padding: "4px 8px 4px 27px", fontSize: 12 }}>
            <span style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={s.title}>
                {s.title}
              </span>
              <span className="fr-kicker" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={s.why}>
                {s.why}
              </span>
            </span>
            <button className="btn btn-ghost" onClick={() => restore({ id: s.id })} style={{ fontSize: 11.5, padding: "2px 8px" }} title="Not a duplicate: ask me about it">
              Add anyway
            </button>
          </div>
        ))}
    </div>
  )
}

interface DetailProps {
  s: Suggestion
  all: Suggestion[]
  waiting: Suggestion[] // still to answer from the same source, this one too
  resolved: Resolved | null
  onResolved: (r: Resolved[]) => void
  onReopen: () => void
}

function Detail({ s, all, waiting, resolved, onResolved, onReopen }: DetailProps) {
  const { today } = useShell()
  const { color } = useLook()
  const client = useQueryClient()
  const toast = useToast()
  const presets = usePresets()
  const areas = (useAreas().data ?? []).map((a) => a.name)
  const items = useAllItems(true).data ?? []
  const [editing, setEditing] = useState(false)
  const [edits, setEdits] = useState<Record<string, unknown>>({})
  const accept = useCommand("suggestion_accept", { label: () => "Accepted" })
  const reject = useCommand("suggestion_reject", { label: () => "Rejected" })
  const batch = useCommand("batch_accept", { label: (o) => o.result.message ?? "Accepted" })
  const fields: Record<string, unknown> = { ...(s.input as Record<string, unknown>), ...edits }
  const dup = s.duplicate_of != null ? items.find((i) => i.id === s.duplicate_of) : null
  const doAccept = async () => {
    const out = await accept({ id: s.id, edits: edits as Record<string, never> })
    if (out) onResolved([{ s, accepted: true, commandId: out.command_id }])
  }
  const doReject = async () => {
    const out = await reject({ id: s.id })
    if (out) onResolved([{ s, accepted: false, commandId: out.command_id }])
  }
  /** Everything still waiting from this source, accepted as it is: a document's in one go, the rest one by one. */
  const acceptAll = async () => {
    const batches = [...new Set(waiting.map((x) => x.batch).filter((b): b is string => !!b))]
    for (const b of batches) {
      const out = await batch({ batch: b })
      if (out) onResolved(waiting.filter((x) => x.batch === b).map((x) => ({ s: x, accepted: true, commandId: out.command_id })))
    }
    for (const x of waiting.filter((x) => !x.batch)) {
      const out = await accept({ id: x.id, edits: {} })
      if (out) onResolved([{ s: x, accepted: true, commandId: out.command_id }])
    }
  }
  useEffect(() => {
    if (resolved) return
    const press = (e: KeyboardEvent) => {
      if (typing(e) || e.metaKey || e.ctrlKey || e.altKey) return
      if (e.key === "a") doAccept()
      if (e.key === "r") doReject()
      if (e.key === "e") setEditing((x) => !x)
    }
    window.addEventListener("keydown", press)
    return () => window.removeEventListener("keydown", press)
  })
  const value = (key: string, v: unknown): string => {
    if (v == null) return key === "duration_min" ? (s.guess_min ? `${dur(s.guess_min)}, Friday’s guess` : "Friday’s guess") : "—"
    if (key === "duration_min") return dur(Number(v))
    if (key === "every") return s.repeat ?? String(v)
    if (typeof v === "string" && /^\d{4}-\d\d-\d\dT/.test(v)) return when(v, today)
    return String(v)
  }
  // Work's length always shows, so a 12-hour assignment isn't accepted as Friday's 2-hour guess unnoticed.
  const work = fields.start == null && s.command === "add"
  const shown = FIELDS.filter(([k]) => fields[k] != null || (k === "duration_min" && work) || (editing && ["preset", "area", "due", "duration_min"].includes(k)))
  const actionLabel = s.command === "drop" ? "Drop it" : dup || s.command === "edit" ? "Update it" : "Accept"
  return (
    <div className="fr-gutter" style={{ overflowY: "auto", minHeight: 0, padding: "24px 28px 60px", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(320px, 100%), 1fr))", gap: 28, alignItems: "start" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 18, minWidth: 0 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, color: "var(--color-neutral-400)" }}>
            <Icon name="sparkle" size={13} style={{ color: "var(--color-accent-300)" }} />
            Found in {s.origin || "a document"}, {s.source}, {when(s.created, today)}
            {s.confidence < 1 && ` · ${Math.round(s.confidence * 100)}% sure`}
          </span>
          {editing ? (
            <input className="input" value={String(fields.title ?? "")} onChange={(e) => setEdits({ ...edits, title: e.target.value })} aria-label="Title" style={{ fontSize: 22, fontWeight: 600 }} />
          ) : (
            <H size={30}>{String(fields.title ?? s.origin)}</H>
          )}
        </div>
        {dup && (
          <div style={{ display: "grid", gridTemplateColumns: "auto minmax(0,1fr)", gap: 12, padding: "12px 14px", borderRadius: "var(--radius-md)", background: "color-mix(in srgb, var(--fr-mark) 9%, var(--color-bg))", boxShadow: "0 0 0 1px color-mix(in srgb, var(--fr-mark) 28%, transparent)" }}>
            <Icon name="copy" size={18} style={{ color: "var(--fr-warn)", marginTop: 1 }} />
            <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <span style={{ fontWeight: 500 }}>Looks like {dup.title}, already in Friday</span>
              <span style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>Accepting updates it rather than adding a second one.</span>
            </span>
          </div>
        )}
        <div style={{ display: "flex", flexDirection: "column" }}>
          {shown
            .filter(([k]) => k !== "title" || editing === false)
            .map(([k, label]) => (
              <div key={k} className="fr-row" style={{ display: "grid", gridTemplateColumns: "96px minmax(0,1fr)", gap: 14, padding: "12px 0" }}>
                <span className="fr-kicker" style={{ paddingTop: 2 }}>
                  {label}
                </span>
                <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 0 }}>
                  <span style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                    {k === "area" && fields.area != null && <span className="fr-swatch" style={{ background: color(String(fields.area)) }} />}
                    <span className="tnum" style={{ fontWeight: 500 }}>
                      {value(k, fields[k])}
                    </span>
                    {k in edits && <span style={{ fontSize: 11, color: "var(--color-accent-300)" }}>edited</span>}
                  </span>
                  {s.quotes[k] && (
                    <span style={{ display: "flex", gap: 8, fontSize: 12, color: "var(--color-neutral-300)", paddingLeft: 10, boxShadow: "inset 2px 0 0 color-mix(in srgb, var(--color-accent) 55%, transparent)" }}>
                      <Icon name="quotes" size={12} style={{ color: "var(--color-accent-400)", marginTop: 2, flex: "none" }} />
                      <span style={{ fontStyle: "italic" }}>{s.quotes[k]}</span>
                    </span>
                  )}
                  {editing && <EditField k={k} value={fields[k]} presets={presets} areas={areas} onChange={(v) => setEdits({ ...edits, [k]: v })} />}
                </div>
              </div>
            ))}
        </div>
        {resolved ? (
          <div className="fr-well" style={{ display: "flex", gap: 12, alignItems: "center", padding: "12px 14px" }}>
            <Icon name={resolved.accepted ? "check-circle" : "x-circle"} size={18} style={{ color: resolved.accepted ? "var(--color-accent-300)" : "var(--color-neutral-500)" }} />
            <span style={{ flex: 1 }}>{resolved.accepted ? "Accepted. It's in your plan." : "Rejected. It won't come back unless the source changes."}</span>
            {resolved.commandId !== null && (
              <button className="btn btn-ghost" onClick={async () => (await undoAll(client, toast, [resolved.commandId as number]), onReopen())}>
                Undo
              </button>
            )}
          </div>
        ) : null}
        {resolved && !resolved.accepted ? <TellWhy title={String(fields.title ?? s.origin)} /> : null}
        {!resolved && fields.start != null && fields.end != null && (s.command === "add" || s.command === "edit") && (
          <Effects id={s.id} start={String(fields.start)} end={String(fields.end)} />
        )}
        {!resolved && (
          <>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", paddingTop: 4 }}>
              <button className="btn btn-primary" onClick={doAccept}>
                <Icon name="check" />
                {actionLabel}
                <kbd style={{ marginLeft: 4, font: "inherit", fontSize: 10, opacity: 0.7 }}>A</kbd>
              </button>
              <button className="btn btn-secondary" onClick={() => setEditing(!editing)}>
                <Icon name="pencil-simple" />
                {editing ? "Done editing" : "Edit"}
                <kbd style={{ marginLeft: 4, font: "inherit", fontSize: 10, opacity: 0.6 }}>E</kbd>
              </button>
              <button className="btn btn-secondary" onClick={doReject}>
                <Icon name="x" />
                Reject
                <kbd style={{ marginLeft: 4, font: "inherit", fontSize: 10, opacity: 0.6 }}>R</kbd>
              </button>
            </div>
            <span className="fr-kicker">{s.command === "drop" ? "Dropping takes it off your plan; Undo brings it back." : "Accepting adds it and Friday plans it. You can undo it from the plan."}</span>
            {waiting.length > 1 && (
              <span style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", fontSize: 12, color: "var(--color-neutral-400)" }}>
                {waiting.length - 1} more from {s.source}.
                <button className="fr-plain fr-link" style={{ fontSize: 12 }} onClick={acceptAll}>
                  Accept all {waiting.length}
                </button>
              </span>
            )}
          </>
        )}
      </div>
      <SourceText s={s} all={all} />
    </div>
  )
}

/** What answering a suggested event would do (29 Oct: "when i am looking at whether to accept or decline events, can
 * you provide an idea of the repercussions"): accepting, what it clashes with, the work planned in its time (which
 * moves) and the work it makes later, worked out in a few seconds (commands/effects.py); declining, nothing in the
 * plan. At an edited time, that time is weighed. */
function Effects({ id, start, end }: { id: number; start: string; end: string }) {
  const { today } = useShell()
  const effect = useQuery({ queryKey: ["suggestion_effect", id, start, end], queryFn: () => query("suggestion_effect", { id, start, end }), staleTime: 60_000, retry: false })
  const e = effect.data && { event: effect.data.event, clashes: effect.data.clashes ?? [], takes: effect.data.takes ?? [], later: effect.data.later ?? [] }
  const span = (x: { start: string; end: string }) => `${when(x.start, today)}–${clock(x.end)}`
  const line = (icon: string, color: string, text: React.ReactNode) => (
    <span style={{ display: "grid", gridTemplateColumns: "16px minmax(0,1fr)", gap: 8, alignItems: "baseline", fontSize: 13, lineHeight: 1.45 }}>
      <Icon name={icon} size={13} style={{ color, position: "relative", top: 2 }} />
      <span>{text}</span>
    </span>
  )
  const quiet = e?.event && !e.clashes.length && !e.takes.length && !e.later.length
  return (
    <div className="fr-well" style={{ display: "flex", flexDirection: "column", gap: 12, padding: "12px 14px" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <span className="fr-kicker">If you accept</span>
        {effect.isLoading && line("hourglass-medium", "var(--color-neutral-500)", "Working out what it changes…")}
        {effect.isError && line("warning-circle", "var(--fr-warn)", "Couldn't work out what it changes right now.")}
        {e?.event &&
          e.clashes.map((c) =>
            line("calendar-x", "var(--fr-warn)", <>Clashes with <b style={{ fontWeight: 500 }}>{c.title}</b> ({span(c)})</>),
          )}
        {e?.event && e.takes.length > 0 &&
          line(
            "arrows-left-right",
            "var(--color-neutral-400)",
            <>
              Takes the time planned for {e.takes.map((t, i) => <span key={i}>{i ? ", " : ""}<b style={{ fontWeight: 500 }}>{t.title}</b> ({span(t)})</span>)}; Friday plans {e.takes.length === 1 ? "it" : "them"} elsewhere.
            </>,
          )}
        {e?.event &&
          e.later.map((l) =>
            line("clock-countdown", "var(--fr-due)", <><b style={{ fontWeight: 500 }}>{l.title}</b> finishes about {lateBy(l.hours)} later{l.due ? ` (due ${when(l.due, today)})` : ""}</>),
          )}
        {quiet && line("check-circle", "var(--color-accent-300)", "Nothing else changes: the time is free and no work finishes later.")}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <span className="fr-kicker">If you decline</span>
        {line("minus-circle", "var(--color-neutral-400)", "Nothing in your plan changes. Friday won't suggest it again unless the email or calendar changes.")}
      </div>
    </div>
  )
}

/** After a reject: say why once, and Friday reads everything after with it (Settings → About you). */
function TellWhy({ title }: { title: string }) {
  const { add } = useNotes()
  const [text, setText] = useState("")
  const [saved, setSaved] = useState(false)
  if (saved) return <span className="fr-kicker">Friday will remember that. Edit it in Settings → About you.</span>
  const save = () => {
    add(text)
    setSaved(true)
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <span style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>Why not? Say it once and Friday won't suggest things like it again.</span>
      <div style={{ display: "flex", gap: 8 }}>
        <input className="input" value={text} maxLength={300} placeholder={`e.g. “${title}” needs no time from me`} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && text.trim() && save()} style={{ flex: 1, fontSize: 13 }} />
        <button className="btn btn-secondary" disabled={!text.trim()} onClick={save}>
          Remember
        </button>
      </div>
    </div>
  )
}

function EditField({ k, value, presets, areas, onChange }: { k: string; value: unknown; presets: string[]; areas: string[]; onChange: (v: unknown) => void }) {
  if (k === "preset") return <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>{presets.map((p) => <Chip key={p} on={value === p} onClick={() => onChange(p)}>{p}</Chip>)}</div>
  if (k === "area") return <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>{areas.map((a) => <Chip key={a} on={value === a} onClick={() => onChange(a)}>{a}</Chip>)}</div>
  if (k === "duration_min") return <LengthInput value={value == null ? null : Number(value)} onPick={onChange} width={130} />
  if (k === "every") return null
  if (["due", "start", "end", "release"].includes(k)) return <DateTimeInput value={value == null ? null : String(value)} onChange={onChange} time={k === "due" ? "23:59" : "09:00"} label={k} />
  return <input className="input" value={String(value ?? "")} onChange={(e) => onChange(e.target.value || null)} style={{ maxWidth: 280, padding: "4px 8px", minHeight: 0 }} />
}

/** The text it was read from, this suggestion's quotes highlighted and other suggestions' shaded. */
function SourceText({ s, all }: { s: Suggestion; all: Suggestion[] }) {
  if (!s.source_text) return null
  const mine = Object.values(s.quotes)
  const theirs = all.filter((o) => o.id !== s.id && o.source_text === s.source_text).flatMap((o) => Object.values(o.quotes))
  const segments = highlight(s.source_text, mine, theirs)
  const [subject, ...rest] = s.origin.split("\n")
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, maxWidth: 520 }}>
      <span className="fr-kicker">From the source</span>
      <div className="fr-well" style={{ display: "flex", flexDirection: "column", gap: 12, padding: "16px 18px", borderRadius: "var(--radius-lg)" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 2, paddingBottom: 10, boxShadow: "inset 0 -1px 0 color-mix(in srgb, var(--color-text) 7%, transparent)" }}>
          <span style={{ fontWeight: 500 }}>{subject || "Document"}</span>
          <span className="fr-kicker">{rest.join(" ") || s.source}</span>
        </div>
        <div style={{ whiteSpace: "pre-wrap", fontSize: 13, lineHeight: 1.6, color: "var(--color-neutral-300)", maxHeight: 520, overflowY: "auto" }}>
          {segments.map((g, i) => (
            <span
              key={i}
              style={{
                background: g.kind === "mine" ? "color-mix(in srgb, var(--color-accent) 28%, transparent)" : g.kind === "theirs" ? "color-mix(in srgb, var(--color-text) 8%, transparent)" : undefined,
                color: g.kind === "mine" ? "var(--color-text)" : undefined,
                borderRadius: 3,
                padding: g.kind ? "0 2px" : undefined,
              }}
            >
              {g.text}
            </span>
          ))}
        </div>
      </div>
      <span style={{ fontSize: 11, color: "var(--color-neutral-500)" }}>Highlighted text is what Friday read. Other items from this source are shaded lightly.</span>
    </div>
  )
}

export function highlight(text: string, mine: string[], theirs: string[]): { text: string; kind: "mine" | "theirs" | null }[] {
  const marks: { at: number; end: number; kind: "mine" | "theirs" }[] = []
  for (const [quotes, kind] of [
    [mine, "mine"],
    [theirs, "theirs"],
  ] as const) {
    for (const q of quotes) {
      const at = q ? text.indexOf(q) : -1
      if (at >= 0 && !marks.some((m) => at < m.end && at + q.length > m.at)) marks.push({ at, end: at + q.length, kind })
    }
  }
  marks.sort((a, b) => a.at - b.at)
  const out: { text: string; kind: "mine" | "theirs" | null }[] = []
  let pos = 0
  for (const m of marks) {
    if (m.at > pos) out.push({ text: text.slice(pos, m.at), kind: null })
    out.push({ text: text.slice(m.at, m.end), kind: m.kind })
    pos = m.end
  }
  if (pos < text.length) out.push({ text: text.slice(pos), kind: null })
  return out
}
