// Shove (v22): take time back. Quick picks, "for N hours", "until", or a slice of tomorrow. When clearing it would
// make work late, the must-dos are listed and you choose.

import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import type { Schemas } from "@/api/client"
import { Icon } from "@/components/fr/controls"
import { useToast } from "@/components/Toasts"
import { runCommand } from "@/hooks/useCommand"
import { useClock } from "@/hooks/useClock"
import { weekday } from "@/lib/format"
import { addDays, fromMin } from "@/lib/time"
import { useShell } from "@/shell/ShellContext"

type Decision = "ask" | "shove_anyway" | "keep_must_dos"

export function ShovePop() {
  const { today, setPop } = useShell()
  const client = useQueryClient()
  const toast = useToast()
  const now = useClock()
  const [hours, setHours] = useState(1)
  const [until, setUntil] = useState("17:00")
  const [mustDo, setMustDo] = useState<{ range: string; list: Schemas["MustDo"][] } | null>(null)
  const nowClock = fromMin(now).slice(11, 16)
  const shove = async (range: string, decision: Decision = "ask") => {
    const out = await runCommand(client, toast, "shove", { range, decision }, { label: (o) => o.result.message ?? "Shoved" })
    const list = out?.result.must_do ?? []
    if (out && !out.result.created?.length && list.length) setMustDo({ range, list })
    else if (out) setPop(null)
  }
  const tomorrow = addDays(today, 1)
  const day = weekday(tomorrow).toLowerCase()
  const quick = [
    { label: "Next hour", sub: `${nowClock}–${fromMin(now + 60).slice(11, 16)}`, range: "1h" },
    { label: "Rest of today", sub: `from ${nowClock}`, range: "rest" },
    ...(nowClock < "19:00" ? [{ label: "Tonight", sub: "19:00–23:00", range: "19:00-23:00" }] : []),
  ]
  const tmr = [
    { label: "Morning", sub: "08:00–12:00", range: `08:00-12:00 ${day}` },
    { label: "Afternoon", sub: "12:00–17:00", range: `12:00-17:00 ${day}` },
    { label: "Evening", sub: "17:00–22:00", range: `17:00-22:00 ${day}` },
    { label: "All day", sub: "The whole day", range: `day ${day}` },
  ]
  return (
    <div className="fr-float" style={{ position: "absolute", right: 20, top: 56, width: 340, maxHeight: "calc(100% - 72px)", overflowY: "auto", zIndex: 10, padding: 12, display: "flex", flexDirection: "column", gap: 2 }}>
      <div style={{ fontWeight: 500, padding: "2px 6px" }}>Shove: take time back</div>
      <div style={{ fontSize: 12, color: "var(--color-neutral-400)", padding: "0 6px 6px" }}>Friday moves work out of it, or tells you what would go late.</div>
      {mustDo ? (
        <MustDos list={mustDo.list} onDecide={(d) => shove(mustDo.range, d)} onCancel={() => setMustDo(null)} />
      ) : (
        <>
          <div style={{ fontSize: 11, color: "var(--color-neutral-500)", padding: "2px 6px" }}>Quick</div>
          {quick.map((o) => (
            <button key={o.label} className="fr-plain fr-hover-accent" onClick={() => shove(o.range)} style={{ display: "flex", justifyContent: "space-between", padding: "8px 6px", borderRadius: "var(--radius-md)" }}>
              <span>{o.label}</span>
              <span className="tnum" style={{ color: "var(--color-neutral-500)" }}>
                {o.sub}
              </span>
            </button>
          ))}
          <div className="fr-row" style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 6, padding: "10px 6px 4px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ width: 64, fontSize: 12, color: "var(--color-neutral-400)" }}>For</span>
              <button className="btn btn-icon btn-secondary" onClick={() => setHours(Math.max(0.5, hours - 0.5))} aria-label="Less" style={{ width: 26, height: 26 }}>
                <Icon name="minus" />
              </button>
              <span className="tnum" style={{ minWidth: 44, textAlign: "center" }}>
                {hours} h
              </span>
              <button className="btn btn-icon btn-secondary" onClick={() => setHours(Math.min(12, hours + 0.5))} aria-label="More" style={{ width: 26, height: 26 }}>
                <Icon name="plus" />
              </button>
              <div style={{ flex: 1 }} />
              <button className="btn btn-secondary" onClick={() => shove(`${Math.round(hours * 60)}m`)} style={{ padding: "4px 10px" }}>
                Shove
              </button>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ width: 64, fontSize: 12, color: "var(--color-neutral-400)" }}>Until</span>
              <input type="time" step={900} className="input" value={until} onChange={(e) => setUntil(e.target.value)} style={{ width: 110, padding: "4px 8px", minHeight: 0 }} />
              <span style={{ fontSize: 11, color: "var(--color-neutral-500)" }}>today</span>
              <div style={{ flex: 1 }} />
              <button className="btn btn-secondary" disabled={until <= nowClock} onClick={() => shove(`${nowClock}-${until}`)} style={{ padding: "4px 10px" }}>
                Shove
              </button>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <span style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>
                Tomorrow, {weekday(tomorrow)} {Number(tomorrow.slice(8, 10))}
              </span>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0,1fr))", gap: 4 }}>
                {tmr.map((o) => (
                  <button key={o.label} className="fr-plain fr-hover-accent fr-well" title={o.sub} onClick={() => shove(o.range)} style={{ padding: "6px 4px", fontSize: 12, textAlign: "center" }}>
                    {o.label}
                  </button>
                ))}
              </div>
            </div>
            <span style={{ fontSize: 11, color: "var(--color-neutral-500)" }}>Fixed events stay. Nothing goes late without asking you first.</span>
          </div>
        </>
      )}
    </div>
  )
}

function MustDos({ list, onDecide, onCancel }: { list: Schemas["MustDo"][]; onDecide: (d: Decision) => void; onCancel: () => void }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "4px 6px" }}>
      <span>This time holds work that would then be late:</span>
      {list.map((m) => (
        <div key={m.item_id} className="fr-row" style={{ display: "flex", justifyContent: "space-between", gap: 10, padding: "8px 0" }}>
          <span style={{ fontWeight: 500 }}>{m.title}</span>
          <span className="tnum" style={{ fontSize: 12, color: "var(--fr-warn)" }}>
            +{m.extra_late_hours} h late
          </span>
        </div>
      ))}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        <button className="btn btn-primary" onClick={() => onDecide("keep_must_dos")}>
          Keep must-dos
        </button>
        <button className="btn btn-secondary" onClick={() => onDecide("shove_anyway")}>
          Shove anyway
        </button>
        <button className="btn btn-ghost" onClick={onCancel}>
          Back
        </button>
      </div>
    </div>
  )
}
