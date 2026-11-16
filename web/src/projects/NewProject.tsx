// A new project (v22): a name, a template's steps (or none), a tag, a due date and about how long it all takes.
// Escape or a click outside closes it.

import { useEffect, useRef, useState } from "react"
import { Chip, H, Icon } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useAreas, useSettings } from "@/hooks/queries"
import { addDays } from "@/lib/time"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"
import { DuePicker, LengthField } from "@/todo/Pickers"

const ICONS: Record<string, string> = { Essay: "article", Presentation: "presentation-chart" }
// Friday's own (core/settings.py DEFAULT_TEMPLATES): they stay; only the ones you saved can be removed (15 Nov)
const BUILT_IN = ["Essay", "Presentation"]

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
  const [minutes, setMinutes] = useState(360) // about how long in all: typed, or an hour at a time
  // Caught before the fields see it: the due field keeps Escape to itself.
  useEffect(() => {
    const escape = (e: KeyboardEvent) => e.key === "Escape" && onClose()
    window.addEventListener("keydown", escape, true)
    return () => window.removeEventListener("keydown", escape, true)
  }, [onClose])
  const apply = useCommand("template_apply", { label: () => "Project made" })
  // Settings' templates without it, shown gone at once; the toast's Undo brings it back (15 Nov, a client)
  const removing = useRef("")
  const forget = useCommand("settings_set", { label: () => `Template ${removing.current} removed` })
  const remove = (name: string) => {
    removing.current = name
    if (template === name) setTemplate(Object.keys(templates).find((t) => t !== name) ?? null)
    forget({ key: "templates", value: Object.fromEntries(Object.entries(templates).filter(([t]) => t !== name)) })
  }
  const add = useCommand("add", { label: () => "Project made" })
  // Once: a second click while the first is on its way made the project twice (audit, 12 Nov).
  const sending = useRef(false)
  const [busy, setBusy] = useState(false)
  const create = async () => {
    if (sending.current) return
    sending.current = true
    setBusy(true)
    try {
      const out = template
        ? await apply({ template, title, hours: minutes / 60, due, area })
        : await add({ title, preset: "Project", due, area, duration_min: minutes })
      if (out) onClose(out.result.item?.id)
    } finally {
      sending.current = false
      setBusy(false)
    }
  }
  return (
    <div className="fr-scrim">
      <div onClick={() => onClose()} style={{ position: "absolute", inset: 0 }} />
      <div role="dialog" aria-modal="true" className="fr-float fr-dialog" style={{ width: "min(640px, 100%)" }}>
        <H size={26}>New project</H>
        <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Name, e.g. History essay" style={{ fontSize: 15 }} autoFocus />
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0,1fr))", gap: 8 }}>
          {[...Object.keys(templates), null].map((t) => (
            <div key={t ?? "blank"} style={{ position: "relative", display: "flex", minWidth: 0 }}>
              <button
                onClick={() => setTemplate(t)}
                className="fr-plain"
                style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 4, padding: 12, paddingRight: t && !BUILT_IN.includes(t) ? 34 : 12, borderRadius: "var(--radius-md)", background: t === template ? "color-mix(in srgb, var(--color-accent) 12%, var(--color-bg))" : "var(--color-bg)", boxShadow: t === template ? "inset 0 0 0 1px var(--color-accent-500)" : "0 0 0 1px color-mix(in srgb, var(--color-text) 7%, transparent)" }}
              >
                <span style={{ display: "flex", gap: 8, alignItems: "center", fontWeight: 500, overflowWrap: "anywhere" }}>
                  <Icon name={t ? (ICONS[t] ?? "list-numbers") : "square"} size={16} style={{ color: "var(--color-accent-300)" }} />
                  {t ?? "Blank"}
                </span>
                <span style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>{t ? templates[t].map((s) => s.title).join(", then ") : "Add your own steps"}</span>
              </button>
              {t && !BUILT_IN.includes(t) && (
                <button className="fr-plain" onClick={() => remove(t)} aria-label={`Remove template ${t}`} title="Remove this template; projects made from it stay" style={{ position: "absolute", top: 8, right: 8, padding: 4, color: "var(--color-neutral-500)" }}>
                  <Icon name="x" size={13} />
                </button>
              )}
            </div>
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
          {/* a value that opens common amounts and a box to type any (16 Nov) */}
          <LengthField value={minutes} onPick={(m) => m && setMinutes(m)} label="About how long, in all" amounts={[120, 360, 600, 1200, 2400, 6000]} />
          <span className="fr-kicker">Friday splits it across the steps; change any step after.</span>
        </div>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button className="btn btn-ghost" onClick={() => onClose()}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={create} disabled={!title.trim() || busy}>
            Create project
          </button>
        </div>
      </div>
    </div>
  )
}
