// Do I have time for this? (`fit`): a change tried on a copy of your plan and never kept. The quick check runs by
// itself a moment after the change stops changing (the deadlines alone, well under a second); "Check exactly" plans it
// as a replan would, a few seconds. An event that makes work late offers other times, which `onTime` takes.

import { useEffect, useState } from "react"
import { errorWords, queryBody, type Schemas } from "@/api/client"
import { Icon } from "@/components/fr/controls"
import { when } from "@/lib/format"
import { useShell } from "@/shell/ShellContext"

type Fit = Schemas["FitOut"]
export type FitCommand = Schemas["FitInput"]["command"]
export const FIT_COMMANDS: readonly FitCommand[] = ["add", "edit", "series_add", "shove", "rule_add", "pin", "day_override"]

export const LOOK: Record<Fit["verdict"], { icon: string; ink: string }> = {
  fits: { icon: "check-circle", ink: "var(--color-accent-300)" },
  tight: { icon: "hourglass-medium", ink: "var(--fr-warn)" },
  late: { icon: "warning", ink: "var(--fr-due)" },
}

/** The check for a change, quick by itself once `input` settles, exact on asking; null until there is one. */
export function useFit(command: FitCommand, input: Record<string, unknown> | null) {
  const key = input ? JSON.stringify([command, input]) : null
  const [fit, setFit] = useState<{ for: string; out: Fit } | null>(null)
  const [busy, setBusy] = useState(false)
  // for the change it was about, as the fit is: a check of what the change was, failing late, doesn't stand under the
  // change as it is now (the audit, 12 Nov)
  const [error, setError] = useState<{ for: string; said: string } | null>(null)
  const cleared = (k: string) => setError((e) => (e?.for === k ? null : e))
  useEffect(() => {
    if (!key || !input) return
    const timer = setTimeout(
      () => queryBody("fit", { command, input, exact: false }).then((out) => (setFit({ for: key, out }), cleared(key)), (e) => setError({ for: key, said: errorWords(e) })),
      400,
    )
    return () => clearTimeout(timer)
  }, [key]) // eslint-disable-line react-hooks/exhaustive-deps
  const exact = async () => {
    if (!key || !input) return
    setBusy(true)
    try {
      setFit({ for: key, out: await queryBody("fit", { command, input, exact: true }) })
      cleared(key)
    } catch (e) {
      setError({ for: key, said: errorWords(e) })
    }
    setBusy(false)
  }
  return { fit: fit && fit.for === key ? fit.out : null, exact, busy, error: error && error.for === key ? error.said : null }
}

/** One line under the change: whether you have time, and what would be late; for an event, other times. */
export function FitLine({ command, input, onTime, compact = false }: { command: FitCommand; input: Record<string, unknown> | null; onTime?: (start: string, end: string) => void; compact?: boolean }) {
  const { today } = useShell()
  const { fit, exact, busy, error } = useFit(command, input)
  if (!input) return null
  if (error) return <span style={{ fontSize: 12, color: "var(--color-neutral-500)" }}>Couldn’t check the time: {error}</span>
  if (!fit) return <span style={{ fontSize: 12, color: "var(--color-neutral-500)" }}>Checking whether you have time…</span>
  const look = LOOK[fit.verdict]
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: compact ? 11.5 : 12 }}>
      <span style={{ display: "flex", gap: 6, alignItems: "flex-start", color: look.ink }}>
        <Icon name={look.icon} size={13} style={{ flex: "none", marginTop: 2 }} />
        <span style={{ textWrap: "pretty" }}>
          {fit.said}
          {fit.exact ? "." : fit.verdict === "late" ? ", even with every free minute." : "."}
          {!fit.exact && (
            <>
              {" "}
              <button
                className="fr-link"
                disabled={busy}
                onClick={exact}
                title="The quick check counts every free minute; this plans it with your rules and preferences, as a replan would"
                style={{ fontSize: "inherit" }}
              >
                {busy ? "Planning it (up to half a minute)…" : "Check exactly"}
              </button>
            </>
          )}
        </span>
      </span>
      {onTime && !!fit.instead?.length && (
        <span style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap", color: "var(--color-neutral-400)" }}>
          Nothing gets later at
          {fit.instead.map((t) => (
            <button key={t.start} className="btn btn-secondary fr-press" onClick={() => onTime(t.start, t.end)} style={{ fontSize: 11.5, padding: "1px 8px" }}>
              {when(t.start, today)}
            </button>
          ))}
        </span>
      )}
    </div>
  )
}
