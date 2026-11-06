// Shove (v22): take time back. Quick picks, "for N hours", from one time to another on any day this week, or a slice
// of tomorrow. When clearing it would make work late, the must-dos are listed and you choose. The choice you press
// sinks and turns while Friday works; then the panel says what was cleared, and the time glows on the calendar.

import { useQueryClient } from "@tanstack/react-query"
import { type ReactNode, useCallback, useEffect, useState } from "react"
import { useLocation, useNavigate } from "react-router"
import type { Schemas } from "@/api/client"
import { Icon, Menu } from "@/components/fr/controls"
import { useToast } from "@/components/Toasts"
import { runCommand, undoAll } from "@/hooks/useCommand"
import { useClock } from "@/hooks/useClock"
import { ampm, weekday } from "@/lib/format"
import { addDays, fromMin } from "@/lib/time"
import { useShell } from "@/shell/ShellContext"
import { markShoved } from "./shoved"
import { TimeInput } from "@/components/fr/TimeInput"

type Decision = "ask" | "shove_anyway" | "keep_must_dos"

interface Done {
  message: string
  day: string | null
  created: number[]
  commandId: number | null
}

const CLOSE_AFTER_MS = 4000

export function ShovePop() {
  const { today, setPop } = useShell()
  const client = useQueryClient()
  const toast = useToast()
  const now = useClock()
  const [hours, setHours] = useState(1)
  const [mustDo, setMustDo] = useState<{ range: string; list: Schemas["MustDo"][] } | null>(null)
  const [busy, setBusy] = useState<string | null>(null) // the choice being shoved
  const [done, setDone] = useState<Done | null>(null)
  const close = useCallback(() => setPop(null), [setPop]) // steady, so the clock's ticks don't restart its timer
  const nowClock = fromMin(now).slice(11, 16)
  // Any stretch of any day this week: from the next quarter hour for an hour, unless you say otherwise.
  const [from, setFrom] = useState(() => fromMin(Math.ceil(now / 15) * 15).slice(11, 16))
  const [until, setUntil] = useState(() => fromMin(Math.ceil(now / 15) * 15 + 60).slice(11, 16))
  const [on, setOn] = useState(0) // days from today
  const days = Array.from({ length: 7 }, (_, n) => {
    const d = addDays(today, n)
    return { value: String(n), label: n === 0 ? "Today" : n === 1 ? "Tomorrow" : `${weekday(d)} ${Number(d.slice(8, 10))}` }
  })
  const wrong = !from || !until ? "Give both times" : until <= from ? "The end comes after the start" : on === 0 && until <= nowClock ? "That time has passed" : null
  const shove = async (key: string, range: string, decision: Decision = "ask") => {
    if (busy) return
    setBusy(key)
    const out = await runCommand(client, toast, "shove", { range, decision }, { label: (o) => o.result.message ?? "Shoved", quiet: true })
    setBusy(null)
    const list = out?.result.must_do ?? []
    const created = out?.result.created ?? []
    if (out && !created.length && list.length) setMustDo({ range, list })
    else if (out) {
      markShoved(created)
      setMustDo(null)
      setDone({ message: out.result.message ?? "Shoved", day: out.result.day ?? null, created, commandId: out.command_id })
    }
  }
  const tomorrow = addDays(today, 1)
  const day = weekday(tomorrow).toLowerCase()
  const quick = [
    { label: "Next hour", sub: `${ampm(nowClock)}–${ampm(fromMin(now + 60))}`, range: "1h" },
    { label: "Rest of today", sub: `from ${ampm(nowClock)}`, range: "rest" },
    ...(nowClock < "19:00" ? [{ label: "Tonight", sub: "7pm–11pm", range: "19:00-23:00" }] : []),
  ]
  const tmr = [
    { label: "Morning", sub: "8am–12pm", range: `08:00-12:00 ${day}` },
    { label: "Afternoon", sub: "12pm–5pm", range: `12:00-17:00 ${day}` },
    { label: "Evening", sub: "5pm–10pm", range: `17:00-22:00 ${day}` },
    { label: "All day", sub: "The whole day", range: `day ${day}` },
  ]
  const working = (key: string, idle: ReactNode) => (busy === key ? <Working /> : idle)
  return (
    <div className="fr-float" style={{ position: "absolute", right: 12, top: 56, width: "min(340px, calc(100vw - 24px))", maxHeight: "calc(100% - 72px)", overflowY: "auto", zIndex: 10, padding: 12, display: "flex", flexDirection: "column", gap: 2 }}>
      {done ? (
        <Shoved done={done} onClose={close} />
      ) : (
        <>
          <div style={{ fontWeight: 500, padding: "2px 6px" }}>Shove: take time back</div>
          <div style={{ fontSize: 12, color: "var(--color-neutral-400)", padding: "0 6px 6px" }}>Friday moves work out of it, or tells you what would go late.</div>
          {mustDo ? (
            <MustDos list={mustDo.list} busy={busy} onDecide={(d) => shove(d, mustDo.range, d)} onCancel={() => setMustDo(null)} />
          ) : (
            <>
              <div style={{ fontSize: 11, color: "var(--color-neutral-500)", padding: "2px 6px" }}>Quick</div>
              {quick.map((o) => (
                <button key={o.label} className="fr-plain fr-hover-accent fr-press" disabled={!!busy} onClick={() => shove(o.label, o.range)} style={{ display: "flex", justifyContent: "space-between", padding: "8px 6px", borderRadius: "var(--radius-md)", ...pressed(busy === o.label) }}>
                  <span>{o.label}</span>
                  <span className="tnum" style={{ color: "var(--color-neutral-500)" }}>
                    {working(o.label, o.sub)}
                  </span>
                </button>
              ))}
              <div className="fr-row" style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 6, padding: "10px 6px 4px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ width: 64, fontSize: 12, color: "var(--color-neutral-400)" }}>For</span>
                  <button className="btn btn-icon btn-secondary" onClick={() => setHours(Math.max(0.5, hours - 0.5))} aria-label="Less" style={{ width: 26, height: 26 }}>
                    <Icon name="minus" />
                  </button>
                  <span className="tnum" style={{ width: 48, flex: "none", whiteSpace: "nowrap", textAlign: "center" }}>
                    {hours} h
                  </span>
                  <button className="btn btn-icon btn-secondary" onClick={() => setHours(Math.min(12, hours + 0.5))} aria-label="More" style={{ width: 26, height: 26 }}>
                    <Icon name="plus" />
                  </button>
                  <div style={{ flex: 1 }} />
                  <button className="btn btn-secondary fr-press" disabled={!!busy} onClick={() => shove("for", `${Math.round(hours * 60)}m`)} style={{ padding: "4px 10px", ...pressed(busy === "for") }}>
                    {working("for", "Shove")}
                  </button>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>From</span>
                    <TimeInput step={900} value={from} onChange={setFrom} label="From" style={{ flex: 1, minWidth: 0, padding: "4px 6px", minHeight: 0 }} />
                    <span style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>to</span>
                    <TimeInput step={900} value={until} onChange={setUntil} label="To" expect={{ after: from }} style={{ flex: 1, minWidth: 0, padding: "4px 6px", minHeight: 0 }} />
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <Menu options={days} value={String(on)} onPick={(v) => setOn(Number(v))} label="Which day" />
                    <div style={{ flex: 1 }} />
                    <button className="btn btn-secondary fr-press" disabled={!!wrong || !!busy} title={wrong ?? undefined} onClick={() => shove("range", `${from}-${until} +${on}d`)} style={{ padding: "4px 10px", ...pressed(busy === "range") }}>
                      {working("range", "Shove")}
                    </button>
                  </div>
                  {wrong && <span style={{ fontSize: 11, color: "var(--color-neutral-500)" }}>{wrong}</span>}
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <span style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>
                    Tomorrow, {weekday(tomorrow)} {Number(tomorrow.slice(8, 10))}
                  </span>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0,1fr))", gap: 4 }}>
                    {tmr.map((o) => (
                      <button key={o.label} className="fr-plain fr-hover-accent fr-well fr-press" disabled={!!busy} title={o.sub} onClick={() => shove(o.label, o.range)} style={{ padding: "6px 4px", fontSize: 12, textAlign: "center", display: "flex", justifyContent: "center", ...pressed(busy === o.label) }}>
                        {working(o.label, o.label)}
                      </button>
                    ))}
                  </div>
                </div>
                <span style={{ fontSize: 11, color: "var(--color-neutral-500)" }}>Fixed events stay. Nothing goes late without asking you first.</span>
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}

/** The choice being shoved stays lit, as a button held down; the others wait. */
function pressed(on: boolean) {
  return on ? { background: "color-mix(in srgb, var(--color-accent) 22%, transparent)", color: "var(--color-accent-200)", opacity: 1 } : {}
}

function Working() {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, color: "var(--color-accent-200)" }}>
      <span className="fr-spinner" />
      Shoving…
    </span>
  )
}

/** What was cleared, with a check: it goes on its own after a few seconds, unless the pointer is resting on it. */
function Shoved({ done, onClose }: { done: Done; onClose: () => void }) {
  const { place, setPlace } = useShell()
  const client = useQueryClient()
  const toast = useToast()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [resting, setResting] = useState(false)
  useEffect(() => {
    if (resting) return
    const timer = setTimeout(onClose, CLOSE_AFTER_MS)
    return () => clearTimeout(timer)
  }, [resting, onClose])
  const show = () => {
    if (done.day) setPlace({ view: place.view === "month" ? 1 : place.view, first: done.day })
    if (pathname !== "/") navigate("/")
    markShoved(done.created) // glow again, now that it's in view
    onClose()
  }
  const undo = async () => {
    if (done.commandId !== null) await undoAll(client, toast, [done.commandId])
    onClose()
  }
  return (
    <div role="status" onPointerEnter={() => setResting(true)} onPointerLeave={() => setResting(false)} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, padding: "14px 6px 6px", textAlign: "center" }}>
      <span className="fr-shoved-check" style={{ width: 40, height: 40, borderRadius: "50%", display: "grid", placeItems: "center", background: "color-mix(in srgb, var(--color-accent) 20%, transparent)", color: "var(--color-accent-200)" }}>
        <Icon name="check" size={22} />
      </span>
      <span style={{ fontWeight: 500, fontSize: 15 }}>Shoved</span>
      <span style={{ fontSize: 13, color: "var(--color-neutral-300)", textWrap: "pretty" }}>{done.message}</span>
      <span style={{ fontSize: 11, color: "var(--color-neutral-500)" }}>It’s yours now, striped on the calendar. ⌘Z undoes it.</span>
      <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
        <button className="btn btn-secondary fr-press" onClick={show} style={{ padding: "4px 10px" }}>
          Show me
        </button>
        <button className="btn btn-ghost fr-press" onClick={undo} style={{ padding: "4px 10px" }}>
          Undo
        </button>
      </div>
    </div>
  )
}

function MustDos({ list, busy, onDecide, onCancel }: { list: Schemas["MustDo"][]; busy: string | null; onDecide: (d: Decision) => void; onCancel: () => void }) {
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
        <button className="btn btn-primary fr-press" disabled={!!busy} onClick={() => onDecide("keep_must_dos")}>
          {busy === "keep_must_dos" ? <Working /> : "Keep must-dos"}
        </button>
        <button className="btn btn-secondary fr-press" disabled={!!busy} onClick={() => onDecide("shove_anyway")}>
          {busy === "shove_anyway" ? <Working /> : "Shove anyway"}
        </button>
        <button className="btn btn-ghost" disabled={!!busy} onClick={onCancel}>
          Back
        </button>
      </div>
    </div>
  )
}
