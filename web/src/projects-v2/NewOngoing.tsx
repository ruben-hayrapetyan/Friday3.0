// New ongoing project, as New project asks: a name, a tag, and hours a week (− and +, as New project's length).
// Rhythm, carry-over, priority and pause are on its own page once it's made.

import { useRef, useState } from "react"
import { Chip, H, Icon } from "@/components/fr/controls"
import { useAreas } from "@/hooks/queries"
import { useCommand } from "@/hooks/useCommand"
import { useLook } from "@/theme/LookProvider"
import { hoursText } from "./model"

export function NewOngoing({ onClose }: { onClose: (id?: number) => void }) {
  const { color } = useLook()
  const areas = (useAreas().data ?? []).filter((a) => !a.archived).map((a) => a.name)
  const [title, setTitle] = useState("")
  const [area, setArea] = useState<string | null>(null)
  const [hours, setHours] = useState(3)
  const add = useCommand("ongoing_add", { label: () => "Ongoing project made; Friday finds it time each week" })
  const sending = useRef(false) // a second click while the first is on its way makes it once
  const [busy, setBusy] = useState(false)
  const create = async () => {
    if (sending.current || !title.trim()) return
    sending.current = true
    setBusy(true)
    try {
      const out = await add({ title: title.trim(), hours_per_week: hours, area })
      if (out) onClose((out.result as { id: number }).id)
    } finally {
      sending.current = false
      setBusy(false)
    }
  }
  const step = hours < 2 ? 0.5 : 1
  return (
    <div className="fr-scrim">
      <div onClick={() => onClose()} style={{ position: "absolute", inset: 0 }} />
      <div role="dialog" aria-modal="true" aria-label="New ongoing project" className="fr-float fr-dialog" style={{ width: "min(560px, 100%)" }}>
        <H size={26}>New ongoing project</H>
        <span className="fr-kicker" style={{ marginTop: -6 }}>
          Hours a week with no deadline, like a language, an instrument or reading.
        </span>
        <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} onKeyDown={(e) => e.key === "Enter" && create()} placeholder="Name, e.g. Guitar practice" aria-label="Name" style={{ fontSize: 15 }} autoFocus />
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
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span className="fr-kicker" style={{ width: 120 }}>
            Hours a week
          </span>
          <button className="btn btn-icon btn-secondary" onClick={() => setHours(Math.max(0.5, hours - step))} aria-label="Fewer hours" style={{ width: 26, height: 26 }}>
            <Icon name="minus" />
          </button>
          <span className="tnum" style={{ width: 56, flex: "none", whiteSpace: "nowrap", textAlign: "center" }}>
            {hoursText(hours)}
          </span>
          <button className="btn btn-icon btn-secondary" onClick={() => setHours(Math.min(60, hours + step))} aria-label="More hours" style={{ width: 26, height: 26 }}>
            <Icon name="plus" />
          </button>
          <span className="fr-kicker">From this week; this week's rest counts as part of a week.</span>
        </div>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button className="btn btn-ghost" onClick={() => onClose()}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={create} disabled={!title.trim() || busy}>
            Create ongoing project
          </button>
        </div>
      </div>
    </div>
  )
}
