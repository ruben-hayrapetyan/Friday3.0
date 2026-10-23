// Pace (v22): how hard Friday pushes for a while. Pick a saved pace and how long; a full solve previews what changes
// before you apply it. Deadlines hold whatever you pick.

import { useState } from "react"
import type { Schemas } from "@/api/client"
import { Icon } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { usePaces } from "@/hooks/queries"
import { usePreview } from "@/hooks/usePreview"
import { lines, summary } from "@/lib/changes"
import { useShell } from "@/shell/ShellContext"

type For = Pick<Schemas["PaceInput"], "for_days" | "until">
const DURATIONS: [string, For][] = [
  ["Today", { for_days: 1 }],
  ["3 days", { for_days: 3 }],
  ["Until Sunday", { until: "sun" }],
  ["Until I change it", {}],
]
const HINTS: Record<string, string> = {
  Normal: "Your usual week.",
  Easy: "Sick or tired. Lighter days, side projects pause.",
  Push: "Motivated. Fuller days, more growth.",
}

export function PacePop() {
  const { today, setPop } = useShell()
  const paces = usePaces().data
  const [name, setName] = useState<string | null>(null)
  const [duration, setDuration] = useState(1)
  const apply = useCommand("pace", { label: (o) => o.result.message })
  const input = name ? { name, ...DURATIONS[duration][1] } : null
  const preview = usePreview("pace", input)
  if (!paces) return null
  const shown = name ?? paces.now_label
  const changes = preview.changes
  return (
    <div className="fr-float" style={{ position: "absolute", right: 12, top: 56, width: "min(360px, calc(100vw - 24px))", zIndex: 10, padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
      <div>
        <div className="fr-h" style={{ fontSize: 22 }}>
          Pace
        </div>
        <div style={{ color: "var(--color-neutral-400)" }}>How hard Friday pushes for a while. Deadlines hold whatever you pick.</div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${Math.min(3, Object.keys(paces.paces).length)},1fr)`, gap: 6 }}>
        {Object.keys(paces.paces).map((p) =>
          p === shown ? (
            <button
              key={p}
              className="btn btn-primary"
              onClick={() => setName(p)}
              style={{ background: "color-mix(in srgb, var(--color-accent) 16%, transparent)", boxShadow: "0 0 calc(16px * var(--g-accent)) color-mix(in srgb, var(--color-accent) 30%, transparent)" }}
            >
              {p}
            </button>
          ) : (
            <button key={p} className="btn btn-secondary" onClick={() => setName(p)}>
              {p}
            </button>
          ),
        )}
      </div>
      <div style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>{HINTS[shown] ?? "A pace you saved."}</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
        {DURATIONS.map(([text], i) => (
          <button
            key={text}
            className="fr-plain fr-hover-text"
            onClick={() => setDuration(i)}
            style={{ fontSize: 12, padding: "4px 10px", borderRadius: 6, background: duration === i ? "var(--color-neutral-800)" : undefined, color: duration === i ? "var(--color-text)" : "var(--color-neutral-400)" }}
          >
            {text}
          </button>
        ))}
      </div>
      <div style={{ minHeight: 64, padding: "10px 12px", borderRadius: "var(--radius-md)", background: "var(--color-bg)", display: "flex", flexDirection: "column", gap: 4 }}>
        {!input && <div style={{ color: "var(--color-neutral-500)" }}>Pick a pace to preview what changes.</div>}
        {input && preview.busy && <div style={{ color: "var(--color-accent-300)" }}>Working out the next two weeks…</div>}
        {input && !preview.busy && changes && (
          <>
            <Line text={summary(changes)} />
            {lines(changes, today)
              .slice(0, 4)
              .map((l) => (
                <Line key={l.title} text={`${l.title}: ${l.text}`} />
              ))}
          </>
        )}
        {preview.error && <div style={{ color: "var(--fr-due)" }}>{preview.error.message}</div>}
      </div>
      <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
        <button className="btn btn-ghost" onClick={() => setPop(null)}>
          Cancel
        </button>
        <button className="btn btn-primary" disabled={!input || preview.busy} onClick={async () => input && (await apply(input)) && setPop(null)}>
          Apply pace
        </button>
      </div>
    </div>
  )
}

function Line({ text }: { text: string }) {
  return (
    <div style={{ display: "flex", gap: 8 }}>
      <Icon name="check" style={{ color: "var(--color-accent-300)", marginTop: 3 }} />
      {text}
    </div>
  )
}
