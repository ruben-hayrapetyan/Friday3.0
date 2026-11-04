// Ask Claude (personal's, COMBINED.md 20, 37): say what you want ("move my 5pm to Thursday", "prioritize assignments
// over readings"), see what Claude would change as Friday's own commands, tick what to keep, and apply. Nothing runs
// before Apply; applied, the changes undo together. ⌘↩ asks; Esc closes. Opened with `now` (a rule Friday couldn't
// read, sent with ↩ from Rules), it asks at once. A proposal that adds, moves or clears time says under it whether you
// have time for it ("can I go to poker Thursday 8 to 11?"), as `components/Fit.tsx` checks it. With "Change calendar
// events without asking" on (27 Oct), what only adds, moves, repeats or deletes an event applies as the answer comes,
// with one Undo; the rest still waits for Apply.

import { spoken } from "@/lib/aiName"
import { useAi } from "@/settings/AiConnect"
import { type QueryClient, useQueryClient } from "@tanstack/react-query"
import { useEffect, useRef, useState } from "react"
import { ApiError, command, type Schemas } from "@/api/client"
import { FIT_COMMANDS, type FitCommand, FitLine } from "@/components/Fit"
import { Box, Icon, Switch } from "@/components/fr/controls"
import { useToast } from "@/components/Toasts"
import { useSettings } from "@/hooks/queries"
import { runTogether, undoAll, useCommand } from "@/hooks/useCommand"
import { useShell } from "@/shell/ShellContext"
import { asking, useAsking, waiting } from "./asking"

/** Claude's proposals you kept, run in order as one change: Undo takes them all back, and one that fails takes back
 * those before it. Whether they all ran. */
export async function applyActions(actions: Schemas["ProposedAction"][], client: QueryClient, toast: ReturnType<typeof useToast>): Promise<boolean> {
  const ids = await runActions(actions, client, toast)
  if (ids === null) return false
  toast({ message: `Applied ${ids.length} change${ids.length === 1 ? "" : "s"}`, action: { label: "Undo", run: () => undoAll(client, toast, ids) } })
  return true
}

/** The actions run in order, as `applyActions` runs them: the changes' ids, or null when one failed. */
async function runActions(actions: Schemas["ProposedAction"][], client: QueryClient, toast: ReturnType<typeof useToast>): Promise<number[] | null> {
  const ids = await runTogether(client, toast, actions)
  if (ids) client.invalidateQueries()
  return ids
}

/** Which of Claude's proposals apply as the answer comes: those that only change calendar events, when you said so. */
export function withoutAsking(actions: Schemas["ProposedAction"][], on: boolean): number[] {
  return on ? actions.flatMap((a, i) => (a.event && !a.error ? [i] : [])) : []
}

/** What to tick at first: everything that would run, but what already ran or can't. */
const ticked = (actions: Schemas["ProposedAction"][], now: number[] = []) => actions.map((a, i) => (a.error || now.includes(i) ? -1 : i)).filter((i) => i >= 0)

export function AskClaudeDialog({ onClose }: { onClose: () => void }) {
  const { ask, askClaude } = useShell()
  const client = useQueryClient()
  const toast = useToast()
  // A question asked earlier and answered while the window was closed, or still being thought about, comes back here
  const earlier = asking.get()
  const resumed = earlier && (!ask?.text || ask.text === earlier.text) ? earlier : null
  const [text, setText] = useState(ask?.text || resumed?.text || "")
  const [error, setError] = useState<string | null>(resumed?.state === "failed" ? resumed.error ?? null : null)
  const [answer, setAnswer] = useState<Schemas["AskClaudeOut"] | null>(resumed?.state === "answered" ? resumed.answer ?? null : null)
  const [kept, setKept] = useState<number[]>(resumed?.answer ? ticked(resumed.answer.actions) : [])
  const flight = useAsking()
  const busy = flight?.state === "asking"
  const [, tick] = useState(0)
  useEffect(() => {
    if (!busy) return
    const every = setInterval(() => tick((n) => n + 1), 1000)
    return () => clearInterval(every)
  }, [busy])
  useEffect(() => {
    asking.open(true)
    if (resumed && resumed.state !== "asking") asking.clear() // shown now: not kept to show again
    return () => void asking.open(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const [done, setDone] = useState<{ at: number[]; ids: number[] } | null>(null) // applied without asking
  const field = useRef<HTMLTextAreaElement>(null)
  const purpose = ask?.purpose ?? "anything"
  const claude = (useSettings().data as { claude?: { events_without_asking?: boolean } } | undefined)?.claude
  const auto = !!claude?.events_without_asking
  const ai = useAi().name
  const saveSetting = useCommand("settings_set", { label: () => (auto ? `${ai} asks before changing events` : `${ai} changes events without asking`) })
  useEffect(() => field.current?.focus(), [])
  const run = async () => {
    if (!text.trim() || busy) return
    setError(null)
    const { id, signal } = asking.begin(text, purpose)
    try {
      const out = await command("ask_claude", { text, purpose }, { signal })
      if (asking.get()?.id !== id || asking.get()?.state !== "asking") return // stopped, or asked again since
      asking.settle(id, out.result)
      const now = withoutAsking(out.result.actions, auto)
      if (!asking.isOpen()) {
        // you closed the window to keep working: say it's here, and open it again on a click
        toast({ message: `${ai} answered “${text.length > 40 ? `${text.slice(0, 40)}…` : text}”`, action: { label: "See it", run: () => askClaude(text, purpose) } })
      } else asking.clear()
      setAnswer(out.result)
      setDone(null)
      setKept(ticked(out.result.actions, now))
      if (now.length) {
        const ids = await runActions(now.map((i) => out.result.actions[i]), client, toast)
        if (ids) {
          setDone({ at: now, ids })
          // the dialog's own Undo goes when it closes; this one stays
          toast({ message: `Changed ${now.length === 1 ? "an event" : `${now.length} events`} without asking`, action: { label: "Undo", run: () => undoAll(client, toast, ids) } })
        }
        else setKept((was) => [...was, ...now].sort((a, b) => a - b)) // they failed and were taken back: yours to apply
      }
    } catch (e) {
      if (signal.aborted) return // you stopped waiting
      const said = e instanceof ApiError || e instanceof Error ? e.message : String(e)
      asking.fail(id, said)
      if (!asking.isOpen()) toast({ message: `${ai} couldn't answer: ${said}`, tone: "error" })
      else asking.clear()
      setError(said)
    }
  }
  const seconds = flight && busy ? (Date.now() - flight.began) / 1000 : 0
  const wait = waiting(seconds, spoken(ai))
  const asked = useRef(false)
  useEffect(() => {
    if (ask?.now && !asked.current) {
      asked.current = true
      run()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const [applying, setApplying] = useState(false)
  const apply = async () => {
    if (!answer || applying) return // a second click or ⌘↩ doesn't apply it twice
    setApplying(true)
    const ok = await applyActions(kept.map((i) => answer.actions[i]), client, toast)
    setApplying(false)
    if (ok) onClose()
  }
  return (
    <div className="fr-scrim" style={{ alignItems: "flex-start", padding: "70px 24px 24px" }}>
      <div onClick={onClose} style={{ position: "absolute", inset: 0 }} />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Ask ${ai}`}
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
            {purpose === "rule" ? "A rule, in your words" : `Ask ${ai}`}
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
            {busy ? (
              <>
                <span className="tnum" role="status" style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
                  <span className="fr-spinner" aria-hidden />
                  {wait.line}
                </span>
                <button className="btn btn-secondary" onClick={() => flight && asking.stop(flight.id)} title="Stop waiting; nothing it would have proposed is kept">
                  <Icon name="stop" />
                  Stop
                </button>
              </>
            ) : (
              <>
                <button className="btn btn-primary" onClick={run} disabled={!text.trim()}>
                  Ask
                </button>
                <span className="fr-kicker">⌘↩ asks. {auto ? "Changes to calendar events apply at once; the rest wait for you." : `${ai} only proposes; nothing changes until you apply it.`}</span>
              </>
            )}
          </div>
        )}
        {busy && wait.note && <span className="fr-kicker">{wait.note}</span>}
        {error && <span style={{ color: "var(--fr-due)" }}>{error}</span>}
        {answer && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {answer.reply && <span style={{ textWrap: "pretty" }}>{answer.reply}</span>}
            {!answer.reply && !answer.actions.length && <span className="fr-kicker">{ai} had no changes to suggest for this. Try saying it another way.</span>}
            {answer.actions.length > 0 && <span className="fr-eyebrow">{ai} wants to</span>}
            {answer.actions.map((a, i) => {
              if (done?.at.includes(i))
                return (
                  <div key={i} style={{ display: "grid", gridTemplateColumns: "18px minmax(0,1fr)", gap: 10, alignItems: "start", padding: 10 }}>
                    <Icon name="check-circle" fill size={16} style={{ color: "var(--color-accent-300)" }} />
                    <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                      <span>{a.sentence}</span>
                      <span className="fr-kicker">Done: a change to your calendar</span>
                    </span>
                  </div>
                )
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
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              {done && (
                <button className="btn btn-secondary" onClick={async () => (await undoAll(client, toast, done.ids), setKept((was) => [...was, ...done.at].sort((a, b) => a - b)), setDone(null))}>
                  <Icon name="arrow-counter-clockwise" />
                  Undo {done.at.length === 1 ? "the change" : `the ${done.at.length} changes`} made
                </button>
              )}
              <button className="btn btn-primary" onClick={apply} disabled={!kept.length || applying}>
                <Icon name="check" />
                Apply {kept.length || ""}
              </button>
              <button className="btn btn-secondary" onClick={() => setAnswer(null)}>
                Ask again
              </button>
              <button className="btn btn-ghost" onClick={onClose}>
                {done && !kept.length ? "Close" : "Discard"}
              </button>
            </div>
          </div>
        )}
        {purpose !== "rule" && (
          <label style={{ display: "flex", alignItems: "center", gap: 10, paddingTop: 4, fontSize: 12, color: "var(--color-neutral-400)" }}>
            <Switch on={auto} onToggle={() => saveSetting({ key: "claude", value: { ...claude, events_without_asking: !auto } })} label="Change calendar events without asking" />
            <span style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              <span style={{ color: "var(--color-text)" }}>Change calendar events without asking</span>
              <span className="fr-kicker">Adding, moving, repeating or deleting events applies at once, with Undo. Tasks, rules and settings still ask.</span>
            </span>
          </label>
        )}
      </div>
    </div>
  )
}
