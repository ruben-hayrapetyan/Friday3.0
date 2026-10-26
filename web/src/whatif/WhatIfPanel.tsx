// What if's panel, over the calendar's right side: what you're trying, what it costs together (later past a deadline,
// past a soft due, days that end later, optional events given up), each change with what it alone leaves short and
// a ✕, a line to try something new in your words, and Keep or Discard. The calendar behind it shows the plan with
// the changes, the items they make or change outlined.

import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { ApiError } from "@/api/client"
import { LOOK } from "@/components/Fit"
import { Icon } from "@/components/fr/controls"
import { useToast } from "@/components/Toasts"
import { runCommand } from "@/hooks/useCommand"
import { ampm, dayLabel } from "@/lib/format"
import { useShell } from "@/shell/ShellContext"
import { useTrial, useWhatIf, whatIf } from "./store"

export function WhatIfPanel({ right }: { right: number }) {
  const { today } = useShell()
  const w = useWhatIf()
  const trial = useTrial(today)
  const client = useQueryClient()
  const toast = useToast()
  const [text, setText] = useState("")
  const [open, setOpen] = useState(true)
  const out = trial.data
  const planning = trial.isFetching
  const refused = (out?.changes ?? []).some((c) => c.error)
  const exit = () => {
    whatIf.stop()
    client.invalidateQueries({ queryKey: ["plan"] })
  }
  const keep = async () => {
    const kept = await runCommand(client, toast, "whatif_keep", { changes: w.changes }, { label: (o) => o.result.message ?? "Kept" })
    if (kept) exit()
  }
  const tryIt = () => {
    if (!text.trim()) return
    whatIf.stage("add", { text: text.trim() })
    setText("")
  }
  const error = trial.error ? (trial.error instanceof ApiError || trial.error instanceof Error ? trial.error.message : String(trial.error)) : null
  const look = out && w.changes.length ? LOOK[out.verdict] : null
  return (
    <aside
      aria-label="What if"
      style={{ position: "absolute", right, top: 60, zIndex: 6, width: "min(360px, calc(100% - 24px))", maxHeight: "calc(100% - 140px)", display: "flex", flexDirection: "column", borderRadius: "var(--radius-lg)", background: "var(--color-surface)", boxShadow: "var(--fr-shadow-float, 0 12px 32px rgba(0,0,0,.28))", border: "1px solid color-mix(in srgb, var(--color-accent) 40%, transparent)", overflow: "hidden" }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 12px", borderBottom: open ? "1px solid var(--fr-hairline)" : undefined }}>
        <Icon name="flask" size={16} style={{ color: "var(--color-accent-300)" }} />
        <button className="fr-plain" onClick={() => setOpen(!open)} style={{ flex: 1, textAlign: "left", fontWeight: 500 }} aria-expanded={open}>
          What if{w.changes.length ? ` · ${w.changes.length} change${w.changes.length === 1 ? "" : "s"}` : ""}
          {!open && look && <Icon name={look.icon} size={13} style={{ color: look.ink, marginLeft: 8 }} />}
        </button>
        {planning && <span className="fr-spinner" aria-label="Planning" />}
        <button className="btn btn-icon btn-ghost" onClick={exit} aria-label="Leave What if" title="Leave What if: nothing is kept" style={{ width: 26, height: 26 }}>
          <Icon name="x" />
        </button>
      </div>
      {open && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12, padding: 12, overflowY: "auto" }}>
          {!w.changes.length ? (
            <span style={{ fontSize: 12, color: "var(--color-neutral-300)", textWrap: "pretty" }}>
              Try things on the calendar as you normally would: add or drag an event, skip one from its popover, add a to-do, shove a stretch. Nothing is saved; this shows what it would cost, and Keep makes it real.
            </span>
          ) : (
            <>
              {planning && (
                <span className="fr-kicker" style={{ textWrap: "pretty" }}>
                  Planning your week with {w.changes.length === 1 ? "it" : "them"}… on a full week this takes about 20 seconds.
                </span>
              )}
              {error && <span style={{ fontSize: 12, color: "var(--fr-due)" }}>{error}</span>}
              {out && look && (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <span style={{ display: "flex", gap: 8, alignItems: "flex-start", color: look.ink, fontSize: 13, fontWeight: 500, opacity: planning ? 0.6 : 1 }}>
                    <Icon name={look.icon} size={15} style={{ flex: "none", marginTop: 2 }} />
                    <span style={{ textWrap: "pretty" }}>{out.said}.</span>
                  </span>
                  {(out.later_days ?? []).slice(0, 3).map((d) => (
                    <span key={d.date} style={{ fontSize: 12, color: "var(--color-neutral-300)", paddingLeft: 23 }}>
                      {dayLabel(d.date)}: work ends {d.after ? ampm(d.after) : "—"}
                      <span style={{ color: "var(--color-neutral-500)" }}> (now {d.before ? ampm(d.before) : "no work"})</span>
                    </span>
                  ))}
                  {(out.notices ?? []).slice(0, 3).map((n) => (
                    <span key={n} style={{ fontSize: 12, color: "var(--color-neutral-400)", paddingLeft: 23, textWrap: "pretty" }}>
                      {n}
                    </span>
                  ))}
                </div>
              )}
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <span className="fr-eyebrow">Trying</span>
                {w.changes.map((c, i) => {
                  const said = trial.isPlaceholderData ? undefined : out?.changes[i] // an older try's may be another's
                  return (
                    <div key={i} style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", gap: 8, alignItems: "start", padding: "6px 0", borderBottom: "1px solid var(--fr-hairline)" }}>
                      <span style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: 13 }}>
                        <span style={{ textWrap: "pretty" }}>{said?.said ?? describe(c)}</span>
                        {said?.error && <span style={{ fontSize: 11.5, color: "var(--fr-due)" }}>Can’t be done: {said.error}</span>}
                        {!!said?.late?.length && <span style={{ fontSize: 11.5, color: "var(--fr-due)" }}>On its own: leaves {said.late.join(", ")} short</span>}
                      </span>
                      <button className="btn btn-icon btn-ghost" onClick={() => whatIf.remove(i)} aria-label="Take this out" title="Take this out" style={{ width: 22, height: 22 }}>
                        <Icon name="x" size={12} />
                      </button>
                    </div>
                  )
                })}
              </div>
            </>
          )}
          <div style={{ display: "flex", gap: 6 }}>
            <input
              className="input"
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && tryIt()}
              placeholder="Try: dinner with Sam fri 7–10pm"
              aria-label="Something to try"
              style={{ flex: 1, minWidth: 0, fontSize: 13 }}
            />
            <button className="btn btn-secondary" onClick={tryIt} disabled={!text.trim()} style={{ fontSize: 12 }}>
              Try
            </button>
          </div>
          {w.changes.length > 0 && (
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <button className="btn btn-primary" onClick={keep} disabled={planning || refused || !out} title={refused ? "Take out what can’t be done first" : "Make these changes for real; one Undo takes them all back"}>
                <Icon name="check" />
                Keep {w.changes.length === 1 ? "it" : `all ${w.changes.length}`}
              </button>
              <button className="btn btn-ghost" onClick={exit}>
                Discard
              </button>
            </div>
          )}
        </div>
      )}
    </aside>
  )
}

/** A change in words before the server has said it. */
function describe(c: { command: string; input: Record<string, unknown> }): string {
  const named = (c.input.text ?? c.input.title) as string | undefined
  const verb = { add: "Add", series_add: "Add", edit: "Change", pin: "Move", unpin: "Let Friday place", skip: "Skip", drop: "Delete", shove: "Keep free", rule_add: "Rule:", day_override: "Change a day" }[c.command] ?? c.command
  return named ? `${verb} ${named}` : `${verb}…`
}
