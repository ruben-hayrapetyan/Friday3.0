// The Inbox (v22): what came in from mail, feeds, calendars and documents, by source. Each suggestion shows the item
// it would make, each field with the words it came from, and the source with those words highlighted. Nothing
// reaches the plan until you accept it (A), edit it (E) or reject it (R).

import { useQuery } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { query, type Schemas } from "@/api/client"
import { Chip, H, Icon } from "@/components/fr/controls"
import { undoAll, useCommand } from "@/hooks/useCommand"
import { useAllItems } from "@/todo/TodoPage"
import { useQueryClient } from "@tanstack/react-query"
import { useToast } from "@/components/Toasts"
import { dur, when } from "@/lib/format"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"
import { usePresets } from "@/todo/AddBox"
import { LengthInput } from "@/todo/Pickers"
import { useNotes } from "@/settings/AboutYou"
import { useAreas } from "@/hooks/queries"
import { NavLink } from "react-router"
import { useDuplicates } from "./CheckTasks"
import { Decisions, useDecisions } from "./Decisions"

type Suggestion = Schemas["SuggestionOut"]
interface Resolved {
  s: Suggestion
  accepted: boolean
  commandId: number | null
}

const ICONS: Record<string, string> = { gmail: "envelope-simple", ics: "rss", gcal: "google-logo", upload: "file-text" }
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

export const useInbox = () => useQuery({ queryKey: ["inbox"], queryFn: () => query("inbox") })

export function InboxPage() {
  const inbox = useInbox().data
  const copies = useDuplicates().data?.groups.length ?? 0
  const deciding = useDecisions().length
  const [selected, setSelected] = useState<number | null>(null)
  const [resolved, setResolved] = useState<Resolved[]>([])
  const pending = inbox?.suggestions ?? []
  const shown: Suggestion[] = [...pending, ...resolved.map((r) => r.s).filter((s) => !pending.some((p) => p.id === s.id))]
  const current = shown.find((s) => s.id === selected) ?? pending[0] ?? null
  const sources = [...new Set(shown.map((s) => s.source))]
  const tight = useShell().layout.tight // a narrow window: the list, then one suggestion with a way back
  const showList = !tight || selected === null
  const showDetail = !tight || selected !== null
  return (
    <>
      <div className="fr-page-head">
        <span className="fr-h fr-title">Inbox</span>
        <span className="tnum" style={{ color: "var(--color-neutral-500)" }}>
          {[deciding ? `${deciding} to decide` : "", pending.length ? `${pending.length} to check from ${new Set(pending.map((s) => s.source)).size} ${new Set(pending.map((s) => s.source)).size === 1 ? "source" : "sources"}` : ""].filter(Boolean).join(" · ") || "All clear"}
        </span>
        <div style={{ flex: 1 }} />
        <span className="fr-head-note" style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12, color: "var(--color-neutral-500)" }}>
          <Icon name="shield-check" size={14} />
          Nothing here reaches your plan until you accept it
        </span>
      </div>
      <div className="fr-panel" style={{ display: "grid", gridTemplateColumns: tight ? "minmax(0,1fr)" : "300px minmax(0,1fr)", overflow: "hidden" }}>
        {showList && (
        <div style={{ overflowY: "auto", minHeight: 0, padding: "12px 10px 40px", boxShadow: "inset -1px 0 0 color-mix(in srgb, var(--color-text) 7%, transparent)", display: "flex", flexDirection: "column", gap: 14 }}>
          <Decisions />
          <NavLink to="/inbox/check" className="fr-well fr-hover" style={{ display: "flex", gap: 10, alignItems: "center", padding: "10px 12px", color: "var(--color-text)", textDecoration: "none" }}>
            <Icon name="list-checks" size={16} style={{ color: "var(--color-accent-300)" }} />
            <span style={{ flex: 1, display: "flex", flexDirection: "column", gap: 1, fontSize: 12 }}>
              <span>Check your tasks{copies ? `: ${copies} with copies` : ""}</span>
              <span style={{ color: "var(--color-neutral-500)" }}>Copies, and going over what Friday brought in again</span>
            </span>
            <Icon name="caret-right" size={13} />
          </NavLink>
          {!!inbox?.repeats && (
            <NavLink to="/settings/repeating" className="fr-well fr-hover" style={{ display: "flex", gap: 10, alignItems: "center", padding: "10px 12px", color: "var(--color-text)", textDecoration: "none" }}>
              <Icon name="repeat" size={16} style={{ color: "var(--color-accent-300)" }} />
              <span style={{ flex: 1, fontSize: 12 }}>
                {inbox.repeats} repeating {inbox.repeats === 1 ? "event" : "events"} from your calendars to import in Repeating
              </span>
              <Icon name="caret-right" size={13} />
            </NavLink>
          )}
          {sources.map((name) => (
            <Source key={name} name={name} items={shown.filter((s) => s.source === name)} pending={pending} resolved={resolved} current={current?.id ?? null} onSelect={setSelected} onResolved={(r) => setResolved((all) => [...all, ...r])} />
          ))}
          {!sources.length && <span style={{ padding: 8, color: "var(--color-neutral-500)" }}>Nothing yet.</span>}
          {!!inbox?.set_aside?.length && <SetAside items={inbox.set_aside} />}
        </div>
        )}
        {showDetail && (
        <div style={{ display: "grid", gridTemplateRows: tight ? "auto minmax(0,1fr)" : "minmax(0,1fr)", minHeight: 0, minWidth: 0 }}>
        {tight && (
          <button className="fr-plain fr-link" onClick={() => setSelected(null)} style={{ justifySelf: "start", padding: "12px 16px 0", fontSize: 13 }}>
            ← All {pending.length}
          </button>
        )}
        {current ? (
          <Detail
            key={current.id}
            s={current}
            all={shown}
            resolved={resolved.find((r) => r.s.id === current.id) ?? null}
            onResolved={(rs) => {
              setResolved((all) => [...all, ...rs])
              const next = pending.find((p) => !rs.some((r) => r.s.id === p.id))
              setSelected(next?.id ?? current.id)
            }}
            onReopen={() => setResolved((all) => all.filter((r) => r.s.id !== current.id))}
          />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "60px 40px", maxWidth: 440 }}>
            <Icon name="tray" size={28} style={{ color: "var(--color-neutral-400)" }} />
            <H size={26}>Inbox is clear</H>
            <span style={{ color: "var(--color-neutral-400)" }}>New items from your email, course feeds and uploaded syllabi land here for you to check first.</span>
          </div>
        )}
        </div>
        )}
      </div>
    </>
  )
}

/** What Friday didn't ask because you have it already (27 Oct: "please scan for duplicates before proposing things to
 * me"), folded under the list: each with why, and a way to ask it after all. */
function SetAside({ items }: { items: { id: number; title: string; why: string }[] }) {
  const [open, setOpen] = useState(false)
  const restore = useCommand("suggestion_restore", { label: (o) => o.result.message ?? "Back in your inbox" })
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, paddingTop: 6 }}>
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

interface SourceProps {
  name: string
  items: Suggestion[]
  pending: Suggestion[]
  resolved: Resolved[]
  current: number | null
  onSelect: (id: number) => void
  onResolved: (r: Resolved[]) => void
}

function Source({ name, items, pending, resolved, current, onSelect, onResolved }: SourceProps) {
  const { today } = useShell()
  const { color } = useLook()
  const inbox = useInbox().data
  const source = inbox?.sources.find((s) => s.name === name)
  const open = items.filter((s) => pending.some((p) => p.id === s.id))
  const rows = items
  const openRows = open.length
  const batch = useCommand("batch_accept", { label: (o) => o.result.message ?? "Accepted" })
  const accept = useCommand("suggestion_accept", { label: () => "Accepted" })
  const acceptAll = async () => {
    const batches = [...new Set(open.map((s) => s.batch).filter((b): b is string => !!b))]
    for (const b of batches) {
      const out = await batch({ batch: b })
      if (out) onResolved(open.filter((s) => s.batch === b).map((s) => ({ s, accepted: true, commandId: out.command_id })))
    }
    for (const s of open.filter((x) => !x.batch)) {
      const out = await accept({ id: s.id, edits: {} })
      if (out) onResolved([{ s, accepted: true, commandId: out.command_id }])
    }
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <div style={{ display: "grid", gridTemplateColumns: "28px minmax(0,1fr) auto", gap: 10, alignItems: "center", padding: "4px 6px 6px" }}>
        <span className="fr-well" style={{ width: 28, height: 28, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Icon name={ICONS[items[0]?.source_kind ?? ""] ?? "tray"} size={15} style={{ color: "var(--color-neutral-300)" }} />
        </span>
        <span style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
          <span style={{ fontSize: 12, fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{name}</span>
          <span style={{ fontSize: 11, color: "var(--color-neutral-500)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {openRows} new{source?.last_sync ? ` · synced ${when(source.last_sync, today)}` : ""}
          </span>
        </span>
        {openRows > 1 && (
          <button className="btn btn-secondary" onClick={acceptAll} style={{ padding: "3px 9px", fontSize: 11, whiteSpace: "nowrap" }}>
            Accept all {openRows}
          </button>
        )}
      </div>
      {rows.map((s) => {
        const r = resolved.find((x) => x.s.id === s.id)
        const fields = s.input as Record<string, unknown>
        const at = (fields.due ?? fields.start) as string | undefined
        return (
          <div
            key={s.id}
            onClick={() => onSelect(s.id)}
            className="fr-hover"
            style={{
              display: "grid",
              gridTemplateColumns: "3px minmax(0,1fr) auto",
              gap: 10,
              alignItems: "center",
              padding: "8px 8px 8px 10px",
              marginLeft: 16,
              borderRadius: "var(--radius-md)",
              background: s.id === current ? "color-mix(in srgb, var(--color-accent) 12%, transparent)" : undefined,
              cursor: "pointer",
              opacity: r ? 0.55 : 1,
            }}
          >
            <span style={{ alignSelf: "stretch", borderRadius: 2, background: color(fields.area as string | undefined) }} />
            <span style={{ display: "flex", flexDirection: "column", gap: 1, minWidth: 0 }}>
              <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", textDecoration: r && !r.accepted ? "line-through" : undefined }}>{String(fields.title ?? s.origin)}</span>
              <span className="tnum" style={{ fontSize: 11, color: "var(--color-neutral-500)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {s.command === "edit" ? "A change · " : s.command === "drop" ? "Gone · " : ""}
                {at ? `${fields.due ? "due " : ""}${when(at, today)}` : ((fields.preset as string) ?? "")}
              </span>
            </span>
            <span style={{ display: "flex", gap: 4, alignItems: "center" }}>
              {s.duplicate_of != null && !r && <span className="fr-tag warn">Duplicate?</span>}
              {r?.accepted && <Icon name="check-circle" size={15} style={{ color: "var(--color-accent-300)" }} />}
              {r && !r.accepted && <Icon name="x-circle" size={15} style={{ color: "var(--color-neutral-500)" }} />}
            </span>
          </div>
        )
      })}
    </div>
  )
}

interface DetailProps {
  s: Suggestion
  all: Suggestion[]
  resolved: Resolved | null
  onResolved: (r: Resolved[]) => void
  onReopen: () => void
}

function Detail({ s, all, resolved, onResolved, onReopen }: DetailProps) {
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
  useEffect(() => {
    if (resolved) return
    const press = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLElement && e.target.closest("input, textarea, select")) return
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
            <H size={34}>{String(fields.title ?? s.origin)}</H>
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
          </>
        )}
      </div>
      <SourceText s={s} all={all} />
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
  if (["due", "start", "end", "release"].includes(k)) return <input type="datetime-local" step={900} className="input" value={String(value ?? "")} onChange={(e) => onChange(e.target.value || null)} style={{ maxWidth: 220, padding: "4px 8px", minHeight: 0 }} />
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
