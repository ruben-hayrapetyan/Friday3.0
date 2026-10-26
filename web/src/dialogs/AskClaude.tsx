// Ask Claude (personal's, COMBINED.md 20, 37): say what you want ("move my 5pm to Thursday", "prioritize assignments
// over readings"), see what Claude would change as Friday's own commands, tick what to keep, and apply. Nothing runs
// before Apply; applied, the changes undo together. ⌘↩ asks; Esc closes. Opened with `now` (a rule Friday couldn't
// read, sent with ↩ from Rules), it asks at once. A proposal that adds, moves or clears time says under it whether you
// have time for it ("can I go to poker Thursday 8 to 11?"), as `components/Fit.tsx` checks it.

import { useQueryClient } from "@tanstack/react-query"
import { useEffect, useRef, useState } from "react"
import { ApiError, type CommandName, command, type Schemas } from "@/api/client"
import { FIT_COMMANDS, type FitCommand, FitLine } from "@/components/Fit"
import { Box, Icon } from "@/components/fr/controls"
import { useToast } from "@/components/Toasts"
import { undoAll } from "@/hooks/useCommand"
import { useShell } from "@/shell/ShellContext"

export function AskClaudeDialog({ onClose }: { onClose: () => void }) {
  const { ask } = useShell()
  const client = useQueryClient()
  const toast = useToast()
  const [text, setText] = useState(ask?.text ?? "")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [answer, setAnswer] = useState<Schemas["AskClaudeOut"] | null>(null)
  const [kept, setKept] = useState<number[]>([])
  const field = useRef<HTMLTextAreaElement>(null)
  const purpose = ask?.purpose ?? "anything"
  useEffect(() => field.current?.focus(), [])
  const run = async () => {
    if (!text.trim() || busy) return
    setBusy(true)
    setError(null)
    try {
      const out = await command("ask_claude", { text, purpose })
      setAnswer(out.result)
      setKept(out.result.actions.map((a, i) => (a.error ? -1 : i)).filter((i) => i >= 0))
    } catch (e) {
      setError(e instanceof ApiError || e instanceof Error ? e.message : String(e))
    }
    setBusy(false)
  }
  const asked = useRef(false)
  useEffect(() => {
    if (ask?.now && !asked.current) {
      asked.current = true
      run()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const apply = async () => {
    if (!answer) return
    const ids: number[] = []
    try {
      for (const i of kept) {
        const a = answer.actions[i]
        const out = await command(a.command as CommandName, a.input as never)
        if (out.command_id != null) ids.push(out.command_id)
      }
    } catch (e) {
      toast({ message: e instanceof Error ? e.message : String(e), tone: "error" })
      return undoAll(client, toast, ids)
    }
    toast({ message: `Applied ${ids.length} change${ids.length === 1 ? "" : "s"}`, action: { label: "Undo", run: () => undoAll(client, toast, ids) } })
    client.invalidateQueries()
    onClose()
  }
  return (
    <div className="fr-scrim" style={{ alignItems: "flex-start", padding: "70px 24px 24px" }}>
      <div onClick={onClose} style={{ position: "absolute", inset: 0 }} />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Ask Claude"
        className="fr-float fr-dialog"
        style={{ width: "min(640px, 100%)" }}
        onKeyDown={(e) => {
          if (e.key === "Escape") onClose()
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) (e.preventDefault(), answer && kept.length ? apply() : run())
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Icon name="sparkle" size={18} style={{ color: "var(--color-accent-300)" }} />
          <span className="fr-h" style={{ fontSize: 22, flex: 1 }}>
            {purpose === "rule" ? "A rule, in your words" : "Ask Claude"}
          </span>
          <button className="btn btn-icon btn-ghost" onClick={onClose} aria-label="Close" style={{ width: 28, height: 28 }}>
            <Icon name="x" />
          </button>
        </div>
        <textarea
          ref={field}
          className="input"
          value={text}
          onChange={(e) => (setText(e.target.value), setAnswer(null))}
          placeholder={purpose === "rule" ? "I want to focus on an exam's course in the days before it" : "Move my 5pm tomorrow to Thursday"}
          aria-label="What you want"
          style={{ minHeight: 70 }}
        />
        {!answer && (
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <button className="btn btn-primary" onClick={run} disabled={busy || !text.trim()}>
              {busy ? "Asking…" : "Ask"}
            </button>
            <span className="fr-kicker">⌘↩ asks. Claude only proposes; nothing changes until you apply it.</span>
          </div>
        )}
        {error && <span style={{ color: "var(--fr-due)" }}>{error}</span>}
        {answer && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {answer.reply && <span style={{ textWrap: "pretty" }}>{answer.reply}</span>}
            {!answer.reply && !answer.actions.length && <span className="fr-kicker">Claude had no changes to suggest for this. Try saying it another way.</span>}
            {answer.actions.length > 0 && <span className="fr-eyebrow">Claude wants to</span>}
            {answer.actions.map((a, i) => {
              const on = kept.includes(i)
              const checked = !a.error && (FIT_COMMANDS as readonly string[]).includes(a.command)
              return (
                <div key={i} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <button
                  className="fr-plain fr-hover"
                  disabled={!!a.error}
                  onClick={() => setKept(on ? kept.filter((k) => k !== i) : [...kept, i])}
                  style={{ display: "grid", gridTemplateColumns: "18px minmax(0,1fr)", gap: 10, alignItems: "start", padding: 10, borderRadius: "var(--radius-md)", opacity: a.error ? 0.6 : 1 }}
                >
                  <Box on={on} />
                  <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <span>{a.sentence}</span>
                    <span className="fr-kicker" style={{ color: a.error ? "var(--fr-due)" : undefined }}>
                      {a.error ?? a.command.replaceAll("_", " ")}
                    </span>
                  </span>
                </button>
                {checked && (
                  <div style={{ paddingLeft: 38 }}>
                    <FitLine command={a.command as FitCommand} input={a.input as Record<string, unknown>} compact />
                  </div>
                )}
                </div>
              )
            })}
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-primary" onClick={apply} disabled={!kept.length}>
                <Icon name="check" />
                Apply {kept.length || ""}
              </button>
              <button className="btn btn-secondary" onClick={() => setAnswer(null)}>
                Ask again
              </button>
              <button className="btn btn-ghost" onClick={onClose}>
                Discard
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
