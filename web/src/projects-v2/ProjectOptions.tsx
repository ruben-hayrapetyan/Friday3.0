// A project's options, under its steps in its popup: how many days early it aims to finish (a rule of yours about it, in Rules), and its pace through the work. Each says
// what it's set to now; a change shows at once. No notes here (16 Nov: "it is unclear what Notes is for"; you chose to
// remove them from projects).

import { type QueryClient, useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { query, type Schemas } from "@/api/client"
import { H } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { dur, weekday } from "@/lib/format"
import { aimFor, EARLY_DAYS, PACES, type Project } from "./model"
import { Choices, Rows, SettingRow } from "./Rows"

type Options = Schemas["ProjectOptionsOut"]
export const OPTIONS_KEY = ["project_options"] as const
export const useProjectOptions = () => useQuery({ queryKey: OPTIONS_KEY, queryFn: () => query("project_options") })

/** A description as a sentence: its first letter a capital (a client: "the text explanation at the bottom needs a capital at
 * the start of the sentence"). */
export const sentence = (text: string) => text.charAt(0).toUpperCase() + text.slice(1)

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
  const [open, setOpen] = useState<"early" | "pace" | null>(null)
  const due = p.item.due
  const total = p.done_min + p.remaining_min
  const pace = PACES.find((x) => x.value === pacing) ?? PACES[0]
  const aim = due && early ? aimFor(due, early) : null
  return (
    <section aria-label="Options" style={{ display: "flex", flexDirection: "column", gap: 18, maxWidth: 760 }}>
      <H size={20}>Options</H>
      <Rows>
        <SettingRow label="Finish early" value={aim ? `${early} ${early === 1 ? "day" : "days"} early, by ${weekday(aim.slice(0, 10))} ${Number(aim.slice(8, 10))}` : due ? "No: it can take until its due" : "It has no due date"} open={open === "early"} onToggle={() => setOpen(open === "early" ? null : "early")} note={aim ? "A rule you'll find in Rules" : undefined}>
          <Choices
            label="Finish early"
            value={early}
            onPick={(d: number) => (d !== early && set({ id: p.item.id, early_days: d }), setOpen(null))}
            options={EARLY_DAYS.map((d) => {
              const by = due && d ? aimFor(due, d) : null
              return { value: d, label: d ? `${d} ${d === 1 ? "day" : "days"} early` : "No", desc: d ? `Aim to be done by ${by ? `${weekday(by.slice(0, 10))} ${Number(by.slice(8, 10))}` : "then"}, leaving room before it's due` : "It can take until its due" }
            })}
          />
        </SettingRow>
        <SettingRow label="Pace" value={pace.label} open={open === "pace"} onToggle={() => setOpen(open === "pace" ? null : "pace")} note={`${sentence(pace.desc)}${total ? ` (${dur(total)} in all)` : ""}. Shows on projects due more than two weeks off.`}>
          <Choices label="Pace" value={pacing} onPick={(v: string) => (v !== pacing && set({ id: p.item.id, pacing: v as "front" | "linear" | "back" | "kind" }), setOpen(null))} options={PACES.map((x) => ({ value: x.value as string, label: x.label, desc: sentence(x.desc) }))} />
        </SettingRow>
      </Rows>
    </section>
  )
}
