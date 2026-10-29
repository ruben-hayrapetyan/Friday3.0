// The Now dock (v22): what you're doing right now. Timing something: the seconds ticking, how long the plan gives
// it and what's next, with Done, Pause, Switch and more. In a planned block: Start and Done (no More time:
// COMBINED.md 31). In a class:
// the class. Free: how long, what's next, and the best things to start, one tap each. The timer is an overlay on
// the plan, never a change to it (DESIGN §8), so Start and Pause move nothing on the calendar. With sleep tracking on
// (Settings → Schedule), a slim row on top offers the tap that fits the hour: I'm up, Ready to work, Done with work
// (with Going to bed beside it, for a night you go straight to bed), then Going to bed; with
// meal tracking on, another offers Eating now around a mealtime (or Skip), and Done eating while you eat. Napping, a
// row says since when, with I'm up; More and free time offer a nap and a snack (`breaks.ts`).

import { useState } from "react"
import { useNavigate } from "react-router"
import type { Block } from "@/api/client"
import { Icon } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useClock, useElapsed } from "@/hooks/useClock"
import { EstimateNudge } from "@/components/EstimateNudge"
import { TimeInput } from "@/components/fr/TimeInput"
import { spanOn } from "@/lib/ampm"
import { useItem, useMeals, useNow, useSleep, useStatus } from "@/hooks/queries"
import { clock, dur, hms, span, when } from "@/lib/format"
import { fromMin, toMin } from "@/lib/time"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"
import { useBreaks } from "./breaks"

type Menu = "time" | "more" | "swap" | null
type Fit = { item_id: number; title: string; minutes: number }

export function Dock() {
  const now = useNow().data
  const timer = useStatus().data?.timer ?? null
  const today = fromMin(useClock()).slice(0, 10)
  const { look, color } = useLook()
  const [menu, setMenu] = useState<Menu>(null)
  const toggle = (m: Exclude<Menu, null>) => setMenu(menu === m ? null : m)
  if (!now) return null
  const cur = now.current
  const next = now.next ? `${now.next.title} ${when(now.next.start, today)}` : "nothing else today"
  const compact = look.dockStyle === "Minimal"
  const work = !!cur && !cur.fixed
  const room = "100% - var(--fr-side) - var(--fr-drawer) - 12px" // beside the sidebar and any drawer (Shell's variables)
  return (
    <div
      className="fr-float"
      data-tour="now"
      style={{
        position: "absolute",
        left: `calc(var(--fr-side) + (${room}) / 2)`,
        bottom: 18,
        transform: "translateX(-50%)",
        width: `min(${compact ? 540 : 780}px, calc(${room} - 16px))`,
        zIndex: 8,
        borderRadius: compact ? 26 : "var(--radius-lg)",
        overflow: "hidden",
      }}
    >
      {work && menu === "more" && <MoreMenu itemId={cur.item_id} onSwitch={() => setMenu("swap")} onClose={() => setMenu(null)} />}
      <SleepTap />
      <MealTap />
      {cur && timer && timer.item_id === cur.item_id ? (
        <Timing cur={cur} elapsed={timer.elapsed_s ?? 0} started={timer.started ?? null} next={next} dot={color(cur.area, cur.preset)} compact={compact} menu={menu} onMenu={toggle} />
      ) : cur?.fixed ? (
        <InEvent cur={cur} next={next} dot={color(cur.area, cur.preset)} />
      ) : cur ? (
        <On cur={cur} next={next} dot={color(cur.area, cur.preset)} compact={compact} menu={menu} onMenu={toggle} />
      ) : (
        <Free until={now.next?.start ?? null} gap={now.gap_minutes} next={now.next?.title ?? null} fits={now.fits} today={today} />
      )}
      {work && menu === "swap" && <Swaps options={now.swaps} onClose={() => setMenu(null)} />}
    </div>
  )
}

const TAPS = {
  up: { icon: "sun-horizon", ask: "Just up?", button: "I'm up" },
  ready: { icon: "coffee", ask: "Morning routine done?", button: "Ready to work" },
  done: { icon: "laptop", ask: "Done with work for the night?", button: "Done with work" },
  bed: { icon: "moon", ask: "Heading to sleep?", button: "Going to bed" },
} as const

/** Tracked sleep's one tap, when there's one to make; Friday learns your nights, mornings and evenings from them.
 * Napping, the nap and I'm up instead. */
function SleepTap() {
  const sleep = useSleep().data
  const mark = useCommand("sleep_mark", { label: (o) => o.result.message ?? "Saved" })
  const up = useCommand("nap_end", { label: (o) => o.result.message ?? "Saved" })
  const [busy, setBusy] = useState(false)
  const nowMin = useClock()
  if (sleep?.on && sleep.napping) {
    const since = sleep.napping.start
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 14px 6px 18px", boxShadow: "inset 0 -1px 0 var(--fr-hairline)", fontSize: 12, color: "var(--color-neutral-400)" }}>
        <Icon name="bed" size={14} style={{ color: "var(--color-accent-300)" }} />
        <span className="tnum" style={{ flex: 1 }}>
          Napping since {clock(since)} · {dur(Math.max(1, nowMin - toMin(since)))}
        </span>
        <button className="btn btn-secondary fr-press" disabled={busy} onClick={async () => (setBusy(true), await up({}), setBusy(false))} style={{ fontSize: 12, padding: "2px 10px" }}>
          I'm up
        </button>
      </div>
    )
  }
  if (!sleep?.on || !sleep.next) return null
  const kind = sleep.next
  const tap = TAPS[kind]
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 14px 6px 18px", boxShadow: "inset 0 -1px 0 var(--fr-hairline)", fontSize: 12, color: "var(--color-neutral-400)" }}>
      <Icon name={tap.icon} size={14} style={{ color: "var(--color-accent-300)" }} />
      <span style={{ flex: 1 }}>{tap.ask}</span>
      {kind === "done" && (
        <button className="fr-link" disabled={busy} onClick={async () => (setBusy(true), await mark({ kind: "bed" }), setBusy(false))} style={{ fontSize: 12 }}>
          Going to bed
        </button>
      )}
      <button className="btn btn-secondary fr-press" disabled={busy} onClick={async () => (setBusy(true), await mark({ kind }), setBusy(false))} style={{ fontSize: 12, padding: "2px 10px" }}>
        {tap.button}
      </button>
    </div>
  )
}

const MEAL_ICON: Record<string, string> = { breakfast: "coffee", lunch: "bowl-food", dinner: "fork-knife", snack: "cookie" }

/** Tracked meals' tap: Eating now when it's a meal's time, Done eating while you eat (the plan keeps your meal free). */
function MealTap() {
  const meals = useMeals().data
  const start = useCommand("meal_start", { label: (o) => o.result.message ?? "Saved" })
  const end = useCommand("meal_end", { label: (o) => o.result.message ?? "Saved" })
  const skip = useCommand("meal_skip", { label: (o) => o.result.message ?? "Saved" })
  const [busy, setBusy] = useState(false)
  const nowMin = useClock()
  if (!meals?.on || !(meals.eating || meals.next)) return null
  const run = async (act: () => Promise<unknown>) => (setBusy(true), await act(), setBusy(false))
  const kind = meals.eating?.kind ?? meals.next ?? "snack"
  const since = meals.eating?.start
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 14px 6px 18px", boxShadow: "inset 0 -1px 0 var(--fr-hairline)", fontSize: 12, color: "var(--color-neutral-400)" }}>
      <Icon name={MEAL_ICON[kind] ?? "fork-knife"} size={14} style={{ color: "var(--color-accent-300)" }} />
      {since ? (
        <>
          <span className="tnum" style={{ flex: 1 }}>
            Eating {kind} since {clock(since)} · {dur(Math.max(1, nowMin - toMin(since)))}
          </span>
          <button className="btn btn-secondary fr-press" disabled={busy} onClick={() => run(() => end({}))} style={{ fontSize: 12, padding: "2px 10px" }}>
            Done eating
          </button>
        </>
      ) : (
        <>
          <span style={{ flex: 1 }}>{kind[0].toUpperCase() + kind.slice(1)}?</span>
          <button className="fr-link" disabled={busy} onClick={() => run(() => skip({ kind: kind as "breakfast" | "lunch" | "dinner" }))} style={{ fontSize: 12 }}>
            Skip
          </button>
          <button className="btn btn-secondary fr-press" disabled={busy} onClick={() => run(() => start({ kind: kind as "breakfast" | "lunch" | "dinner" }))} style={{ fontSize: 12, padding: "2px 10px" }}>
            Eating now
          </button>
        </>
      )}
    </div>
  )
}

interface State {
  cur: Block
  next: string
  dot: string
  compact: boolean
  menu: Menu
  onMenu: (m: Exclude<Menu, null>) => void
}

const row = { display: "flex", alignItems: "center", gap: 14, padding: "10px 14px 12px 18px" } as const
const column = { display: "flex", flexDirection: "column", minWidth: 0, flex: 1 } as const
const kicker = { display: "flex", gap: 6, alignItems: "center", fontSize: 12, color: "var(--color-neutral-400)", whiteSpace: "nowrap", overflow: "hidden" } as const
const dim = { overflow: "hidden", textOverflow: "ellipsis", color: "var(--color-neutral-500)" } as const
const buttons = { display: "flex", gap: 6, flex: "none" } as const
const titleStyle = (compact: boolean) => ({ fontSize: compact ? 17 : 22, lineHeight: 1.05, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }) as const
const clamp = (x: number) => Math.max(0, Math.min(100, x))
const share = (cur: Block, nowMin: number) => clamp(((nowMin - toMin(cur.start)) / Math.max(1, toMin(cur.end) - toMin(cur.start))) * 100)

/** The timer running on what you're doing: the seconds, the plan's room for it, then what's next. */
function Timing({ cur, elapsed, started, next, dot, compact, menu, onMenu }: State & { elapsed: number; started: string | null }) {
  const seconds = useElapsed(elapsed)
  const nowMin = useClock()
  const pause = useCommand("stop", { label: (o) => o.result.message ?? "Paused" })
  const finish = useCommand("stop", { label: (o) => o.result.message ?? "Done" })
  const left = toMin(cur.end) - nowMin
  return (
    <>
      <Bar pct={share(cur, nowMin)} live />
      <div style={row}>
        <div style={column}>
          <div style={kicker}>
            <Pulse color={dot} />
            <span className="tnum">Timing since {clock(cur.start)}</span>
            <span style={dim}>
              · {left > 0 ? `${span(left)} left` : "past its time"} · then {next}
            </span>
          </div>
          <div className="fr-h" title={cur.title} style={titleStyle(compact)}>
            {cur.title}
          </div>
        </div>
        <span className="tnum" style={{ flex: "none", fontSize: compact ? 20 : 26, fontWeight: 500, letterSpacing: "-0.02em", color: "var(--color-accent-200)", minWidth: compact ? 56 : 84, textAlign: "right" }}>
          {hms(seconds)}
        </span>
        <div style={buttons}>
          <button className="btn btn-primary" onClick={() => finish({ done: true })} title="Stop the timer and mark it done" style={{ whiteSpace: "nowrap" }}>
            <Icon name="check" size={15} />
            {!compact && "Done"}
          </button>
          <IconButton icon="pause" label="Pause the timer (Space)" onClick={() => pause({})} />
          <IconButton icon="swap" label="Do something else" on={menu === "swap"} onClick={() => onMenu("swap")} />
          <IconButton icon="dots-three" label="More" on={menu === "more"} onClick={() => onMenu("more")} />
        </div>
      </div>
      {/* Started and finding it's longer (or shorter) than you thought: the estimate, a tap from here. */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 14px 10px 18px", fontSize: 12, color: "var(--color-neutral-400)" }}>
        <EstimateNudge itemId={cur.item_id} runningMin={seconds / 60} />
        {started && <ForgotToStop started={started} />}
      </div>
    </>
  )
}

/** A timer left running (28 Oct: "what if i forgot to turn the timer off"): stop it as of when you really stopped, so
 * only that counts as done and as how long it took. */
function ForgotToStop({ started }: { started: string }) {
  const [open, setOpen] = useState(false)
  const [at, setAt] = useState("")
  const stop = useCommand("stop", { label: (o) => o.result.message ?? "Stopped" })
  const end = (done: boolean) => {
    if (!at) return
    stop({ at: spanOn(started.slice(0, 10), started.slice(11, 16), at).end, done })
    setOpen(false)
  }
  if (!open)
    return (
      <button className="fr-link" onClick={() => setOpen(true)} style={{ marginLeft: "auto", fontSize: 12 }}>
        Forgot to stop?
      </button>
    )
  return (
    <span role="group" aria-label="When you stopped" onKeyDown={(e) => e.key === "Enter" && end(false)} style={{ marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 6 }}>
      Stopped at
      <TimeInput value={at} onChange={setAt} label="Stopped at" expect={{ after: started.slice(11, 16) }} style={{ width: 92, padding: "2px 8px", minHeight: 0, fontSize: 12 }} />
      <button className="btn btn-secondary" disabled={!at} onClick={() => end(false)} style={{ fontSize: 12, padding: "2px 8px", minHeight: 0 }}>
        Stop then
      </button>
      <button className="btn btn-secondary" disabled={!at} onClick={() => end(true)} style={{ fontSize: 12, padding: "2px 8px", minHeight: 0 }}>
        Done then
      </button>
      <button className="fr-link" onClick={() => setOpen(false)} style={{ fontSize: 12 }}>
        Cancel
      </button>
    </span>
  )
}

/** In a planned block, not timing it yet. */
function On({ cur, next, dot, compact, menu, onMenu }: State) {
  const nowMin = useClock()
  const start = useCommand("start", { label: (o) => o.result.message ?? "Timing" })
  const done = useCommand("done", { label: () => `${cur.title}: done` })
  const worked = useItem(cur.item_id).data?.item.done_min ?? 0 // some done already: Resume, not Start
  return (
    <>
      <Bar pct={share(cur, nowMin)} />
      <div style={row}>
        <div style={column}>
          <div style={kicker}>
            <span style={{ flex: "none", width: 6, height: 6, borderRadius: "50%", background: dot }} />
            <span className="tnum">
              Now {clock(cur.start)}–{clock(cur.end)}
            </span>
            <span style={dim}>· then {next}</span>
          </div>
          <div className="fr-h" title={cur.title} style={titleStyle(compact)}>
            {cur.title}
          </div>
        </div>
        <span className="tnum" style={{ flex: "none", fontSize: compact ? 16 : 20, fontWeight: 500, letterSpacing: "-0.02em", whiteSpace: "nowrap" }}>
          {span(toMin(cur.end) - nowMin)} left
        </span>
        <div style={buttons}>
          <button className="btn btn-primary" onClick={() => start({ id: cur.item_id })} title={worked ? `Resume the timer: ${dur(worked)} done so far (Space)` : "Start the timer (Space)"} style={{ whiteSpace: "nowrap" }}>
            <Icon name="play" size={14} fill />
            {!compact && (worked ? "Resume" : "Start")}
          </button>
          <IconButton icon="check" label="Mark it done" onClick={() => done({ id: cur.item_id })} />
          <IconButton icon="dots-three" label="More" on={menu === "more"} onClick={() => onMenu("more")} />
        </div>
      </div>
    </>
  )
}

/** In a class or other fixed event: where you are, until when, and what's after. */
function InEvent({ cur, next, dot }: { cur: Block; next: string; dot: string }) {
  const nowMin = useClock()
  return (
    <>
      <Bar pct={share(cur, nowMin)} muted />
      <div style={row}>
        <div style={column}>
          <div style={kicker}>
            <span style={{ flex: "none", width: 6, height: 6, borderRadius: "50%", background: dot }} />
            <span className="tnum">Now, until {clock(cur.end)}</span>
            <span style={dim}>· then {next}</span>
          </div>
          <div className="fr-h" title={cur.title} style={titleStyle(false)}>
            {cur.title}
          </div>
        </div>
        <span className="tnum" style={{ flex: "none", fontSize: 18, fontWeight: 500, whiteSpace: "nowrap" }}>
          {span(toMin(cur.end) - nowMin)} left
        </span>
      </div>
    </>
  )
}

interface FreeProps {
  until: string | null
  gap: number
  next: string | null
  fits: Fit[]
  today: string
}

/** Nothing on: how long you're free, what's next, and what to start, one tap each. */
function Free({ until, gap, next, fits, today }: FreeProps) {
  const start = useCommand("start", { label: (o) => o.result.message ?? "Timing" })
  const breaks = useBreaks()
  const quiet = { fontSize: 12, display: "inline-flex", gap: 4, alignItems: "center" } as const
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "12px 14px 12px 18px" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, minWidth: 0 }}>
        <span className="fr-h" style={{ fontSize: 22, lineHeight: 1.05, whiteSpace: "nowrap" }}>
          {until ? `Free until ${when(until, today)}` : "Free for the rest of today"}
        </span>
        {until && gap > 0 && (
          <span className="tnum" style={{ fontSize: 13, color: "var(--color-neutral-400)", whiteSpace: "nowrap" }}>
            {dur(gap)}
          </span>
        )}
        <span style={{ flex: 1 }} />
        {next && <span style={{ ...dim, fontSize: 12, whiteSpace: "nowrap", minWidth: 0 }}>then {next}</span>}
      </div>
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
        {fits.length ? (
          <>
            <span style={{ fontSize: 12, color: "var(--color-neutral-400)", marginRight: 2 }}>Start now:</span>
            {fits.slice(0, 3).map((f, n) => (
              <button
                key={f.item_id}
                className={n === 0 ? "btn btn-primary" : "btn btn-secondary"}
                onClick={() => start({ id: f.item_id })}
                title="Starts the timer; the plan stays as it is"
                style={{ whiteSpace: "nowrap", boxShadow: "none", padding: "4px 10px", background: n === 0 ? undefined : "var(--fr-chip-bg)" }}
              >
                {n === 0 && <Icon name="play" size={13} fill />}
                {f.title}
                <span className="tnum" style={{ opacity: 0.65 }}>
                  {dur(f.minutes)}
                </span>
              </button>
            ))}
          </>
        ) : (
          <span style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>Nothing needs this time. It's yours.</span>
        )}
        <span style={{ flex: 1 }} />
        {breaks.nap && (
          <button className="fr-link" onClick={breaks.nap} title="Taking a nap: the plan keeps the time clear" style={quiet}>
            <Icon name="bed" size={12} />
            Nap
          </button>
        )}
        {breaks.snack && (
          <button className="fr-link" onClick={breaks.snack} title="Having a snack: the plan keeps the time clear" style={{ ...quiet, marginLeft: 8 }}>
            <Icon name="cookie" size={12} />
            Snack
          </button>
        )}
      </div>
    </div>
  )
}

function Bar({ pct, live, muted }: { pct: number; live?: boolean; muted?: boolean }) {
  const color = muted ? "var(--color-neutral-500)" : "var(--color-accent)"
  return (
    <div style={{ height: 2, background: "color-mix(in srgb, var(--color-text) 6%, transparent)" }}>
      <div style={{ height: "100%", width: `${pct}%`, background: color, boxShadow: live ? "0 0 calc(12px * var(--g-dock)) calc(2px * var(--g-dock)) var(--color-accent)" : undefined }} />
    </div>
  )
}

function Pulse({ color }: { color: string }) {
  return <span style={{ flex: "none", width: 8, height: 8, borderRadius: "50%", background: color, boxShadow: `0 0 0 3px color-mix(in srgb, ${color} 30%, transparent)` }} />
}

function IconButton({ icon, label, on, onClick }: { icon: string; label: string; on?: boolean; onClick: () => void }) {
  return (
    <button
      className="btn btn-icon btn-secondary"
      onClick={onClick}
      aria-label={label}
      title={label}
      style={{ boxShadow: "none", background: on ? "color-mix(in srgb, var(--color-accent) 18%, transparent)" : "var(--fr-chip-bg)" }}
    >
      <Icon name={icon} size={15} />
    </button>
  )
}

/** Longer by a preset, or until a time; the item gets that much more length. */

function MoreMenu({ itemId, onSwitch, onClose }: { itemId: number; onSwitch: () => void; onClose: () => void }) {
  const navigate = useNavigate()
  const { setPop } = useShell()
  const stuck = useCommand("stuck", { label: (o) => o.result.message ?? "Noted" })
  const breaks = useBreaks()
  const options = [
    { icon: "swap", label: "Switch", desc: "Do something else now", run: onSwitch },
    { icon: "warning-circle", label: "Stuck", desc: "Note it, and see what else fits", run: () => (stuck({ id: itemId }), onSwitch()) },
    { icon: "hand-palm", label: "Shove", desc: "Take time back", run: () => (onClose(), setPop("shove")) },
    { icon: "gauge", label: "Pace", desc: "Push harder or ease off", run: () => (onClose(), setPop("pace")) },
    { icon: "arrow-square-out", label: "Open", desc: "Details, sessions and why", run: () => (onClose(), navigate(`/todo?item=${itemId}`)) },
    ...(breaks.nap ? [{ icon: "bed", label: "Nap", desc: "Pause and nap; work waits", run: () => (onClose(), breaks.nap?.()) }] : []),
    ...(breaks.snack ? [{ icon: "cookie", label: "Snack", desc: "Eat something; work waits", run: () => (onClose(), breaks.snack?.()) }] : []),
  ]
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0,1fr))", gap: 4, padding: "10px 12px 6px", boxShadow: "inset 0 -1px 0 color-mix(in srgb, var(--color-text) 7%, transparent)" }}>
      {options.map((o) => (
        <button key={o.label} className="fr-plain" onClick={o.run} style={{ display: "grid", gridTemplateColumns: "18px minmax(0,1fr)", gap: "2px 10px", alignItems: "center", padding: "8px 10px", borderRadius: "var(--radius-md)" }}>
          <Icon name={o.icon} size={16} style={{ color: "var(--color-neutral-300)" }} />
          <span>{o.label}</span>
          <span />
          <span style={{ fontSize: 11, color: "var(--color-neutral-500)" }}>{o.desc}</span>
        </button>
      ))}
    </div>
  )
}

/** Other things to do now, safe for every deadline, best first; starting one moves the timer, not the plan. */
function Swaps({ options, onClose }: { options: Fit[]; onClose: () => void }) {
  const start = useCommand("start", { label: (o) => o.result.message ?? "Switched" })
  return (
    <div style={{ display: "flex", gap: 6, alignItems: "center", padding: "0 14px 12px 18px", flexWrap: "wrap" }}>
      <span style={{ fontSize: 12, color: "var(--color-neutral-400)", marginRight: 4 }}>
        {options.length ? "Instead, with nothing going late:" : "Nothing else fits right now without something going late."}
      </span>
      {options.slice(0, 3).map((s) => (
        <button
          key={s.item_id}
          className="fr-plain fr-hover-accent"
          onClick={() => (start({ id: s.item_id }), onClose())}
          style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 10px", borderRadius: "var(--radius-md)", background: "color-mix(in srgb, var(--color-text) 6%, transparent)" }}
        >
          {s.title}
          <span className="tnum" style={{ color: "var(--color-neutral-500)" }}>
            {dur(s.minutes)}
          </span>
        </button>
      ))}
    </div>
  )
}
