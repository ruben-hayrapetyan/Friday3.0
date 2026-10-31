// The v22 dialogs: the morning brief, what gives when it can't all fit (triage), and locks that make work late.

import { useQuery, useQueryClient } from "@tanstack/react-query"
import { type ReactNode, type RefObject, useEffect, useRef, useState } from "react"
import { command, query, type Schemas } from "@/api/client"
import { Box, H, Icon, Seg } from "@/components/fr/controls"
import { useToast } from "@/components/Toasts"
import { runTogether, undoAll, useCommand } from "@/hooks/useCommand"
import { useHorizon, usePaces, useSettings } from "@/hooks/queries"
import { clock, dur, when } from "@/lib/format"
import { nextBlocks } from "@/lib/todo"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"
import { dayName } from "@/inbox/messages"

/** A dialog takes the keys while it's open: Esc closes it, and Tab starts inside it (the audit, 31 Oct). */
export function useDialogKeys(onClose: () => void): RefObject<HTMLDivElement | null> {
  const box = useRef<HTMLDivElement>(null)
  const close = useRef(onClose)
  close.current = onClose
  useEffect(() => {
    if (!box.current?.contains(document.activeElement)) box.current?.focus({ preventScroll: true })
    const press = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !e.defaultPrevented) close.current()
    }
    window.addEventListener("keydown", press)
    return () => window.removeEventListener("keydown", press)
  }, [])
  return box
}

export function Modal({ onClose, children, top, width = 560 }: { onClose: () => void; children: ReactNode; top?: boolean; width?: number }) {
  const box = useDialogKeys(onClose)
  return (
    <div className="fr-scrim" style={top ? { alignItems: "flex-start", padding: "56px 24px 24px", background: "color-mix(in srgb, #05070b 60%, transparent)" } : undefined}>
      <div onClick={onClose} style={{ position: "absolute", inset: 0 }} />
      <div ref={box} tabIndex={-1} role="dialog" aria-modal="true" className="fr-float fr-dialog" style={{ width: `min(${width}px, 100%)`, outline: "none" }}>
        {children}
      </div>
    </div>
  )
}

function Close({ onClose }: { onClose: () => void }) {
  return (
    <button className="btn btn-icon btn-ghost" onClick={onClose} aria-label="Close" style={{ width: 28, height: 28, color: "var(--color-neutral-400)" }}>
      <Icon name="x" />
    </button>
  )
}

/** The brief's switch, kept with your settings (Settings → Schedule, and setup's question): `notify.morning_brief`. */
export function useBriefSwitch(): [boolean | undefined, (on: boolean) => void] {
  const notify = (useSettings().data as Record<string, unknown> | undefined)?.notify as { morning_brief: boolean } | undefined
  const save = useCommand("settings_set", { label: () => "Saved" })
  return [notify?.morning_brief, (on) => save({ key: "notify", value: { ...notify, morning_brief: on } })]
}

export function BriefDialog({ onClose }: { onClose: () => void }) {
  const { today } = useShell()
  const { color } = useLook()
  const brief = useQuery({ queryKey: ["brief"], queryFn: () => query("brief") }).data
  const blocks = useHorizon().data?.blocks ?? []
  const paces = usePaces().data
  const pace = useCommand("pace", { label: (o) => o.result.message })
  const start = useCommand("start", { label: () => "Started" })
  const [auto, setAuto] = useBriefSwitch()
  const next = nextBlocks(blocks.filter((b) => b.start.startsWith(today)))
  const first = brief?.rocks.map((r) => next.get(r.item_id)).find(Boolean)
  return (
    <Modal onClose={onClose} top width={720}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 6 }}>
          <span style={{ fontSize: 13, color: "var(--color-neutral-400)" }}>{dayName(today)}</span>
          <H size={40} style={{ lineHeight: 0.95 }}>
            Good morning
          </H>
          <span style={{ fontSize: 15, color: "var(--color-neutral-200)", textWrap: "pretty", maxWidth: 560 }}>{brief?.summary}</span>
        </div>
        <Close onClose={onClose} />
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <span className="fr-kicker">What matters today</span>
        {brief?.rocks.map((r) => {
          const b = next.get(r.item_id)
          return (
            <div key={r.item_id} style={{ display: "grid", gridTemplateColumns: "4px minmax(0,1fr) auto", gap: 14, alignItems: "center", padding: "12px 14px 12px 0", borderRadius: "var(--radius-md)", background: "var(--color-bg)" }}>
              <span style={{ alignSelf: "stretch", borderRadius: "0 2px 2px 0", background: color(b?.area, b?.preset) }} />
              <span style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
                <H size={18} style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {r.title}
                </H>
                <span style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>{r.due ? `${r.hard ? "Hard deadline" : "Due"} ${when(r.due, today)}` : "No due date"}</span>
              </span>
              <span className="tnum" style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 1 }}>
                <span style={{ fontWeight: 500 }}>{b ? `${clock(b.start)}–${clock(b.end)}` : "not today"}</span>
                <span className="fr-kicker">{r.planned_min ? dur(r.planned_min) : ""}</span>
              </span>
            </div>
          )
        })}
        {brief && !brief.rocks.length && <span style={{ color: "var(--color-neutral-400)" }}>Nothing big today.</span>}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0,1fr))", gap: 24 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span className="fr-kicker">Fixed today</span>
          {brief?.fixed.map((f) => (
            <div key={f.id} className="fr-row" style={{ display: "grid", gridTemplateColumns: "52px minmax(0,1fr)", gap: 10, padding: "6px 0" }}>
              <span className="tnum" style={{ color: "var(--color-neutral-300)" }}>
                {f.start ? clock(f.start) : ""}
              </span>
              <span>{f.title}</span>
            </div>
          ))}
          {brief && !brief.fixed.length && <span style={{ color: "var(--color-neutral-500)" }}>Nothing fixed.</span>}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span className="fr-kicker">Heads up</span>
          {brief?.alerts.map((a) => (
            <div key={`${a.item_id}${a.kind}`} className="fr-row" style={{ display: "grid", gridTemplateColumns: "16px minmax(0,1fr)", gap: 10, alignItems: "start", padding: "6px 0" }}>
              <Icon name="warning" size={14} style={{ color: "var(--fr-warn)", marginTop: 2 }} />
              <span>
                {a.title}: start by {when(a.latest_start, today)}
              </span>
            </div>
          ))}
          {brief && !brief.alerts.length && <span style={{ color: "var(--color-neutral-500)" }}>Nothing pressing.</span>}
        </div>
      </div>
      {brief?.sleep && (
        // Tracked sleep: a short night, and the Easy day to answer it with.
        <div className="fr-well" style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 12px", marginTop: 12 }}>
          <Icon name="moon" size={16} style={{ color: "var(--color-accent-300)", flex: "none" }} />
          <span style={{ flex: 1, textWrap: "pretty" }}>{brief.sleep}</span>
          <button className="btn btn-secondary" onClick={() => pace({ name: "Easy", for_days: 1 })} style={{ fontSize: 12 }}>
            Easy today
          </button>
        </div>
      )}
      <div className="fr-row" style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", paddingTop: 16 }}>
        <span className="fr-kicker">Pace today</span>
        {paces && <Seg options={Object.keys(paces.paces)} value={paces.now_label} onPick={(p) => pace({ name: p, for_days: 1 })} />}
        <span className="fr-kicker" style={{ flex: 1, minWidth: 160 }}>
          {brief?.pace ?? "Deadlines hold whatever you pick."}
        </span>
        <button className="btn btn-ghost" onClick={onClose}>
          See the plan
        </button>
        {first && (
          <button className="btn btn-primary" onClick={() => (start({ id: first.item_id }), onClose())}>
            <Icon name="play" />
            Start {first.title}
          </button>
        )}
      </div>
      <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--color-neutral-500)", cursor: "pointer" }}>
        <input
          type="checkbox"
          checked={auto ?? true}
          onChange={(e) => setAuto(e.target.checked)}
          style={{ accentColor: "var(--color-accent)" }}
        />
        Show this when I open Friday each morning
      </label>
    </Modal>
  )
}

/** Whether the brief should open by itself: once a morning on this device, while its switch is on. */
export function briefDue(today: string): boolean {
  try {
    if (localStorage.getItem("friday-brief-shown") === today) return false
    localStorage.setItem("friday-brief-shown", today)
  } catch {
    return false // storage blocked: don't open it on every load
  }
  return new Date().getHours() < 12
}

/** An event you could skip (personal's Going | Skip switch, large): skipping keeps it on your calendar and only stops
 * it blocking time; Going means Friday stops asking about it. Either happens at once and says so on the row (30 Oct:
 * "when it says skip salsa... and it says going/skip, neither of those buttons work": Going waited on the options
 * being worked out again, and Skip only marked it for Apply). */
type Said = "working" | "skipped" | "going"
function SkipRow({ option, said, onSkip, onGoing }: { option: Schemas["TriageOption"]; said?: Said; onSkip: () => void; onGoing: () => void }) {
  return (
    <div className="fr-hover" style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto auto", gap: 12, alignItems: "center", padding: 12, borderRadius: "var(--radius-md)", background: said === "skipped" ? "color-mix(in srgb, var(--color-accent) 10%, transparent)" : undefined, opacity: said === "going" ? 0.6 : 1 }}>
      <span style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
        <span style={{ fontWeight: 500 }}>{option.action}</span>
        <span style={{ fontSize: 12, color: "var(--color-neutral-400)", textWrap: "pretty" }}>
          {said === "going" ? "You’re going: Friday won’t suggest skipping it again" : said === "skipped" ? "Skipped: it stays on your calendar, and Friday plans work over it" : option.side_effects?.join("; ")}
        </span>
      </span>
      <span className="tnum" style={{ fontSize: 13, fontWeight: 500, color: "var(--color-accent-300)", whiteSpace: "nowrap" }}>
        −{option.late_hours_saved} h
      </span>
      <span className="fr-seg big" role="group" aria-label={`Going to ${option.skip_title}?`}>
        <button aria-pressed={said === "going"} onClick={onGoing} disabled={!!said} title="You go to it: Friday stops suggesting it">
          Going
        </button>
        <button aria-pressed={said === "skipped"} onClick={onSkip} disabled={!!said} title="Skip it this time: it stays on your calendar">
          Skip
        </button>
      </span>
    </div>
  )
}

export function TriageDialog({ onClose }: { onClose: () => void }) {
  // Several quick replans on the server, so a few seconds.
  const triage = useQuery({ queryKey: ["triage"], queryFn: () => query("triage"), staleTime: 0 })
  const client = useQueryClient()
  const toast = useToast()
  const [chosen, setChosen] = useState<string[]>([])
  const [said, setSaid] = useState<Record<string, Said>>({}) // the events answered, by option
  const say = (action: string, to: Said | null) =>
    setSaid((was) => {
      const next = { ...was }
      if (to) next[action] = to
      else delete next[action]
      return next
    })
  const data = triage.data
  const late = data ? Object.values(data.late).reduce((s, h) => s + h, 0) : 0
  const options = data?.options ?? []
  const counted = options.filter((o) => chosen.includes(o.action) || said[o.action] === "skipped")
  const saved = Math.min(late, counted.reduce((s, o) => s + o.late_hours_saved, 0))
  const best = options.reduce<Schemas["TriageOption"] | null>((b, o) => (!b || o.late_hours_saved > b.late_hours_saved ? o : b), null)
  // An option may take several commands (a night override per day); they apply, and undo, together.
  const [applying, setApplying] = useState(false)
  const apply = async () => {
    if (applying) return // a second click doesn't apply them twice
    setApplying(true)
    const ids = await runTogether(client, toast, options.filter((x) => chosen.includes(x.action)).flatMap((o) => o.steps))
    setApplying(false)
    if (!ids) return
    toast({ message: chosen.join(", "), action: { label: "Undo", run: () => undoAll(client, toast, ids) } })
    client.invalidateQueries()
    onClose()
  }
  const toggle = (a: string) => setChosen(chosen.includes(a) ? chosen.filter((x) => x !== a) : [...chosen, a])
  // "I'm going": never offered again (COMBINED.md 56). Said on the row at once; the options are worked out again
  // behind it.
  const going = async (o: Schemas["TriageOption"]) => {
    say(o.action, "going")
    try {
      const out = await command("event_going", { title: o.skip_title as string })
      toast({ message: out.result.message ?? `Won’t suggest skipping ${o.skip_title}` })
    } catch (error) {
      say(o.action, null)
      toast({ message: error instanceof Error ? error.message : String(error), tone: "error" })
    }
    client.invalidateQueries({ queryKey: ["triage"] })
  }
  // Skipping it this time: done at once, with an undo.
  const skip = async (o: Schemas["TriageOption"]) => {
    say(o.action, "working")
    const ids = await runTogether(client, toast, o.steps)
    if (!ids) return say(o.action, null)
    say(o.action, "skipped")
    toast({ message: `${o.action}: it stays on your calendar`, action: { label: "Undo", run: () => (say(o.action, null), undoAll(client, toast, ids)) } })
    client.invalidateQueries({ queryKey: ["plan"] })
  }
  return (
    <Modal onClose={onClose}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 4 }}>
          <H size={26} style={{ lineHeight: 1.05 }}>
            {triage.isLoading ? "Working out what could give" : late ? `${late.toFixed(1)} h of work won’t make it` : "Everything fits"}
          </H>
          <span style={{ color: "var(--color-neutral-300)", textWrap: "pretty" }}>
            {data && late ? `Late now: ${Object.entries(data.late).map(([t, h]) => `${t} (${h} h)`).join(", ")}. Each option was tried on a copy of your plan.` : triage.isLoading ? "Trying options…" : "Nothing is going late."}
          </span>
        </div>
        <Close onClose={onClose} />
      </div>
      {late > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <div className="tnum" style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
            <span style={{ color: "var(--color-neutral-300)" }}>{late.toFixed(1)} h late now</span>
            <span style={{ color: saved >= late ? "var(--color-accent-300)" : "var(--fr-warn)" }}>{counted.length ? `${(late - saved).toFixed(1)} h late after these` : "Pick what gives"}</span>
          </div>
          <div style={{ position: "relative", height: 8, borderRadius: 4, background: "color-mix(in srgb, var(--color-text) 8%, transparent)", overflow: "hidden" }}>
            <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${(saved / late) * 100}%`, background: saved >= late ? "var(--color-accent)" : "var(--fr-warn)" }} />
          </div>
        </div>
      )}
      {triage.error && <span style={{ color: "var(--fr-due)" }}>{triage.error.message}</span>}
      {options.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span className="fr-kicker" style={{ paddingBottom: 2 }}>
            Best options first. Pick one or combine them.
          </span>
          {options.map((o) =>
            o.skip_title ? (
              <SkipRow key={o.action} option={o} said={said[o.action]} onSkip={() => skip(o)} onGoing={() => going(o)} />
            ) : (
            <button
              key={o.action}
              onClick={() => toggle(o.action)}
              disabled={o.late_hours_saved <= 0}
              className="fr-plain fr-hover"
              style={{ display: "grid", gridTemplateColumns: "18px minmax(0,1fr) auto", gap: 12, alignItems: "center", padding: 12, borderRadius: "var(--radius-md)", background: chosen.includes(o.action) ? "color-mix(in srgb, var(--color-accent) 10%, transparent)" : undefined }}
            >
              <Box on={chosen.includes(o.action)} />
              <span style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
                <span style={{ display: "flex", gap: 8, alignItems: "center", fontWeight: 500 }}>
                  {o.action}
                  {o === best && <span className="fr-tag accent">Best fit</span>}
                </span>
                <span style={{ fontSize: 12, color: "var(--color-neutral-400)", textWrap: "pretty" }}>{o.side_effects?.join("; ") || "Nothing else changes."}</span>
              </span>
              <span className="tnum" style={{ fontSize: 13, fontWeight: 500, color: o.late_hours_saved > 0 ? "var(--color-accent-300)" : "var(--color-neutral-500)", whiteSpace: "nowrap" }}>
                −{o.late_hours_saved} h
              </span>
            </button>
            ),
          )}
        </div>
      )}
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <span className="fr-kicker" style={{ flex: 1 }}>
          Every change can be undone from the plan.
        </span>
        <button className="btn btn-ghost" onClick={onClose}>
          Cancel
        </button>
        <button className="btn btn-primary" onClick={apply} disabled={!chosen.length || applying}>
          Apply {chosen.length > 1 ? `${chosen.length} changes` : ""}
        </button>
      </div>
    </Modal>
  )
}
