// Checking your tasks (from the Inbox): copies of the same task, and going over everything Friday brought in from
// your calendars and mail once more. A copy usually comes from one deadline sitting on two calendars; you pick the one
// to keep and the others' time logged moves onto it. Going over again keeps each task planned until you've decided:
// keep it, change its kind, or take it off your list (its calendar keeps the event either way).

import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { NavLink } from "react-router"
import { type Item, query } from "@/api/client"
import { DueLabel } from "@/components/DueLabel"
import { H, Icon, Menu, Seg } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { dur } from "@/lib/format"
import { useLook } from "@/theme/LookProvider"
import { usePresets } from "@/todo/AddBox"

export const useDuplicates = () => useQuery({ queryKey: ["duplicates"], queryFn: () => query("duplicates") })
const useToReview = () => useQuery({ queryKey: ["to_review"], queryFn: () => query("to_review") })

type Tab = "copies" | "again"

export function CheckTasks() {
  const copies = useDuplicates().data
  const review = useToReview().data
  const [tab, setTab] = useState<Tab>("copies")
  const groups = copies?.groups.length ?? 0
  const left = review?.items.length ?? 0
  return (
    <>
      <div className="fr-page-head" style={{ gap: 12 }}>
        <NavLink to="/inbox" className="fr-link" style={{ fontSize: 13 }}>
          ← Inbox
        </NavLink>
        <span className="fr-h fr-title">Check your tasks</span>
        <Seg
          options={[
            { value: "copies" as const, label: `Copies${groups ? ` (${groups})` : ""}` },
            { value: "again" as const, label: `Go over again${left ? ` (${left})` : ""}` },
          ]}
          value={tab}
          onPick={setTab}
          label="What to check"
        />
      </div>
      <div className="fr-panel" style={{ overflowY: "auto", minHeight: 0 }}>
        <div style={{ maxWidth: 860, padding: "18px 22px 140px", display: "flex", flexDirection: "column", gap: 18 }}>{tab === "copies" ? <Copies /> : <Again />}</div>
      </div>
    </>
  )
}

function Copies() {
  const data = useDuplicates().data
  const merge = useCommand("duplicates_merge", { label: (o) => o.result.message ?? "Merged" })
  const apart = useCommand("not_duplicates", { label: () => "Kept apart" })
  const [chosen, setChosen] = useState<Record<string, number>>({})
  if (!data) return null
  const keep = (key: string, fallback: number) => chosen[key] ?? fallback
  if (!data.groups.length)
    return (
      <Empty icon="copy" title="No copies" says="Every open task is there once. If the same task shows up twice later, it lands here." />
    )
  return (
    <>
      <div style={{ display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ flex: "1 1 320px", color: "var(--color-neutral-300)", fontSize: 13 }}>
          The same task more than once, usually a deadline on two of your calendars. Pick the one to keep; the others’ time logged moves onto it, and your calendars keep their events.
        </span>
        <button
          className="btn btn-primary"
          onClick={() => merge({ groups: data.groups.map((g) => ({ keep: keep(g.key, g.keep), drop: g.items.map((i) => i.id).filter((id) => id !== keep(g.key, g.keep)) })) })}
        >
          <Icon name="check" />
          Keep one of each ({data.groups.length})
        </button>
      </div>
      {data.groups.map((g) => {
        const kept = keep(g.key, g.keep)
        return (
          <section key={g.key} className="fr-well" style={{ display: "flex", flexDirection: "column", gap: 4, padding: "10px 12px", borderRadius: "var(--radius-md)" }}>
            {g.items.map((i) => (
              <label key={i.id} className="fr-hover-soft" style={{ display: "grid", gridTemplateColumns: "20px minmax(0,1fr)", gap: 8, alignItems: "center", padding: "4px 6px", borderRadius: 4, cursor: "pointer" }}>
                <input type="radio" name={g.key} checked={i.id === kept} onChange={() => setChosen({ ...chosen, [g.key]: i.id })} aria-label={`Keep ${i.title} (${data.sources[i.id] ?? "you"})`} />
                <TaskLine item={i} from={data.sources[i.id]} dim={i.id !== kept} />
              </label>
            ))}
            <span style={{ display: "flex", gap: 8, paddingTop: 4, flexWrap: "wrap" }}>
              <button className="btn btn-secondary" onClick={() => merge({ groups: [{ keep: kept, drop: g.items.map((i) => i.id).filter((id) => id !== kept) }] })} style={{ fontSize: 12 }}>
                Keep the chosen one
              </button>
              <button className="btn btn-ghost" onClick={() => apart({ ids: g.items.map((i) => i.id) })} style={{ fontSize: 12 }}>
                They’re different
              </button>
            </span>
          </section>
        )
      })}
    </>
  )
}

function Again() {
  const data = useToReview().data
  const start = useCommand("review_again", { label: (o) => o.result.message ?? "Ready" })
  const done = useCommand("reviewed", { label: (o) => o.result.message ?? "Done" })
  const edit = useCommand("edit", { label: () => "Kind changed" })
  const presets = usePresets()
  if (!data) return null
  if (!data.items.length)
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 12, alignItems: "flex-start", maxWidth: 520 }}>
        <Empty icon="arrow-counter-clockwise" title="Go over everything again" says="Every open task Friday brought in from your calendars and mail, one list. Keep each, change its kind, or take it off your list. Until you decide, it stays planned." />
        <button className="btn btn-primary" onClick={() => start({})}>
          <Icon name="list-checks" />
          Start going over them
        </button>
      </div>
    )
  return (
    <>
      <div style={{ display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ flex: "1 1 320px", color: "var(--color-neutral-300)", fontSize: 13 }}>
          {data.items.length} left. Keep what’s right, fix a wrong kind, remove what isn’t yours to do. Removing never touches your calendar.
        </span>
        <button className="btn btn-secondary" onClick={() => done({ ids: data.items.map((i) => i.id), keep: true })}>
          Keep all {data.items.length}
        </button>
      </div>
      <div style={{ display: "flex", flexDirection: "column" }}>
        {data.items.map((i) => (
          <div key={i.id} className="fr-row" style={{ display: "flex", flexWrap: "wrap", gap: "6px 12px", alignItems: "center", padding: "6px 0" }}>
            <span style={{ flex: "1 1 260px", minWidth: 0 }}>
              <TaskLine item={i} from={data.sources[i.id]} />
            </span>
            <Menu options={presets.map((p) => ({ value: p, label: p }))} value={i.preset ?? ""} onPick={(preset) => edit({ id: i.id, preset })} label={`Kind of ${i.title}`} />
            <button className="btn btn-secondary" onClick={() => done({ ids: [i.id], keep: true })} style={{ fontSize: 12 }} aria-label={`Keep ${i.title}`}>
              <Icon name="check" />
              Keep
            </button>
            <button className="btn btn-ghost" onClick={() => done({ ids: [i.id], keep: false })} style={{ fontSize: 12, color: "var(--fr-due)" }} aria-label={`Remove ${i.title}`}>
              <Icon name="x" />
              Remove
            </button>
          </div>
        ))}
      </div>
    </>
  )
}

/** A task on one line: its title and tag, then kind, due, length, time done and where it came from. */
function TaskLine({ item, from, dim }: { item: Item; from?: string; dim?: boolean }) {
  const { color } = useLook()
  const meta = { fontSize: 11, color: "var(--color-neutral-500)", whiteSpace: "nowrap" } as const
  return (
    <span style={{ display: "flex", flexWrap: "wrap", gap: "2px 10px", alignItems: "baseline", minWidth: 0, opacity: dim ? 0.6 : 1 }}>
      <span style={{ fontSize: 13, fontWeight: 500 }}>{item.title}</span>
      {item.area && (
        <span style={{ ...meta, display: "inline-flex", gap: 4, alignItems: "center" }}>
          <span style={{ width: 6, height: 6, borderRadius: 2, background: color(item.area, item.preset) }} />
          {item.area}
        </span>
      )}
      <span className="tnum fr-mono" style={meta}>
        {item.preset ?? "No kind"}
        {item.due && (
          <>
            {" · "}
            <DueLabel due={item.due} prefix="due " />
          </>
        )}
        {item.duration_min ? ` · ${dur(item.duration_min)}` : ""}
        {item.done_min ? ` · ${dur(item.done_min)} done` : ""}
        {` · from ${from ?? "you"}`}
      </span>
    </span>
  )
}

function Empty({ icon, title, says }: { icon: string; title: string; says: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: "30px 0 4px", maxWidth: 480 }}>
      <Icon name={icon} size={26} style={{ color: "var(--color-neutral-400)" }} />
      <H size={22}>{title}</H>
      <span style={{ color: "var(--color-neutral-400)", fontSize: 13 }}>{says}</span>
    </div>
  )
}
