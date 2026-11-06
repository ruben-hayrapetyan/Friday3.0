// A new project (v22): a name, a template's steps (or none), a tag, a due date and about how long it all takes.
// Escape or a click outside closes it.

import { useEffect, useState } from "react"
import { Chip, H, Icon } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useAreas, useSettings } from "@/hooks/queries"
import { dur } from "@/lib/format"
import { addDays } from "@/lib/time"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"
import { DuePicker } from "@/todo/Pickers"

const ICONS: Record<string, string> = { Essay: "article", Presentation: "presentation-chart" }

export function NewProject({ onClose }: { onClose: (id?: number) => void }) {
  const { today } = useShell()
  const { color } = useLook()
  const settings = useSettings().data as Record<string, unknown> | undefined
  const templates = (settings?.templates as Record<string, { title: string }[]>) ?? {}
  const areas = (useAreas().data ?? []).filter((a) => !a.archived).map((a) => a.name)
  const [title, setTitle] = useState("")
  const [template, setTemplate] = useState<string | null>(Object.keys(templates)[0] ?? null)
  const [area, setArea] = useState<string | null>(null)
  const [due, setDue] = useState<string | null>(`${addDays(today, 7)}T23:59`)
  const [hours, setHours] = useState(6)
  // Caught before the fields see it: the due field keeps Escape to itself.
  useEffect(() => {
    const escape = (e: KeyboardEvent) => e.key === "Escape" && onClose()
    window.addEventListener("keydown", escape, true)
    return () => window.removeEventListener("keydown", escape, true)
  }, [onClose])
  const apply = useCommand("template_apply", { label: () => "Project made" })
  const add = useCommand("add", { label: () => "Project made" })
  const create = async () => {
    const out = template
      ? await apply({ template, title, hours, due, area })
      : await add({ title, preset: "Project", due, area, duration_min: hours * 60 })
    if (out) onClose(out.result.item?.id)
  }
  return (
    <div className="fr-scrim">
      <div onClick={() => onClose()} style={{ position: "absolute", inset: 0 }} />
      <div role="dialog" aria-modal="true" className="fr-float fr-dialog" style={{ width: "min(640px, 100%)" }}>
        <H size={26}>New project</H>
        <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Name, e.g. History essay" style={{ fontSize: 15 }} autoFocus />
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0,1fr))", gap: 8 }}>
          {[...Object.keys(templates), null].map((t) => (
            <button
              key={t ?? "blank"}
              onClick={() => setTemplate(t)}
              className="fr-plain"
              style={{ display: "flex", flexDirection: "column", gap: 4, padding: 12, borderRadius: "var(--radius-md)", background: t === template ? "color-mix(in srgb, var(--color-accent) 12%, var(--color-bg))" : "var(--color-bg)", boxShadow: t === template ? "inset 0 0 0 1px var(--color-accent-500)" : "0 0 0 1px color-mix(in srgb, var(--color-text) 7%, transparent)" }}
            >
              <span style={{ display: "flex", gap: 8, alignItems: "center", fontWeight: 500 }}>
                <Icon name={t ? (ICONS[t] ?? "list-numbers") : "square"} size={16} style={{ color: "var(--color-accent-300)" }} />
                {t ?? "Blank"}
              </span>
              <span style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>{t ? templates[t].map((s) => s.title).join(", then ") : "Add your own steps"}</span>
            </button>
          ))}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <span className="fr-kicker">Tag</span>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            <Chip on={area === null} onClick={() => setArea(null)}>
              No tag
            </Chip>
            {areas.map((a) => (
              <Chip key={a} on={area === a} swatch={color(a)} onClick={() => setArea(a)}>
                {a}
              </Chip>
            ))}
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <span className="fr-kicker">Due</span>
          <DuePicker value={due} today={today} onPick={setDue} autoFocus={false} />
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span className="fr-kicker" style={{ width: 120 }}>
            About how long, in all
          </span>
          <button className="btn btn-icon btn-secondary" onClick={() => setHours(Math.max(1, hours - 1))} aria-label="Less" style={{ width: 26, height: 26 }}>
            <Icon name="minus" />
          </button>
          <span className="tnum" style={{ width: 56, flex: "none", whiteSpace: "nowrap", textAlign: "center" }}>
            {dur(hours * 60)}
          </span>
          <button className="btn btn-icon btn-secondary" onClick={() => setHours(hours + 1)} aria-label="More" style={{ width: 26, height: 26 }}>
            <Icon name="plus" />
          </button>
          <span className="fr-kicker">Friday splits it across the steps; change any step after.</span>
        </div>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button className="btn btn-ghost" onClick={() => onClose()}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={create} disabled={!title.trim()}>
            Create project
          </button>
        </div>
      </div>
    </div>
  )
}
