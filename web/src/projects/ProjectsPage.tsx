// Projects (v22): each open project with its progress; the selected one's steps in order (move them, tick them,
// set what each waits on and how long it takes), and a timeline of when each is planned against the due date.

import { useState } from "react"
import { useSearchParams } from "react-router"
import type { Item, Schemas } from "@/api/client"
import { Box, Check, H, Icon } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useHorizon, useProjects } from "@/hooks/queries"
import { dur, weekday, when } from "@/lib/format"
import { addDays, toMin } from "@/lib/time"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"
import { NewProject } from "./NewProject"

type Project = Schemas["ProjectOut"]
const STATUS: Record<Project["status"], [string, string]> = {
  on_track: ["On track", "var(--color-accent-300)"],
  late: ["Behind", "var(--fr-due)"],
  unplanned: ["Not planned yet", "var(--fr-warn)"],
  done: ["Done", "var(--color-neutral-400)"],
}

export function ProjectsPage() {
  const projects = useProjects().data ?? []
  const [params, setParams] = useSearchParams()
  const tight = useShell().layout.tight // a narrow window: the list, then one project with a way back
  const [creating, setCreating] = useState(false)
  const id = Number(params.get("id")) || projects[0]?.item.id
  const current = projects.find((p) => p.item.id === id) ?? null
  return (
    <>
      <div className="fr-page-head">
        <span className="fr-h fr-title">Projects</span>
        <span className="fr-head-note" style={{ color: "var(--color-neutral-500)", whiteSpace: "nowrap" }}>
          {projects.length} open{projects.some((p) => p.status === "late") ? `, ${projects.filter((p) => p.status === "late").length} behind` : ""}
        </span>
        <div style={{ flex: 1 }} />
        <button className="btn btn-primary" onClick={() => setCreating(true)} style={{ whiteSpace: "nowrap" }}>
          <Icon name="plus" />
          New project
        </button>
      </div>
      <div className="fr-panel" style={{ display: "grid", gridTemplateColumns: tight ? "minmax(0,1fr)" : "240px minmax(0,1fr)", overflow: "hidden" }}>
        {(!tight || !params.get("id")) && (
        <div style={{ overflowY: "auto", minHeight: 0, padding: "12px 10px", boxShadow: "inset -1px 0 0 color-mix(in srgb, var(--color-text) 7%, transparent)", display: "flex", flexDirection: "column", gap: 2 }}>
          {projects.map((p) => (
            <ListRow key={p.item.id} p={p} on={p.item.id === current?.item.id} onPick={() => setParams({ id: String(p.item.id) })} />
          ))}
          {!projects.length && <span style={{ padding: 8, color: "var(--color-neutral-500)" }}>No projects yet. A project is something with steps, like an essay or a presentation.</span>}
        </div>
        )}
        {(!tight || params.get("id")) && (
          <div style={{ display: "grid", gridTemplateRows: tight ? "auto minmax(0,1fr)" : "minmax(0,1fr)", minHeight: 0, minWidth: 0 }}>
            {tight && (
              <button className="fr-plain fr-link" onClick={() => setParams({})} style={{ justifySelf: "start", padding: "12px 16px 0", fontSize: 13 }}>
                ← All projects
              </button>
            )}
            {current ? <Detail key={current.item.id} p={current} /> : <div />}
          </div>
        )}
      </div>
      {creating && <NewProject onClose={(newId) => (setCreating(false), newId && setParams({ id: String(newId) }))} />}
    </>
  )
}

const pct = (p: Project) => (p.done_min + p.remaining_min ? Math.round((p.done_min / (p.done_min + p.remaining_min)) * 100) : 0)

function ListRow({ p, on, onPick }: { p: Project; on: boolean; onPick: () => void }) {
  const { today } = useShell()
  const { color } = useLook()
  const steps = p.children.filter((c) => c.parent_id === p.item.id)
  return (
    <button onClick={onPick} className="fr-plain fr-hover" style={{ display: "grid", gridTemplateColumns: "3px minmax(0,1fr)", gap: 10, padding: "9px 8px", borderRadius: "var(--radius-md)", background: on ? "color-mix(in srgb, var(--color-accent) 12%, transparent)" : undefined }}>
      <span style={{ borderRadius: 2, background: color(p.item.area) }} />
      <span style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
        <span style={{ fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{p.item.title}</span>
        <span style={{ height: 3, borderRadius: 2, background: "color-mix(in srgb, var(--color-text) 8%, transparent)" }}>
          <span style={{ display: "block", height: "100%", width: `${pct(p)}%`, borderRadius: 2, background: color(p.item.area) }} />
        </span>
        <span className="tnum" style={{ fontSize: 11, color: "var(--color-neutral-500)" }}>
          {steps.filter((c) => c.status === "done").length} of {steps.length} steps{p.item.due ? `, due ${when(p.item.due, today)}` : ""}
        </span>
      </span>
    </button>
  )
}

function Detail({ p }: { p: Project }) {
  const { today } = useShell()
  const { color } = useLook()
  const blocks = useHorizon().data?.blocks ?? []
  const add = useCommand("add", { label: () => "Step added" })
  const reorder = useCommand("reorder", { label: () => "Reordered" })
  const [text, setText] = useState("")
  const steps = p.children.filter((c) => c.parent_id === p.item.id)
  const total = p.done_min + p.remaining_min
  const [label, fg] = STATUS[p.status]
  const move = (i: number, by: number) => {
    const ids = steps.map((s) => s.id)
    const j = i + by
    if (j < 0 || j >= ids.length) return
    ;[ids[i], ids[j]] = [ids[j], ids[i]]
    reorder({ parent_id: p.item.id, ids })
  }
  return (
    <div style={{ overflowY: "auto", minHeight: 0, padding: "24px 30px 120px", display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 16, flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: 260, display: "flex", flexDirection: "column", gap: 6 }}>
          <span style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, color: "var(--color-neutral-400)" }}>
            <span className="fr-swatch" style={{ background: color(p.item.area) }} />
            {p.item.area ?? "No tag"}, {p.item.preset ?? "Project"}
          </span>
          <H size={36}>{p.item.title}</H>
          <span className="tnum" style={{ color: "var(--color-neutral-300)" }}>
            {p.item.due ? `Due ${when(p.item.due, today)}, ` : ""}
            {steps.length} steps, {dur(total)} in all
          </span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6, width: 220 }}>
          <div className="tnum" style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
            <span style={{ color: "var(--color-neutral-300)" }}>
              {dur(p.done_min)} of {dur(total)}
            </span>
            <span style={{ color: fg }}>{label}</span>
          </div>
          <div style={{ height: 6, borderRadius: 3, background: "color-mix(in srgb, var(--color-text) 8%, transparent)", overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${pct(p)}%`, background: color(p.item.area) }} />
          </div>
        </div>
      </div>
      <div style={{ display: "flex", flexDirection: "column" }}>
        <div style={{ display: "grid", gridTemplateColumns: "22px 18px minmax(0,1fr) 170px 96px 92px 28px", gap: 12, padding: "0 0 6px", fontSize: 11, color: "var(--color-neutral-500)" }}>
          <span />
          <span />
          <span>Step</span>
          <span>Waits on</span>
          <span style={{ textAlign: "right" }}>Length</span>
          <span style={{ textAlign: "right" }}>Planned</span>
          <span />
        </div>
        {steps.map((s, i) => (
          <Step key={s.id} step={s} steps={steps} first={i === 0} last={i === steps.length - 1} next={blocks.find((b) => b.item_id === s.id)?.start ?? null} onMove={(by) => move(i, by)} />
        ))}
        <div className="fr-row" style={{ display: "flex", gap: 8, alignItems: "center", padding: "10px 0" }}>
          <Icon name="plus" style={{ color: "var(--color-neutral-500)", marginLeft: 40 }} />
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={async (e) => e.key === "Enter" && text.trim() && (await add({ text, parent_id: p.item.id, area: p.item.area })) && setText("")}
            placeholder="Add a step ~2h"
            style={{ flex: 1, border: 0, outline: 0, background: "transparent", color: "var(--color-text)", font: "inherit" }}
          />
        </div>
      </div>
      <Timeline p={p} steps={steps} />
    </div>
  )
}

function Step({ step, steps, first, last, next, onMove }: { step: Item; steps: Item[]; first: boolean; last: boolean; next: string | null; onMove: (by: number) => void }) {
  const { today } = useShell()
  const [open, setOpen] = useState(false)
  const done = useCommand("done", { label: () => `${step.title}: done` })
  const reopen = useCommand("reopen", { label: () => "Open again" })
  const edit = useCommand("edit", { label: () => "Saved" })
  const drop = useCommand("drop", { label: () => "Deleted" })
  const depend = useCommand("depend", { label: () => "Now waits on it" })
  const undepend = useCommand("undepend", { label: () => "No longer waits" })
  const isDone = step.status === "done"
  const waits = step.waiting_on ?? []
  const names = waits.map((id) => steps.find((s) => s.id === id)?.title).filter(Boolean)
  // Waiting on something that (through its own waits) waits on this one would make a loop.
  const loops = (target: number): boolean => {
    const seen = new Set<number>()
    const stack = [target]
    while (stack.length) {
      const at = stack.pop() as number
      if (at === step.id) return true
      if (seen.has(at)) continue
      seen.add(at)
      stack.push(...(steps.find((s) => s.id === at)?.waiting_on ?? []))
    }
    return false
  }
  const length = step.duration_min ?? 60
  return (
    <div className="fr-row" style={{ display: "grid", gridTemplateColumns: "22px 18px minmax(0,1fr) 170px 96px 92px 28px", gap: 12, alignItems: "center", padding: "10px 0", opacity: isDone ? 0.55 : 1 }}>
      <span style={{ display: "flex", flexDirection: "column" }}>
        <button className="fr-plain" onClick={() => onMove(-1)} aria-label="Move up" style={{ height: 12, color: "var(--color-neutral-400)", opacity: first ? 0.25 : 1 }}>
          <Icon name="caret-up" size={12} />
        </button>
        <button className="fr-plain" onClick={() => onMove(1)} aria-label="Move down" style={{ height: 12, color: "var(--color-neutral-400)", opacity: last ? 0.25 : 1 }}>
          <Icon name="caret-down" size={12} />
        </button>
      </span>
      <Check done={isDone} onToggle={() => (isDone ? reopen({ id: step.id }) : done({ id: step.id }))} />
      <span style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
        <span style={{ fontWeight: 500, textDecoration: isDone ? "line-through" : undefined }}>{step.title}</span>
        {names.length > 0 && !isDone && (
          <span style={{ fontSize: 12, color: "var(--fr-warn)" }}>
            <Icon name="hourglass-medium" size={11} /> Waiting on {names.join(", ")}
          </span>
        )}
      </span>
      <button onClick={() => setOpen(!open)} className="fr-plain" title={names.join(", ") || "Nothing"} style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 8px", borderRadius: "var(--radius-md)", background: "var(--color-bg)", boxShadow: open ? "inset 0 0 0 1px var(--color-accent-500)" : "0 0 0 1px color-mix(in srgb, var(--color-text) 7%, transparent)", color: names.length ? "var(--color-text)" : "var(--color-neutral-500)", fontSize: 12, minWidth: 0 }}>
        <span style={{ flex: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{names.join(", ") || "Nothing"}</span>
        <Icon name="caret-down" size={10} style={{ opacity: 0.6 }} />
      </button>
      <span className="tnum" style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 4, fontSize: 12 }}>
        <button className="fr-plain" onClick={() => edit({ id: step.id, duration_min: Math.max(15, length - 15) })} aria-label="Shorter" style={{ padding: "0 2px", color: "var(--color-neutral-400)" }}>
          −
        </button>
        {dur(length)}
        <button className="fr-plain" onClick={() => edit({ id: step.id, duration_min: length + 15 })} aria-label="Longer" style={{ padding: "0 2px", color: "var(--color-neutral-400)" }}>
          +
        </button>
      </span>
      <span className="tnum" style={{ textAlign: "right", fontSize: 12, color: "var(--color-neutral-300)" }}>
        {isDone ? "Done" : next ? when(next, today) : "not planned"}
      </span>
      <button className="btn btn-icon btn-ghost" onClick={() => drop({ id: step.id })} aria-label="Delete step" title="Delete step" style={{ width: 28, height: 28, color: "var(--color-neutral-500)" }}>
        <Icon name="trash" />
      </button>
      {open && (
        <div style={{ gridColumn: "3 / -1", display: "flex", flexDirection: "column", gap: 2, padding: "8px 10px", borderRadius: "var(--radius-md)", background: "var(--color-bg)" }}>
          <span style={{ fontSize: 11, color: "var(--color-neutral-500)", paddingBottom: 4 }}>{step.title} waits on</span>
          {steps
            .filter((s) => s.id !== step.id)
            .map((s) => {
              const on = waits.includes(s.id)
              const cyc = !on && loops(s.id)
              return (
                <button key={s.id} disabled={cyc} onClick={() => (on ? undepend({ item_id: step.id, depends_on_id: s.id }) : depend({ item_id: step.id, depends_on_id: s.id }))} className="fr-plain fr-hover-soft" style={{ display: "flex", alignItems: "center", gap: 10, padding: "5px 4px", fontSize: 12, opacity: cyc ? 0.4 : 1 }}>
                  <Box on={on} />
                  {s.title}
                  {cyc && <span style={{ fontSize: 11, color: "var(--color-neutral-500)" }}>would loop</span>}
                </button>
              )
            })}
          <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: 4 }}>
            <button className="btn btn-ghost" onClick={() => setOpen(false)} style={{ fontSize: 12, padding: "3px 10px" }}>
              Done
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

/** When each step is planned, from today to the due date (or the last block). */
function Timeline({ p, steps }: { p: Project; steps: Item[] }) {
  const { today } = useShell()
  const { skinOf } = useLook()
  const blocks = useHorizon().data?.blocks ?? []
  const spans = steps.map((s) => ({ s, bs: blocks.filter((b) => b.item_id === s.id) }))
  const ends = [p.item.due, ...blocks.filter((b) => steps.some((s) => s.id === b.item_id)).map((b) => b.end)].filter((x): x is string => !!x)
  const last = ends.sort().at(-1) ?? addDays(today, 7)
  const lo = toMin(`${today}T00:00`)
  const hi = Math.max(lo + 3 * 1440, toMin(`${last.slice(0, 10)}T00:00`) + 1440)
  const at = (t: string) => ((toMin(t) - lo) / (hi - lo)) * 100
  const days = Math.round((hi - lo) / 1440)
  const every = Math.max(1, Math.ceil(days / 10))
  const axis = Array.from({ length: days }, (_, i) => addDays(today, i)).filter((_, i) => i % every === 0)
  const finish = p.planned_finish
  const slack = finish && p.item.due ? Math.round((toMin(p.item.due) - toMin(finish)) / 60) : null
  const line = p.status === "unplanned" ? "Some steps aren't planned yet: give them a length." : slack === null ? "" : slack >= 0 ? `Planned to finish ${when(finish as string, today)}, ${slack >= 24 ? `${Math.round(slack / 24)} days` : `${slack} h`} before it's due.` : `Planned to finish ${when(finish as string, today)}, after it's due.`
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
        <H size={18}>Timeline</H>
        <span className="fr-kicker">When each step is planned, up to the deadline</span>
      </div>
      <div style={{ position: "relative", padding: "22px 0 6px", borderRadius: "var(--radius-md)", background: "var(--color-bg)" }}>
        {axis.map((d) => (
          <span key={d}>
            <span className="tnum" style={{ position: "absolute", top: 4, left: `${at(`${d}T00:00`)}%`, fontSize: 10, color: "var(--color-neutral-500)", transform: "translateX(-50%)" }}>
              {weekday(d)} {Number(d.slice(8, 10))}
            </span>
            <span style={{ position: "absolute", top: 18, bottom: 0, left: `${at(`${d}T00:00`)}%`, width: 1, background: "color-mix(in srgb, var(--color-text) 7%, transparent)" }} />
          </span>
        ))}
        <span style={{ position: "absolute", top: 18, bottom: 0, left: `${Math.max(0, at(`${today}T12:00`))}%`, width: 2, background: "var(--fr-now)" }} />
        {p.item.due && (
          <>
            <span style={{ position: "absolute", top: 18, bottom: 0, left: `${at(p.item.due)}%`, width: 2, background: "var(--fr-due)" }} />
            <span style={{ position: "absolute", top: 4, left: `${at(p.item.due)}%`, fontSize: 10, color: "var(--fr-due)", paddingLeft: 4 }}>Due</span>
          </>
        )}
        {spans.map(({ s, bs }) => {
          const k = skinOf(s.status === "done" ? "done" : "planned", s.area)
          const from = bs.length ? at(bs[0].start) : null
          const to = bs.length ? at(bs[bs.length - 1].end) : null
          return (
            <div key={s.id} style={{ position: "relative", height: 28 }}>
              {from !== null && to !== null && (
                <div title={`${s.title}: ${bs.length} sessions`} style={{ position: "absolute", top: 4, height: 20, left: `${from}%`, width: `${Math.max(1.5, to - from)}%`, padding: "0 6px", borderRadius: 5, background: k.bg, border: k.bd, color: k.fg, fontSize: 11, lineHeight: "20px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {s.title}
                </div>
              )}
            </div>
          )
        })}
      </div>
      <span style={{ fontSize: 12, color: STATUS[p.status][1] }}>{line}</span>
    </div>
  )
}
