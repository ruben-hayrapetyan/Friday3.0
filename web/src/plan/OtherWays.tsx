// Other ways (personal's options, COMBINED.md 25): on demand, two more ways to plan the same work, each a card with
// how it differs, its hours and sittings, anything late, and the next seven days at a glance. Preview lays one over
// the calendar, dashed; Pick makes it your plan, and Friday learns from the pick.

import { useQuery, useQueryClient } from "@tanstack/react-query"
import { query, type Schemas } from "@/api/client"
import { setGhosts } from "@/api/events"
import { Icon } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { addDays, toMin } from "@/lib/time"
import { weekday } from "@/lib/format"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"

type Way = Schemas["OtherWay"]

export function OtherWaysDialog({ onClose }: { onClose: () => void }) {
  // Two plans made afresh on the server: a few seconds.
  const found = useQuery({ queryKey: ["other_ways"], queryFn: () => query("other_ways"), staleTime: 0, gcTime: 0 })
  const { setWay } = useShell()
  const client = useQueryClient()
  const pick = usePick(onClose)
  const ways = found.data?.ways ?? []
  return (
    <div className="fr-scrim" style={{ alignItems: "flex-start", padding: "56px 24px 24px" }}>
      <div onClick={onClose} style={{ position: "absolute", inset: 0 }} />
      <div role="dialog" aria-modal="true" aria-label="Other ways" className="fr-float fr-dialog" style={{ width: "min(900px, 100%)" }}>
        <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="fr-h" style={{ fontSize: 26, lineHeight: 1.05 }}>
              Other ways
            </span>
            <span style={{ color: "var(--color-neutral-400)" }}>
              {found.isLoading ? "Planning your week two more ways…" : ways.length ? "The same work, planned differently. Preview one on the calendar, or pick it." : "Nothing much else would change: your plan is the way it fits."}
            </span>
          </div>
          <button className="btn btn-icon btn-ghost" onClick={onClose} aria-label="Close" style={{ width: 28, height: 28 }}>
            <Icon name="x" />
          </button>
        </div>
        {found.error && <span style={{ color: "var(--fr-due)" }}>{found.error.message}</span>}
        <div style={{ display: "grid", gridTemplateColumns: `repeat(${Math.max(1, ways.length)}, minmax(0,1fr))`, gap: 12 }}>
          {ways.map((w, i) => (
            <WayCard
              key={w.seed}
              way={w}
              n={i + 1}
              onPreview={() => {
                setGhosts(client, w.blocks)
                setWay(w)
                onClose()
              }}
              onPick={() => pick(w)}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

function usePick(after: () => void) {
  const { setWay } = useShell()
  const client = useQueryClient()
  const run = useCommand("other_way_pick", { label: (o) => o.result.message })
  return async (w: Way) => {
    const out = await run({ weights: w.weights, seed: w.seed, rule_totals: w.rule_totals })
    if (!out) return
    setGhosts(client, w.blocks) // shown until the plan it makes arrives
    setWay(null)
    after()
  }
}

function WayCard({ way, n, onPreview, onPick }: { way: Way; n: number; onPreview: () => void; onPick: () => void }) {
  const late = Object.entries(way.late)
  return (
    <div className="fr-well" style={{ display: "flex", flexDirection: "column", gap: 10, padding: 14, borderRadius: "var(--radius-lg)" }}>
      <span className="fr-eyebrow">Way {n}</span>
      <span style={{ textWrap: "pretty", minHeight: 38 }}>{way.summary}</span>
      <div className="tnum" style={{ display: "flex", gap: 6, flexWrap: "wrap", fontSize: 12 }}>
        <span className="fr-tag">{way.hours} h</span>
        <span className="fr-tag">{way.sessions} sittings</span>
        {late.length ? <span className="fr-tag due">{late.length} late</span> : <span className="fr-tag">nothing late</span>}
      </div>
      <WeekStrip blocks={way.blocks} />
      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn btn-secondary" onClick={onPreview}>
          <Icon name="eye" />
          Preview
        </button>
        <button className="btn btn-primary" onClick={onPick}>
          <Icon name="check" />
          Pick this
        </button>
      </div>
    </div>
  )
}

/** The next seven days, 08:00 to midnight: each block a bar in its tag's colour. */
function WeekStrip({ blocks }: { blocks: Schemas["BlockOut"][] }) {
  const { today } = useShell()
  const { color } = useLook()
  const days = Array.from({ length: 7 }, (_, i) => addDays(today, i))
  const top = 8 * 60
  const span = 16 * 60
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(7, minmax(0,1fr))", gap: 3 }} aria-label="The next seven days">
      {days.map((d) => (
        <div key={d} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <span className="fr-eyebrow" style={{ fontSize: 8.5, letterSpacing: "0.06em", textAlign: "center" }}>
            {weekday(d).slice(0, 2)}
          </span>
          <div style={{ position: "relative", height: 70, borderRadius: 3, background: "color-mix(in srgb, var(--color-text) 5%, transparent)" }}>
            {blocks
              .filter((b) => b.start.startsWith(d))
              .map((b) => {
                const from = toMin(b.start) - toMin(d) - top
                const len = toMin(b.end) - toMin(b.start)
                return (
                  <span
                    key={b.key}
                    title={`${b.title} ${b.start.slice(11, 16)}–${b.end.slice(11, 16)}`}
                    style={{ position: "absolute", left: 2, right: 2, top: `${Math.max(0, (from / span) * 100)}%`, height: `${Math.max(2, (len / span) * 100)}%`, borderRadius: 2, background: color(b.area) }}
                  />
                )
              })}
          </div>
        </div>
      ))}
    </div>
  )
}

/** While a way is laid over the calendar: what it is, Pick this, or back to the options. */
export function WayBanner() {
  const { way, setWay, setDialog } = useShell()
  const client = useQueryClient()
  const pick = usePick(() => undefined)
  if (!way) return null
  const back = () => {
    setGhosts(client, [])
    setWay(null)
  }
  return (
    <div className="fr-float" role="status" style={{ position: "absolute", top: 66, left: "50%", transform: "translateX(-50%)", zIndex: 8, display: "flex", gap: 10, alignItems: "center", padding: "8px 12px" }}>
      <span className="fr-eyebrow">Previewing</span>
      <span style={{ maxWidth: 420, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{way.summary}</span>
      <button className="btn btn-primary" onClick={() => pick(way)}>
        Pick this
      </button>
      <button className="btn btn-secondary" onClick={() => (back(), setDialog("ways"))}>
        Back to the options
      </button>
      <button className="btn btn-icon btn-ghost" onClick={back} aria-label="Stop previewing" style={{ width: 26, height: 26 }}>
        <Icon name="x" />
      </button>
    </div>
  )
}
