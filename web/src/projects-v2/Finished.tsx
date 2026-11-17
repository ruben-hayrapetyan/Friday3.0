// The Finished shelf, folded: every finished project (archived, or ticked done) with what it took against its steps'
// lengths; each opens again, or is deleted (Undo, in its toast, brings it back).

import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { query } from "@/api/client"
import { H, Icon } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { dur, when } from "@/lib/format"
import { useLook } from "@/theme/LookProvider"
import { againstPlan, type Finished as FinishedProject } from "./model"

export const FINISHED_KEY = ["projects_finished"] as const
export const useFinished = () => useQuery({ queryKey: FINISHED_KEY, queryFn: () => query("projects_finished") })

const TONE = { warn: "var(--fr-warn)", good: "var(--color-accent-300)", quiet: "var(--color-neutral-400)" }

export function Finished({ today }: { today: string }) {
  const { color } = useLook()
  const found = useFinished().data ?? []
  const [open, setOpen] = useState(false)
  const [sure, setSure] = useState<number | null>(null)
  const gone = (id: number) => ({ optimistic: (client: import("@tanstack/react-query").QueryClient) => client.setQueryData<FinishedProject[]>(FINISHED_KEY, (list) => list?.filter((f) => f.id !== id)) })
  const unarchive = useCommand("project_unarchive", { label: (o) => o.result.message, optimistic: (client, input) => gone(input.id).optimistic(client) })
  const remove = useCommand("project_delete", { label: (o) => o.result.message, optimistic: (client, input) => gone(input.id).optimistic(client) })
  if (!found.length) return null
  return (
    <section aria-label="Finished" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <button className="fr-plain" onClick={() => setOpen(!open)} aria-expanded={open} style={{ display: "flex", gap: 10, alignItems: "baseline", textAlign: "left", flexWrap: "wrap" }}>
        <Icon name={open ? "caret-down" : "caret-right"} size={12} style={{ color: "var(--color-neutral-400)" }} />
        <H size={20}>Finished</H>
        <span className="fr-kicker">
          {found.length} {found.length === 1 ? "project" : "projects"} · what each took against its plan
        </span>
      </button>
      {open &&
        found.map((f) => {
          const plan = againstPlan(f)
          return (
            <div key={f.id} style={{ display: "flex", flexWrap: "wrap", gap: "6px 14px", alignItems: "center", padding: "10px 6px", boxShadow: "inset 0 -1px 0 color-mix(in srgb, var(--color-text) 7%, transparent)" }}>
              <span style={{ width: 4, alignSelf: "stretch", borderRadius: 2, background: color(f.area, "Project") }} />
              <span style={{ display: "flex", flexDirection: "column", gap: 2, flex: "1 1 200px", minWidth: 0 }}>
                <span style={{ fontWeight: 500, overflowWrap: "anywhere" }}>{f.title}</span>
                <span className="fr-kicker">
                  {f.steps} {f.steps === 1 ? "step" : "steps"}
                  {f.finished ? ` · finished ${when(f.finished, today).toLowerCase()}` : ""}
                </span>
              </span>
              <span className="tnum" style={{ fontSize: 13, flex: "none" }}>
                {dur(f.actual_min) || "0m"} <span className="fr-kicker">of {dur(f.estimate_min) || "no plan"} planned</span>
              </span>
              <span className="tnum" style={{ fontSize: 12, color: TONE[plan.tone], flex: "none", minWidth: 110 }}>
                {plan.words}
              </span>
              <span style={{ display: "flex", gap: 4, flex: "none", alignItems: "center", flexWrap: "wrap" }}>
                {sure === f.id ? (
                  <>
                    <button className="btn btn-secondary" onClick={() => (setSure(null), remove({ id: f.id }))} style={{ fontSize: 12, padding: "3px 8px", color: "var(--fr-due)" }}>
                      Delete it
                    </button>
                    <button className="btn btn-ghost" onClick={() => setSure(null)} style={{ fontSize: 12, padding: "3px 8px" }}>
                      Keep it
                    </button>
                  </>
                ) : (
                  <>
                    <button className="btn btn-ghost" onClick={() => unarchive({ id: f.id })} title="Open it again, with the steps archiving put away" style={{ fontSize: 12, padding: "3px 8px" }}>
                      <Icon name="arrow-u-up-left" size={13} /> Open again
                    </button>
                    <button className="btn btn-icon btn-ghost" onClick={() => setSure(f.id)} aria-label={`Delete ${f.title}`} title="Delete it" style={{ width: 28, height: 28, color: "var(--color-neutral-400)" }}>
                      <Icon name="trash" size={14} />
                    </button>
                  </>
                )}
              </span>
            </div>
          )
        })}
    </section>
  )
}
