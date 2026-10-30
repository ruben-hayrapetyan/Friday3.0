// What if's controls, as calendar apps show a mode you're in (Docs' "Suggesting", a tentative event's dashed edge):
// in the header, a chip that says what you're trying and how it lands (Fits, Tight, Late), with Discard and Keep;
// on the right, in the drawer's place so the week narrows rather than being covered, the changes one by one (each
// with what it alone leaves short, Edit for a new event, ✕ to take it out), what they cost together, and a line to
// try something new in your words. While Friday plans, a bar runs and the last answer stays.

import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { ApiError, type Schemas } from "@/api/client"
import { LOOK } from "@/components/Fit"
import { Icon } from "@/components/fr/controls"
import { useToast } from "@/components/Toasts"
import { runCommand } from "@/hooks/useCommand"
import { ampm, dayLabel } from "@/lib/format"
import { useShell } from "@/shell/ShellContext"
import { draftOf } from "@/shell/EventPane"
import { type Change, placeholder, useTrial, useWhatIf, whatIf } from "./store"

const EXAMPLES = ["dinner with Sam fri 7–10pm", "essay ~3h due thu 5pm", "No work after 10pm"]
const RULE = /^(no |never |don't |dont |always |keep |at most |only |prefer |avoid |finish )/i
const SHORT: Record<Schemas["WhatIfOut"]["verdict"], string> = { fits: "Fits", tight: "Tight", late: "Late" }

function useKeep() {
  const client = useQueryClient()
  const toast = useToast()
  return async () => {
    const changes = whatIf.get().changes
    const kept = await runCommand(client, toast, "whatif_keep", { changes }, { label: (o) => o.result.message ?? "Kept" })
    if (kept) {
      whatIf.stop()
      client.invalidateQueries()
    }
  }
}

function discard(client: ReturnType<typeof useQueryClient>) {
  whatIf.stop()
  client.invalidateQueries({ queryKey: ["plan"] })
}

/** The header's What if: a button to start, and while trying, how it lands, Discard and Keep. */
export function WhatIfBar({ tight }: { tight: boolean }) {
  const w = useWhatIf()
  const { today } = useShell()
  const trial = useTrial(today)
  const client = useQueryClient()
  const keep = useKeep()
  if (!w.on)
    return (
      <button className="btn btn-secondary" data-tour="whatif" onClick={whatIf.start} title="What if: try changes on the calendar and see what they cost, without making them" style={{ flex: "none", fontSize: 12, gap: 6 }}>
        <Icon name="flask" size={15} />
        {!tight && "What if"}
      </button>
    )
  const n = w.changes.length
  const out = trial.out && trial.answered === n ? trial.out : null
  const refused = (out?.changes ?? []).some((c) => c.error)
  const look = out ? LOOK[out.verdict] : null
  return (
    <div
      role="group"
      aria-label="What if"
      style={{ flex: "none", display: "flex", alignItems: "center", gap: 6, padding: "3px 4px 3px 10px", borderRadius: 999, fontSize: 12, background: "color-mix(in srgb, var(--color-accent) 13%, transparent)", border: "1px solid color-mix(in srgb, var(--color-accent) 45%, transparent)" }}
    >
      <Icon name="flask" size={14} style={{ color: "var(--color-accent-200)" }} />
      {!tight && <span style={{ fontWeight: 500, color: "var(--color-accent-200)" }}>What if</span>}
      <button className="fr-plain fr-hover-text" onClick={() => whatIf.showPanel(!w.panel)} title={w.panel ? "Hide the changes" : "Show the changes"} style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--color-neutral-300)" }}>
        {!n ? (
          "nothing tried yet"
        ) : trial.planning ? (
          <>
            <span className="fr-spinner" aria-label="Planning" />
            {!tight && "planning…"}
          </>
        ) : trial.error ? (
          <span style={{ color: "var(--fr-due)" }}>couldn’t plan it</span>
        ) : look && out ? (
          <span style={{ display: "flex", alignItems: "center", gap: 4, color: look.ink, fontWeight: 500 }}>
            <Icon name={look.icon} size={13} />
            {SHORT[out.verdict]}
          </span>
        ) : null}
        {n > 0 && !tight && <span style={{ color: "var(--color-neutral-500)" }}>· {n} change{n === 1 ? "" : "s"}</span>}
      </button>
      <button className="btn btn-ghost" onClick={() => discard(client)} style={{ fontSize: 12, padding: "2px 10px" }} title="Leave What if; nothing you tried is kept">
        {n ? "Discard" : "Leave"}
      </button>
      {n > 0 && (
        <button className="btn btn-primary" onClick={keep} disabled={trial.planning || refused || !out} style={{ fontSize: 12, padding: "2px 12px" }} title={refused ? "Take out what can’t be done first" : "Make these changes for real; one Undo takes them all back"}>
          Keep
        </button>
      )}
    </div>
  )
}

/** The changes, in the drawer's place. */
export function WhatIfPanel() {
  const w = useWhatIf()
  const { today, setEvent } = useShell()
  const trial = useTrial(today)
  const client = useQueryClient()
  const keep = useKeep()
  const [text, setText] = useState("")
  const n = w.changes.length
  const out = trial.out
  const current = out && trial.answered === n ? out : null
  const look = current ? LOOK[current.verdict] : null
  const rule = RULE.test(text.trim())
  const tryIt = () => {
    const said = text.trim()
    if (!said) return
    whatIf.stage(rule ? "rule_add" : "add", { text: said })
    setText("")
  }
  const error = trial.error ? (trial.error instanceof ApiError || trial.error instanceof Error ? trial.error.message : String(trial.error)) : null
  const refused = (current?.changes ?? []).some((c) => c.error)
  const editEvent = (i: number) => {
    const plan = out?.plan
    const id = w.made[i]?.[0] ?? placeholder(i)
    const found = plan?.fixed.find((f) => f.id === id)
    const input = w.changes[i].input as Record<string, unknown>
    if (found) setEvent(draftOf(found))
    else if (typeof input.start === "string" && typeof input.end === "string")
      setEvent(draftOf({ id: placeholder(i), title: String(input.title ?? ""), start: input.start, end: input.end, color: null, notes: "" } as never))
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14, minHeight: 0, height: "100%" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <Icon name="flask" size={16} style={{ color: "var(--color-accent-300)" }} />
        <span className="fr-h" style={{ fontSize: 18, flex: 1 }}>
          What if
        </span>
        <button className="btn btn-icon btn-ghost" onClick={() => whatIf.showPanel(false)} aria-label="Hide the changes" title="Hide (the header still shows how it lands)" style={{ width: 26, height: 26 }}>
          <Icon name="caret-right" />
        </button>
      </div>
      <span className="fr-kicker" style={{ marginTop: -8, textWrap: "pretty" }}>
        Nothing is saved. The calendar shows your week with these changes; Keep makes them real.
      </span>
      <div style={{ height: 2, borderRadius: 2, overflow: "hidden", background: trial.planning ? "color-mix(in srgb, var(--color-accent) 15%, transparent)" : "transparent" }}>
        {trial.planning && <div className="fr-progress" style={{ height: "100%", width: "40%", background: "var(--color-accent-300)" }} />}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 14, overflowY: "auto", minHeight: 0, flex: 1, paddingBottom: 12 }}>
        {!n && (
          <span style={{ fontSize: 13, color: "var(--color-neutral-300)", textWrap: "pretty" }}>
            Try things as you normally would: drag a block, double-click to add an event, delete or move one from its drawer, add a to-do. Or type one below.
          </span>
        )}
        {n > 0 && (
          <section style={{ display: "flex", flexDirection: "column", gap: 6, opacity: current ? 1 : 0.55 }}>
            <span className="fr-eyebrow">How it lands</span>
            {error ? (
              <span style={{ fontSize: 13, color: "var(--fr-due)" }}>
                {error}{" "}
                <button className="fr-link" onClick={() => trial.refetch()}>
                  Try again
                </button>
              </span>
            ) : !out ? (
              <span className="fr-kicker">Planning your week with {n === 1 ? "it" : "them"}… about 20 seconds on a full week.</span>
            ) : (
              <>
                <span style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 13, fontWeight: 500, color: look?.ink ?? LOOK[out.verdict].ink }}>
                  <Icon name={LOOK[out.verdict].icon} size={15} style={{ flex: "none", marginTop: 2 }} />
                  <span style={{ textWrap: "pretty" }}>{out.said}.</span>
                </span>
                {(out.later ?? []).slice(0, 4).map((x) => (
                  <Line key={`l${x.item_id}`} icon="warning" ink="var(--fr-due)">
                    {x.title} <span style={{ color: "var(--color-neutral-500)" }}>+{Math.round((x.after_h - x.before_h) * 10) / 10} h past its due</span>
                  </Line>
                ))}
                {(out.later_days ?? []).slice(0, 3).map((d) => (
                  <Line key={`d${d.date}`} icon="moon" ink="var(--color-neutral-400)">
                    {dayLabel(d.date)}: work ends {d.after ? ampm(d.after) : "—"} <span style={{ color: "var(--color-neutral-500)" }}>(now {d.before ? ampm(d.before) : d.date === today ? "nothing more today" : "no work"})</span>
                  </Line>
                ))}
                {(out.notices ?? []).slice(0, 3).map((t) => (
                  <Line key={`n${t}`} icon="info" ink="var(--color-neutral-400)">
                    {t}
                  </Line>
                ))}
              </>
            )}
          </section>
        )}
        {n > 0 && (
          <section style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span className="fr-eyebrow">Trying</span>
            {w.changes.map((c, i) => {
              const said = i < trial.answered ? out?.changes[i] : undefined
              const event = c.command === "add" && (c.input as { when?: string }).when === "fixed"
              return (
                <div key={i} style={{ display: "grid", gridTemplateColumns: "18px minmax(0,1fr) auto", gap: 8, alignItems: "start", padding: "8px 0", borderBottom: "1px solid var(--fr-hairline)" }}>
                  <Icon name={ICON[c.command] ?? "dot"} size={15} style={{ color: "var(--color-accent-300)", marginTop: 1 }} />
                  <span style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: 13, minWidth: 0 }}>
                    <span style={{ textWrap: "pretty", opacity: said ? 1 : 0.7 }}>{said?.said ?? describe(c)}</span>
                    {said?.error && <span style={{ fontSize: 11.5, color: "var(--fr-due)" }}>Can’t be done: {said.error}</span>}
                    {!!said?.late?.length && <span style={{ fontSize: 11.5, color: "var(--fr-due)" }}>On its own: leaves {said.late.join(", ")} short</span>}
                  </span>
                  <span style={{ display: "flex", gap: 2 }}>
                    {event && (
                      <button className="btn btn-icon btn-ghost" onClick={() => editEvent(i)} aria-label="Edit" title="Edit this event" style={{ width: 24, height: 24 }}>
                        <Icon name="pencil-simple" size={12} />
                      </button>
                    )}
                    <button className="btn btn-icon btn-ghost" onClick={() => whatIf.remove(i)} aria-label="Take this out" title="Take this out" style={{ width: 24, height: 24 }}>
                      <Icon name="x" size={12} />
                    </button>
                  </span>
                </div>
              )
            })}
          </section>
        )}
        <section style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span className="fr-eyebrow">Try something</span>
          <div style={{ display: "flex", gap: 6 }}>
            <input className="input" value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && tryIt()} placeholder="An event, a to-do or a rule" aria-label="Something to try" style={{ flex: 1, minWidth: 0, fontSize: 13 }} />
            <button className="btn btn-secondary" onClick={tryIt} disabled={!text.trim()} style={{ fontSize: 12 }}>
              {rule ? "Try rule" : "Try"}
            </button>
          </div>
          <span style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {EXAMPLES.map((x) => (
              <button key={x} className="fr-chip" onClick={() => setText(x)} style={{ fontSize: 11.5, color: "var(--color-neutral-300)" }}>
                {x}
              </button>
            ))}
          </span>
        </section>
      </div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", padding: "10px 0 14px", borderTop: "1px solid var(--fr-hairline)" }}>
        <button className="btn btn-ghost" onClick={() => discard(client)}>
          {n ? "Discard" : "Leave What if"}
        </button>
        <span style={{ flex: 1 }} />
        {n > 0 && (
          <button className="btn btn-primary" onClick={keep} disabled={trial.planning || refused || !current} title={refused ? "Take out what can’t be done first" : "One Undo takes them all back"}>
            <Icon name="check" />
            Keep {n === 1 ? "it" : `all ${n}`}
          </button>
        )}
      </div>
    </div>
  )
}

const ICON: Record<string, string> = { add: "plus-circle", series_add: "repeat", edit: "pencil-simple", pin: "arrows-out-cardinal", unpin: "push-pin-slash", skip: "x-circle", drop: "trash", shove: "hand-palm", rule_add: "list-checks", day_override: "calendar-dots" }

function Line({ icon, ink, children }: { icon: string; ink: string; children: React.ReactNode }) {
  return (
    <span style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 12.5, paddingLeft: 2, textWrap: "pretty" }}>
      <Icon name={icon} size={13} style={{ color: ink, flex: "none", marginTop: 2 }} />
      <span>{children}</span>
    </span>
  )
}

/** A change in words before the server has said it. */
function describe(c: Change): string {
  const input = c.input as Record<string, unknown>
  const named = (input.text ?? input.title) as string | undefined
  const when = typeof input.start === "string" ? ` · ${dayLabel(input.start.slice(0, 10))} ${ampm(input.start.slice(11, 16))}` : ""
  const verb: Record<string, string> = { add: "Add", series_add: "Add", edit: "Change", pin: "Move a block", unpin: "Let Friday place a block", skip: "Skip an event", drop: "Delete an item", shove: "Keep a stretch free", rule_add: "Rule:", day_override: "Change a day" }
  return `${verb[c.command] ?? c.command}${named ? ` ${named}` : ""}${when}`
}
