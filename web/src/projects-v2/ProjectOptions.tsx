// A project's notes and options, under its page on the new layout: its Notes (the same text as in its To-do details),
// how many days early it aims to finish (a rule of yours about it, in Rules), and its pace through the work. Each says
// what it's set to now; a change shows at once.

import { type QueryClient, useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { query, type Schemas } from "@/api/client"
import { H, Seg } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { dur, weekday } from "@/lib/format"
import { aimFor, EARLY_DAYS, PACES, type Project } from "./model"

type Options = Schemas["ProjectOptionsOut"]
export const OPTIONS_KEY = ["project_options"] as const
export const useProjectOptions = () => useQuery({ queryKey: OPTIONS_KEY, queryFn: () => query("project_options") })

/** Each project's days early, by id, for the bars' dotted lines. */
export const earlyDays = (all: Options[]) => Object.fromEntries(all.map((o) => [o.id, o.early_days]))

function changed(client: QueryClient, id: number, change: Partial<Options>): void {
  client.setQueryData<Options[]>(OPTIONS_KEY, (list) => {
    const was = list?.find((o) => o.id === id) ?? { id, pacing: null, early_days: 0 }
    return [...(list ?? []).filter((o) => o.id !== id), { ...was, ...change }]
  })
}

export function ProjectOptions({ p }: { p: Project }) {
  const mine = (useProjectOptions().data ?? []).find((o) => o.id === p.item.id)
  const pacing = mine?.pacing ?? "kind"
  const early = mine?.early_days ?? 0
  const set = useCommand("project_set", {
    label: (o) => o.result.message,
    optimistic: (client, input) =>
      changed(client, input.id, { ...(input.pacing != null ? { pacing: input.pacing === "kind" ? null : input.pacing } : {}), ...(input.early_days != null ? { early_days: input.early_days } : {}) }),
  })
  const edit = useCommand("edit", {
    label: () => "Notes saved",
    optimistic: (client, input) => client.setQueryData<Project[]>(["projects"], (list) => list?.map((x) => (x.item.id === input.id ? { ...x, item: { ...x.item, notes: input.notes ?? "" } } : x))),
  })
  const [notes, setNotes] = useState(p.item.notes ?? "")
  const saveNotes = () => notes !== (p.item.notes ?? "") && edit({ id: p.item.id, notes })
  const due = p.item.due
  const total = p.done_min + p.remaining_min
  const pace = PACES.find((x) => x.value === pacing) ?? PACES[0]
  const aim = due && early ? aimFor(due, early) : null
  return (
    <section aria-label="Notes and options" style={{ display: "flex", flexDirection: "column", gap: 18, maxWidth: 760, paddingTop: 12 }}>
      <H size={20}>Notes and options</H>
      <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <span style={{ fontWeight: 500, fontSize: 13 }}>Notes</span>
        <textarea className="input" value={notes} onChange={(e) => setNotes(e.target.value)} onBlur={saveNotes} rows={4} placeholder="Anything to keep with it: sources, what the teacher said, ideas" aria-label="Notes" style={{ resize: "vertical", font: "inherit", fontSize: 13 }} />
        <span className="fr-kicker">The same notes as in its To-do details; the first lines show beside its name on the shelf.</span>
      </label>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <span style={{ fontWeight: 500, fontSize: 13 }}>Finish early</span>
          <span style={{ fontSize: 12, color: "var(--color-neutral-300)", textWrap: "pretty" }}>
            {aim ? `${early} ${early === 1 ? "day" : "days"} early: done by ${weekday(aim.slice(0, 10))} ${Number(aim.slice(8, 10))}, a rule you'll find in Rules` : due ? "No: it can take until its due" : "It has no due date"}
          </span>
        </span>
        <Seg options={EARLY_DAYS.map((d) => ({ value: d, label: d ? `${d} ${d === 1 ? "day" : "days"}` : "No" }))} value={early} onPick={(d) => d !== early && set({ id: p.item.id, early_days: d })} size="small" label="Days early" />
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <span style={{ fontWeight: 500, fontSize: 13 }}>Pace through the work</span>
          <span style={{ fontSize: 12, color: "var(--color-neutral-300)", textWrap: "pretty" }}>
            {pace.label}: {pace.desc}
            {total ? ` (${dur(total)} in all)` : ""}. It shows on projects due more than two weeks off.
          </span>
        </span>
        <Seg options={PACES.map((x) => ({ value: x.value as string, label: x.label }))} value={pacing} onPick={(v) => v !== pacing && set({ id: p.item.id, pacing: v as "front" | "linear" | "back" | "kind" })} size="small" label="Pace" />
      </div>
    </section>
  )
}
