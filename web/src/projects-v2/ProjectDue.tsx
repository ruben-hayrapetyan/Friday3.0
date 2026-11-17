// A project's due date and how firm it is, set on the project itself, at the top of its page (16 Nov: "the only way to
// add a due date to a project is through tasks which i find highly problematic"). Rows as To-do details has them: the
// value in words, a click opens the choices; a change shows at once.

import { useState } from "react"
import { useCommand } from "@/hooks/useCommand"
import { when } from "@/lib/format"
import { useShell } from "@/shell/ShellContext"
import { DuePicker } from "@/todo/Pickers"
import type { Project } from "./model"
import { Choices, Rows, SettingRow } from "./Rows"

const FIRM = [
  { value: "hard", label: "Hard", desc: "It has to be done by then" },
  { value: "soft", label: "Soft", desc: "Best done by then; it can run a little late" },
  { value: "none", label: "None", desc: "A date to aim for, nothing more" },
] as const

export function ProjectDue({ p }: { p: Project }) {
  const { today } = useShell()
  const [open, setOpen] = useState<"due" | "firm" | null>(null)
  const edit = useCommand("edit", {
    label: () => "Saved",
    optimistic: (client, input) =>
      client.setQueryData<Project[]>(["projects"], (list) =>
        list?.map((x) => (x.item.id === input.id ? { ...x, item: { ...x.item, ...(input.due !== undefined ? { due: input.due ?? null } : {}), ...(input.firmness ? { firmness: input.firmness } : {}) } } : x)),
      ),
  })
  const due = p.item.due ?? null
  const firm = FIRM.find((f) => f.value === p.item.firmness) ?? FIRM[1]
  const toggle = (k: "due" | "firm") => setOpen(open === k ? null : k)
  return (
    <section aria-label="When it's due" style={{ maxWidth: 760 }}>
      <Rows>
        <SettingRow label="Due" value={due ? when(due, today) : "No due date"} open={open === "due"} onToggle={() => toggle("due")} note={due ? undefined : "Friday plans its steps when there's room"}>
          <DuePicker value={due} today={today} onPick={(v) => (v !== due && edit({ id: p.item.id, due: v }), setOpen(null))} stacked autoFocus={false} />
        </SettingRow>
        {due && (
          <SettingRow label="How firm" value={`${firm.label}: ${firm.desc.toLowerCase()}`} open={open === "firm"} onToggle={() => toggle("firm")}>
            <Choices label="How firm" value={firm.value as string} onPick={(v: string) => (v !== firm.value && edit({ id: p.item.id, firmness: v as "hard" | "soft" | "none" }), setOpen(null))} options={FIRM.map((f) => ({ value: f.value as string, label: f.label, desc: f.desc }))} />
          </SettingRow>
        )}
      </Rows>
    </section>
  )
}
