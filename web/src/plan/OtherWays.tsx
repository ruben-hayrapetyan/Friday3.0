// Other ways (personal's options, COMBINED.md 25): on demand, two more ways to plan the same work, each a card with
// how it differs, its hours and sittings, anything late, and the next seven days at a glance. Preview lays one over
// the calendar, dashed; Pick makes it your plan, and Friday learns from the pick. Each takes about half a minute to
// plan, so each card shows as it comes, with its progress, and the window can close meanwhile (./finding.ts).

import { useEffect, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import type { Schemas } from "@/api/client"
import { setGhosts } from "@/api/events"
import { Icon } from "@/components/fr/controls"
import { useToast } from "@/components/Toasts"
import { useDialogKeys } from "@/dialogs/Dialogs"
import { useCommand } from "@/hooks/useCommand"
import { addDays, toMin } from "@/lib/time"
import { clock, weekday } from "@/lib/format"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"
import { finding, heading, type Slot, slots, stale, useFinding } from "./finding"

type Way = Schemas["OtherWay"]

export function OtherWaysDialog({ onClose }: { onClose: () => void }) {
  const f = useFinding()
  const now = useTicking(f?.state === "planning")
  const { setWay, setDialog } = useShell()
  const client = useQueryClient()
  const toast = useToast()
  const pick = usePick(onClose)
  const box = useDialogKeys(onClose)
  const plan = () =>
    void finding.start((done) =>
      toast({ message: done.ways.length ? `${done.ways.length === 1 ? "Another way" : "Two other ways"} to plan your week ${done.ways.length === 1 ? "is" : "are"} ready` : "No other way would change much", action: done.ways.length ? { label: "See them", run: () => setDialog("ways") } : undefined }),
    )
  useEffect(() => {
    finding.open(true)
    // Ways found in the last few minutes are shown again (Back to the options), not planned again.
    if (stale(finding.get(), Date.now())) plan()
    return () => void finding.open(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const said = heading(f, now)
  const planning = !f || f.state === "planning"
  return (
    <div className="fr-scrim" style={{ alignItems: "flex-start", padding: "56px 24px 24px" }}>
      <div onClick={onClose} style={{ position: "absolute", inset: 0 }} />
      <div ref={box} tabIndex={-1} role="dialog" aria-modal="true" aria-label="Other ways" className="fr-float fr-dialog" style={{ width: "min(900px, 100%)", outline: "none" }}>
        <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="fr-h" style={{ fontSize: 26, lineHeight: 1.05 }}>
              Other ways
            </span>
            <span role="status" style={{ color: f?.state === "failed" ? "var(--fr-due)" : "var(--color-neutral-400)" }}>
              {said.line}
            </span>
            {said.note && <span style={{ color: "var(--color-neutral-400)", fontSize: 13 }}>{said.note}</span>}
          </div>
          {planning ? (
            <button className="btn btn-secondary" onClick={() => finding.stop()} title="Stop planning; the ways found so far stay">
              Stop
            </button>
          ) : (
            <button className="btn btn-secondary" onClick={plan} title="Plan two other ways afresh">
              <Icon name="arrow-clockwise" />
              Plan again
            </button>
          )}
          <button className="btn btn-icon btn-ghost" onClick={onClose} aria-label="Close" style={{ width: 28, height: 28 }}>
            <Icon name="x" />
          </button>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: `repeat(${f?.wanted ?? 2}, minmax(0,1fr))`, gap: 12 }}>
          {(f ? slots(f, now) : [{ line: "Planning way 1… 0s", share: null }, { line: "Next", share: null }]).map((slot, i) =>
            slot.way ? (
              <WayCard
                key={slot.way.seed}
                way={slot.way}
                n={i + 1}
                onPreview={() => {
                  setGhosts(client, slot.way!.blocks)
                  setWay(slot.way!)
                  onClose()
                }}
                onPick={() => pick(slot.way!)}
              />
            ) : f && f.state !== "planning" && !f.ways.length ? null : (
              <Planning key={`slot${i}`} n={i + 1} slot={slot} />
            ),
          )}
        </div>
      </div>
    </div>
  )
}

/** A way still being planned: what it's doing, and a bar against how long the last way took (moving stripes when
 * Friday can't say yet). Its place is the card's, so the card that comes takes it without the dialog jumping. */
function Planning({ n, slot }: { n: number; slot: Slot }) {
  return (
    <div className="fr-well" data-testid="way-planning" style={{ display: "flex", flexDirection: "column", gap: 10, padding: 14, borderRadius: "var(--radius-lg)", minHeight: 214 }}>
      <span className="fr-eyebrow">Way {n}</span>
      <span className="tnum" style={{ color: "var(--color-neutral-400)" }}>
        {slot.line}
      </span>
      {slot.line !== "Next" && slot.line !== "Not planned" && (
        <div role="progressbar" aria-label={`Way ${n}`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={slot.share === null ? undefined : Math.round(slot.share * 100)} style={{ height: 6, borderRadius: 3, overflow: "hidden", background: "color-mix(in srgb, var(--color-text) 8%, transparent)" }}>
          <div className={slot.share === null ? "fr-progress" : undefined} style={{ height: "100%", width: slot.share === null ? "40%" : `${Math.round(slot.share * 100)}%`, background: "var(--color-accent-300)", borderRadius: 3, transition: "width 0.25s linear" }} />
        </div>
      )}
    </div>
  )
}

/** Now, every quarter second while `on`: the seconds counting and the bar filling. */
function useTicking(on: boolean): number {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    if (!on) return
    const timer = setInterval(() => setNow(Date.now()), 250)
    return () => clearInterval(timer)
  }, [on])
  return on ? now : Date.now()
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
          <span className="fr-eyebrow" style={{ fontSize: 11.5, letterSpacing: "0.06em", textAlign: "center" }}>
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
                    title={`${b.title} ${clock(b.start)}–${clock(b.end)}`}
                    style={{ position: "absolute", left: 2, right: 2, top: `${Math.max(0, (from / span) * 100)}%`, height: `${Math.max(2, (len / span) * 100)}%`, borderRadius: 2, background: color(b.area, b.preset) }}
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
