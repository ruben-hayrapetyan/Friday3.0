// The Now dock (v22): what you're doing right now. Timing something: the seconds ticking, how long the plan gives
// it and what's next, with Done, Pause, Switch and more. In a planned block: Start and Done (no More time). In a
// class:
// the class. Free: how long, what's next, and the best things to start, one tap each. The timer is an overlay on
// the plan, never a change to it (DESIGN §8), so Start and Pause move nothing on the calendar. With sleep tracking on
// (Settings → Schedule), a slim row on top offers the tap that fits the hour: I'm up, Ready to work, Done with work
// (with Going to bed beside it, for a night you go straight to bed), then Going to bed; with
// meal tracking on, another offers Eating now around a mealtime (or Skip), and Done eating while you eat. Napping, a
// row says since when, with I'm up; More and free time offer a nap and a snack (`breaks.ts`). Timing more than one
// thing at once (2 Nov: "working on two things at once even if friday didn't originally plan to"), a slim row for
// each of the others, ticking, with Done and Stop; "Do something else" offers starting one alongside.
//
// Minimal (Settings → Appearance) is the one-line pill its card draws (15 Nov: it was the full bar, narrower): a dot,
// what's on or what's free, and its main round actions. A tap opens the full bar, every row above; it folds back on
// a tap of the title or once what's on changes (an action taken). A sleep or meal tap waiting, or a second timer, is a
// small mark on the pill.

import { type KeyboardEvent, useEffect, useState } from "react"
import { useNavigate } from "react-router"
import type { Block, Schemas } from "@/api/client"
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
import { useBreakDay } from "@/breaks/BreakDay"
import { BREAK_ICON, things } from "@/breaks/words"
import { useShell } from "@/shell/ShellContext"
import { useBreaks } from "./breaks"
import { mealLabel } from "@/body/mealNames"
import { covered, DOCK_VAR } from "./dockRoom"
import { type Running, runningNow } from "./running"

type Menu = "time" | "more" | "swap" | null
type Fit = { item_id: number; title: string; minutes: number }

/** Whether the bar's main row shows: on a break day there are no planned times (breaks/), so only what you're timing
 * or an event you're in has one; the break's own row says the rest. */
export function nowRow({ onBreak, timing, inEvent }: { onBreak: boolean; timing: boolean; inEvent: boolean }): boolean {
  return !onBreak || timing || inEvent
}

export function Dock() {
  const box = useDockCover()
  const now = useNow().data
  const status = useStatus().data
  const timer = status?.timer ?? null
  const alongside = status?.alongside ?? []
  const today = fromMin(useClock()).slice(0, 10)
  const { look, color } = useLook()
  const [menu, setMenu] = useState<Menu>(null)
  const toggle = (m: Exclude<Menu, null>) => setMenu(menu === m ? null : m)
  const { today: planningDay } = useShell()
  const onBreak = !!useBreakDay(planningDay).data?.vacation
  const sleep = useSleep().data
  const meals = useMeals().data
  const [opened, setOpened] = useState(false)
  // What the bar shows: when it changes (Start, Done, Pause, a tap on the sleep or meal row, the next block), an
  // opened Minimal bar folds back to its pill.
  const shows = [now?.current?.key, now?.current_source, timer?.item_id, alongside.length, sleep?.next, !!sleep?.napping, meals?.next, !!meals?.eating].join("|")
  useEffect(() => (setOpened(false), setMenu(null)), [shows])
  if (!now) return null
  const cur = now.current
  const next = now.next ? `${now.next.title} ${when(now.next.start, today)}` : "nothing else today"
  const minimal = look.dockStyle === "Minimal"
  const pill = minimal && !opened
  const fold = minimal ? () => (setOpened(false), setMenu(null)) : undefined
  const timing = !!cur && !!timer && timer.item_id === cur.item_id
  const work = !!cur && !cur.fixed
  const room = "100% - var(--fr-side) - var(--fr-drawer) - 12px" // beside the sidebar and any drawer (Shell's variables)
  // a tap waiting on the sleep or meal row, or another timer: a mark on the pill, so the pill is never all there is
  // Two or more going at once (timers, a meal): side by side on the pill, which widens for them (21 Nov)
  const running = runningNow(status, meals)
  const several = running.length > 1
  const waiting = [
    ...(sleep?.on && sleep.napping ? ["bed"] : sleep?.on && sleep.next ? [TAPS[sleep.next].icon] : []),
    ...(meals?.on && (meals.eating || meals.next) && !(several && meals.eating) ? [MEAL_ICON[meals.eating?.kind ?? meals.next ?? "snack"] ?? "fork-knife"] : []),
  ]
  return (
    <div
      ref={box}
      className="fr-float"
      data-tour="now"
      data-pill={pill ? "" : undefined}
      style={{
        position: "absolute",
        left: `calc(var(--fr-side) + (${room}) / 2)`,
        bottom: 18,
        transform: "translateX(-50%)",
        width: `min(${pill ? (several ? 640 : 440) : 780}px, calc(${room} - 16px))`,
        zIndex: 8,
        borderRadius: pill ? 999 : "var(--radius-lg)",
        overflow: "hidden",
      }}
    >
      {pill ? (
        <Pill now={now} cur={cur} timing={timing} elapsed={timer?.elapsed_s ?? 0} dot={cur ? color(cur.area, cur.preset) : "var(--color-neutral-500)"} today={today} marks={waiting} alongside={alongside.length} running={several ? running : null} onOpen={() => setOpened(true)} />
      ) : (
        <>
          {work && menu === "more" && <MoreMenu itemId={cur.item_id} onSwitch={() => setMenu("swap")} onClose={() => setMenu(null)} />}
          <BreakTap />
          <SleepTap />
          <MealTap />
          {alongside.map((t) => (
            <Alongside key={t.item_id} timer={t} />
          ))}
          {!nowRow({ onBreak, timing: !!timer, inEvent: !!cur?.fixed }) ? null : cur && timing && timer ? (
            <Timing cur={cur} elapsed={timer.elapsed_s ?? 0} started={timer.started ?? null} next={next} thenSame={!!now.then_same} dot={color(cur.area, cur.preset)} menu={menu} onMenu={toggle} onFold={fold} />
          ) : cur?.fixed ? (
            <InEvent cur={cur} next={next} dot={color(cur.area, cur.preset)} onFold={fold} />
          ) : cur ? (
            <On cur={cur} next={next} dot={color(cur.area, cur.preset)} menu={menu} onMenu={toggle} onFold={fold} />
          ) : (
            <Free {...freeLine(now)} gap={now.gap_minutes} fits={now.fits} today={today} onFold={fold} />
          )}
          {work && menu === "swap" && <Swaps options={now.swaps} timing={!!timer} onClose={() => setMenu(null)} />}
        </>
      )}
    </div>
  )
}

/** Minimal's pill: the dot, what's on (or free), and its main round actions; the rest is a tap away. */
function Pill({ now, cur, timing, elapsed, dot, today, marks, alongside, running, onOpen }: { now: Schemas["NowOut"]; cur: Block | null | undefined; timing: boolean; elapsed: number; dot: string; today: string; marks: string[]; alongside: number; running: Running[] | null; onOpen: () => void }) {
  const seconds = useElapsed(elapsed)
  const nowMin = useClock()
  const pause = useCommand("stop", { label: (o) => o.result.message ?? "Paused" })
  const finish = useCommand("stop", { label: (o) => o.result.message ?? "Done" })
  const start = useCommand("start", { label: (o) => o.result.message ?? "Timing" })
  const done = useCommand("done", { label: () => `${cur?.title}: done` })
  const worked = useItem(cur && !cur.fixed && !timing ? cur.item_id : null).data?.item.done_min ?? 0
  const fit = now.fits[0]
  const title = cur ? cur.title : now.next?.start ? `Free until ${when(now.next.start, today)}` : "Free for the rest of today"
  const aside = timing ? hms(seconds) : cur?.fixed ? `until ${clock(cur.end)}` : cur ? `${span(toMin(cur.end) - nowMin)} left` : ""
  const round = { width: 32, height: 32, borderRadius: "50%", boxShadow: "none", flex: "none" } as const
  if (running) return <PillOfSeveral running={running} dot={dot} marks={marks} round={round} onOpen={onOpen} />
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 6px 5px 6px" }}>
      <button className="fr-plain" onClick={onOpen} aria-expanded={false} aria-label={`Open the Now bar: ${title}`} title="Open the Now bar" style={{ flex: 1, minWidth: 0, display: "flex", alignItems: "center", gap: 8, padding: "4px 8px 4px 10px", textAlign: "left", borderRadius: 999 }}>
        {timing ? <Pulse color={dot} /> : <span style={{ flex: "none", width: 7, height: 7, borderRadius: "50%", background: dot }} />}
        <span className="fr-h" style={{ fontSize: 15, lineHeight: 1.1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", minWidth: 0 }}>
          {title}
        </span>
        {aside && (
          <span className="tnum" style={{ flex: "none", fontSize: 12, whiteSpace: "nowrap", color: timing ? "var(--color-accent-200)" : "var(--color-neutral-400)" }}>
            {aside}
          </span>
        )}
        <span style={{ flex: 1 }} />
        {marks.map((icon) => (
          <Icon key={icon} name={icon} size={13} style={{ flex: "none", color: "var(--color-accent-300)" }} />
        ))}
        {alongside > 0 && (
          <span className="tnum" style={{ flex: "none", fontSize: 11, color: "var(--color-neutral-400)" }}>
            +{alongside}
          </span>
        )}
      </button>
      {timing && cur ? (
        <>
          <button className="btn btn-icon btn-primary" onClick={() => finish({ done: true })} aria-label="Stop the timer and mark it done" title="Stop the timer and mark it done" style={round}>
            <Icon name="check" size={15} />
          </button>
          <button className="btn btn-icon btn-secondary" onClick={() => pause({})} aria-label="Pause the timer (Space)" title="Pause the timer (Space)" style={{ ...round, background: "var(--fr-chip-bg)" }}>
            <Icon name="pause" size={15} />
          </button>
        </>
      ) : cur && !cur.fixed ? (
        <>
          <button className="btn btn-icon btn-primary" onClick={() => start({ id: cur.item_id })} aria-label={worked ? `Resume the timer: ${dur(worked)} done so far (Space)` : "Start the timer (Space)"} title={worked ? `Resume the timer: ${dur(worked)} done so far (Space)` : "Start the timer (Space)"} style={round}>
            <Icon name="play" size={14} fill />
          </button>
          <button className="btn btn-icon btn-secondary" onClick={() => done({ id: cur.item_id })} aria-label="Mark it done" title="Mark it done" style={{ ...round, background: "var(--fr-chip-bg)" }}>
            <Icon name="check" size={15} />
          </button>
        </>
      ) : !cur && fit ? (
        <button className="btn btn-icon btn-primary" onClick={() => start({ id: fit.item_id })} aria-label={`Start ${fit.title}`} title={`Start ${fit.title}, ${dur(fit.minutes)}: the plan stays as it is`} style={round}>
          <Icon name="play" size={14} fill />
        </button>
      ) : null}
    </div>
  )
}

/** In an opened Minimal bar, the title folds it back to the pill. */
function foldable(onFold?: () => void) {
  if (!onFold) return {}
  return {
    role: "button",
    tabIndex: 0,
    "aria-expanded": true,
    "aria-label": "Fold the Now bar",
    title: "Fold the Now bar",
    onClick: onFold,
    onKeyDown: (e: KeyboardEvent) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onFold()),
    style: { cursor: "pointer" },
  } as const
}

/** Says in --fr-dock how much of the window's foot the dock covers, whenever its rows come and go or the window
 * resizes, so the page's columns leave that much room (dockRoom); 0 once it's gone. */
function useDockCover() {
  const [box, setBox] = useState<HTMLDivElement | null>(null)
  useEffect(() => {
    const root = document.documentElement
    const say = () => root.style.setProperty(DOCK_VAR, `${covered(box ? box.getBoundingClientRect().top : null, window.innerHeight)}px`)
    say()
    const watch = box && typeof ResizeObserver !== "undefined" ? new ResizeObserver(say) : null
    if (box) watch?.observe(box)
    window.addEventListener("resize", say)
    return () => (watch?.disconnect(), window.removeEventListener("resize", say), root.style.setProperty(DOCK_VAR, "0px"))
  }, [box])
  return setBox
}

const TAPS = {
  up: { icon: "sun-horizon", ask: "Just up?", button: "I'm up" },
  ready: { icon: "coffee", ask: "Morning routine done?", button: "Ready to work" },
  done: { icon: "laptop", ask: "Done with work for the night?", button: "Done with work" },
  bed: { icon: "moon", ask: "Heading to sleep?", button: "Going to bed" },
} as const

/** Tracked sleep's one tap, when there's one to make; Friday learns your nights, mornings and evenings from them.
 * Napping, the nap and I'm up instead. */
/** On a break (breaks/): today's list in a line, opening it beside the calendar. */
function BreakTap() {
  const { today, setBreakDay, breakDay } = useShell()
  const navigate = useNavigate()
  const day = useBreakDay(today).data
  const v = day?.vacation
  if (!day || !v) return null
  const left = day.items.filter((t) => !t.ticked).length
  const said = v.mode === "off" || !day.items.length ? "nothing to do today" : left ? `${things(left)} to do today` : "today's list is done"
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 14px 6px 18px", boxShadow: "inset 0 -1px 0 var(--fr-hairline)", fontSize: 12, color: "var(--color-neutral-400)" }}>
      <Icon name={BREAK_ICON} size={14} style={{ color: "var(--fr-break)" }} />
      <span style={{ flex: 1, minWidth: 0 }}>
        <span style={{ color: "var(--color-text)" }}>{v.name}</span> · {said}
      </span>
      {day.items.length > 0 && (
        <button className="btn btn-secondary fr-press" onClick={() => (navigate("/"), setBreakDay(breakDay === today ? null : today))} style={{ fontSize: 12, padding: "2px 10px" }}>
          Today's list
        </button>
      )}
    </div>
  )
}

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
            Eating {mealLabel(kind, meals.eating?.nth ?? 1).toLowerCase()} since {clock(since)} · {dur(Math.max(1, nowMin - toMin(since)))}
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
  menu: Menu
  onMenu: (m: Exclude<Menu, null>) => void
  onFold?: () => void // an opened Minimal bar: the title folds it back to the pill
}

const row = { display: "flex", alignItems: "center", gap: 14, padding: "10px 14px 12px 18px" } as const
const column = { display: "flex", flexDirection: "column", minWidth: 0, flex: 1 } as const
const kicker = { display: "flex", gap: 6, alignItems: "center", fontSize: 12, color: "var(--color-neutral-400)", whiteSpace: "nowrap", overflow: "hidden" } as const
const dim = { overflow: "hidden", textOverflow: "ellipsis", color: "var(--color-neutral-500)", flexShrink: 1000 } as const
// the kicker's time: "· then …" gives way first; in a phone's width the time itself ends in … rather than being cut
// part way (15 Nov: "Now 12:30pm–1pm" lost its last 6px at 390px)
const kickerTime = { minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" } as const
const buttons = { display: "flex", gap: 6, flex: "none" } as const
const titleStyle = { fontSize: 22, lineHeight: 1.05, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" } as const
const clamp = (x: number) => Math.max(0, Math.min(100, x))
const share = (cur: Block, nowMin: number) => clamp(((nowMin - toMin(cur.start)) / Math.max(1, toMin(cur.end) - toMin(cur.start))) * 100)

/** The timer running on what you're doing: the seconds, the plan's room for it, then what's next. */
function Timing({ cur, elapsed, started, next, thenSame, dot, menu, onMenu, onFold }: State & { elapsed: number; started: string | null; thenSame: boolean }) {
  const seconds = useElapsed(elapsed)
  const nowMin = useClock()
  const pause = useCommand("stop", { label: (o) => o.result.message ?? "Paused" })
  const finish = useCommand("stop", { label: (o) => o.result.message ?? "Done" })
  // What's also planned next is this work (21 Nov, a user's notes: "0:09 left · then Preliminary Thesis 20:00" over
  // "48m left"): how long it has left in all, as the estimate below says, not this block; "then" is the next other.
  const item = useItem(thenSame ? cur.item_id : null).data?.item
  const all = item && item.amount === "fixed" && item.duration_min != null ? item.duration_min - item.done_min - Math.floor(seconds / 60) : null
  const left = all ?? toMin(cur.end) - nowMin
  const [forgot, setForgot] = useState(false)
  return (
    <>
      <Bar pct={share(cur, nowMin)} live />
      <div style={row}>
        <div {...foldable(onFold)} style={{ ...column, ...foldable(onFold).style }}>
          <div style={kicker}>
            <Pulse color={dot} />
            <span className="tnum" style={kickerTime}>Timing since {clock(cur.start)}</span>
            <span style={dim}>
              · {left > 0 ? `${span(left)} left` : "past its time"} · then {next}
            </span>
          </div>
          <div className="fr-h" title={cur.title} style={titleStyle}>
            {cur.title}
          </div>
        </div>
        <span className="tnum" style={{ flex: "none", fontSize: 26, fontWeight: 500, letterSpacing: "-0.02em", color: "var(--color-accent-200)", minWidth: 84, textAlign: "right" }}>
          {hms(seconds)}
        </span>
        <div style={buttons}>
          <button className="btn btn-primary" onClick={() => finish({ done: true })} title="Stop the timer and mark it done" style={{ whiteSpace: "nowrap" }}>
            <Icon name="check" size={15} />
            Done
          </button>
          <IconButton icon="pause" label="Pause the timer (Space)" onClick={() => pause({})} />
          <IconButton icon="swap" label="Do something else" on={menu === "swap"} onClick={() => onMenu("swap")} />
          <IconButton icon="dots-three" label="More" on={menu === "more"} onClick={() => onMenu("more")} />
        </div>
      </div>
      {/* Started and finding it's longer (or shorter) than you thought: the estimate, a tap from here. */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 14px 10px 18px", fontSize: 12, color: "var(--color-neutral-400)" }}>
        <EstimateNudge itemId={cur.item_id} runningMin={seconds / 60} />
        {started && !forgot && (
          <button className="fr-link" onClick={() => setForgot(true)} style={{ marginLeft: "auto", fontSize: 12, flex: "none" }}>
            Forgot to stop?
          </button>
        )}
      </div>
      {started && forgot && <ForgotToStop started={started} now={nowMin} onClose={() => setForgot(false)} />}
    </>
  )
}

/** A timer left running (28 Oct: "what if i forgot to turn the timer off"): stop it as of when you really stopped, so
 * only that counts as done and as how long it took. Its own row under the timer, opened at the time it is now (9 Nov:
 * an empty box's arrows counted from 9am, so a timer started at 5:34pm was "stopped" at 8:50am), every control the same
 * height, the buttons before Cancel and none moving with the time typed (5 Nov). */
function ForgotToStop({ started, now, onClose }: { started: string; now: number; onClose: () => void }) {
  const [at, setAt] = useState(() => stoppedGuess(now, toMin(started)))
  const stop = useCommand("stop", { label: (o) => o.result.message ?? "Stopped" })
  const end = (done: boolean) => {
    if (!at) return
    stop({ at: spanOn(started.slice(0, 10), started.slice(11, 16), at).end, done })
    onClose()
  }
  const control = { fontSize: 12, height: 28, minHeight: 0, padding: "0 10px", flex: "none" } as const
  return (
    <div role="group" aria-label="When you stopped" onKeyDown={(e) => e.key === "Enter" && end(false)} style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 8, padding: "0 14px 12px 18px", fontSize: 12, color: "var(--color-neutral-400)" }}>
      <span style={{ flex: "none" }}>You stopped at</span>
      <TimeInput value={at} onChange={setAt} label="Stopped at" expect={{ after: started.slice(11, 16), near: stoppedGuess(now, toMin(started)) }} style={{ fontSize: 12, height: 28, minHeight: 0, padding: "0 10px", width: 92 }} />
      <button className="btn btn-primary fr-press" disabled={!at} onClick={() => end(false)} style={control}>
        Stop then
      </button>
      <button className="btn btn-secondary fr-press" disabled={!at} onClick={() => end(true)} style={control}>
        Done then
      </button>
      <button className="btn btn-ghost" onClick={onClose} style={control}>
        Cancel
      </button>
    </div>
  )
}

/** Where "you stopped at" starts: now, to the 5 minutes before (it was earlier, and the arrows step by 5), never
 * before the timer started (a stop before its start would read as the next day's). */
export function stoppedGuess(now: number, started: number): string {
  const round = Math.floor(now / 5) * 5
  return fromMin(round > started ? round : now).slice(11, 16)
}

/** In a planned block, not timing it yet. */
function On({ cur, next, dot, menu, onMenu, onFold }: State) {
  const nowMin = useClock()
  const start = useCommand("start", { label: (o) => o.result.message ?? "Timing" })
  const done = useCommand("done", { label: () => `${cur.title}: done` })
  const worked = useItem(cur.item_id).data?.item.done_min ?? 0 // some done already: Resume, not Start
  return (
    <>
      <Bar pct={share(cur, nowMin)} />
      <div style={row}>
        <div {...foldable(onFold)} style={{ ...column, ...foldable(onFold).style }}>
          <div style={kicker}>
            <span style={{ flex: "none", width: 6, height: 6, borderRadius: "50%", background: dot }} />
            <span className="tnum" style={kickerTime}>
              Now {clock(cur.start)}–{clock(cur.end)}
            </span>
            <span style={dim}>· then {next}</span>
          </div>
          <div className="fr-h" title={cur.title} style={titleStyle}>
            {cur.title}
          </div>
        </div>
        <span className="tnum" style={{ flex: "none", fontSize: 20, fontWeight: 500, letterSpacing: "-0.02em", whiteSpace: "nowrap" }}>
          {span(toMin(cur.end) - nowMin)} left
        </span>
        <div style={buttons}>
          <button className="btn btn-primary" onClick={() => start({ id: cur.item_id })} title={worked ? `Resume the timer: ${dur(worked)} done so far (Space)` : "Start the timer (Space)"} style={{ whiteSpace: "nowrap" }}>
            <Icon name="play" size={14} fill />
            {worked ? "Resume" : "Start"}
          </button>
          <IconButton icon="check" label="Mark it done" onClick={() => done({ id: cur.item_id })} />
          <IconButton icon="dots-three" label="More" on={menu === "more"} onClick={() => onMenu("more")} />
        </div>
      </div>
    </>
  )
}

/** In a class or other fixed event: where you are, until when, and what's after. */
function InEvent({ cur, next, dot, onFold }: { cur: Block; next: string; dot: string; onFold?: () => void }) {
  const nowMin = useClock()
  return (
    <>
      <Bar pct={share(cur, nowMin)} muted />
      <div style={row}>
        <div {...foldable(onFold)} style={{ ...column, ...foldable(onFold).style }}>
          <div style={kicker}>
            <span style={{ flex: "none", width: 6, height: 6, borderRadius: "50%", background: dot }} />
            <span className="tnum" style={kickerTime}>Now, until {clock(cur.end)}</span>
            <span style={dim}>· then {next}</span>
          </div>
          <div className="fr-h" title={cur.title} style={titleStyle}>
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
  onFold?: () => void
}

/** Nothing on: how long you're free, what's next, and what to start, one tap each. */
function Free({ until, gap, next, fits, today, onFold }: FreeProps) {
  const start = useCommand("start", { label: (o) => o.result.message ?? "Timing" })
  const breaks = useBreaks()
  const quiet = { fontSize: 12, display: "inline-flex", gap: 4, alignItems: "center" } as const
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "12px 14px 12px 18px" }}>
      <div {...foldable(onFold)} style={{ display: "flex", alignItems: "baseline", gap: 12, minWidth: 0, ...foldable(onFold).style }}>
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
        {breaks.again && (
          // First of the three, so Nap and Snack keep their places when it comes and goes
          <button className="fr-link" onClick={breaks.again.run} title={`Having another ${breaks.again.kind}: the plan keeps the time clear`} style={{ ...quiet, marginRight: 8 }}>
            <Icon name={MEAL_ICON[breaks.again.kind] ?? "fork-knife"} size={12} />
            Another {breaks.again.kind}
          </button>
        )}
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

// Its ring is RING px past the dot; the line it sits in hides what's outside it, so the dot keeps that much room around
// it (16 Nov, a screenshot: the ring's left side was cut off at the line's edge).
export const RING = 3

/** The pill with two or more going at once: each side by side, oldest first, its own time ticking; Done and Pause act
 * on the timer you started last, as on the one-thing pill; a tap anywhere else opens the bar with each one's row. */
function PillOfSeveral({ running, dot, marks, round, onOpen }: { running: Running[]; dot: string; marks: string[]; round: object; onOpen: () => void }) {
  const pause = useCommand("stop", { label: (o) => o.result.message ?? "Paused" })
  const finish = useCommand("stop", { label: (o) => o.result.message ?? "Done" })
  const main = running.find((r) => r.main)
  const names = running.map((r) => r.title).join(", ")
  return (
    <div className="fr-several" style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 6px" }}>
      <button className="fr-plain" onClick={onOpen} aria-expanded={false} aria-label={`Open the Now bar: ${names}`} title="Open the Now bar" style={{ flex: 1, minWidth: 0, display: "flex", alignItems: "center", gap: 6, padding: "4px 8px 4px 6px", textAlign: "left", borderRadius: 999, overflow: "hidden" }}>
        {running.map((r, i) => (
          <span key={r.key} style={{ display: "contents" }}>
            {i > 0 && <span aria-hidden style={{ flex: "none", width: 1, height: 16, margin: "0 6px", background: "color-mix(in srgb, var(--color-text) 14%, transparent)" }} />}
            <Going r={r} dot={dot} />
          </span>
        ))}
        <span style={{ flex: 1 }} />
        {marks.map((icon) => (
          <Icon key={icon} name={icon} size={13} style={{ flex: "none", color: "var(--color-accent-300)" }} />
        ))}
      </button>
      {main && (
        <>
          <button className="btn btn-icon btn-primary" onClick={() => finish({ done: true })} aria-label={`Stop the timer and mark ${main.title} done`} title={`Stop the timer and mark ${main.title} done`} style={round}>
            <Icon name="check" size={15} />
          </button>
          <button className="btn btn-icon btn-secondary" onClick={() => pause({})} aria-label={`Pause the timer on ${main.title} (Space)`} title={`Pause the timer on ${main.title} (Space)`} style={{ ...round, background: "var(--fr-chip-bg)" }}>
            <Icon name="pause" size={15} />
          </button>
        </>
      )}
    </div>
  )
}

/** One thing going on, in the pill of several: a pulse (or the meal's icon), its name, how long so far. */
function Going({ r, dot }: { r: Running; dot: string }) {
  const seconds = useElapsed(r.kind === "timer" ? r.elapsed_s : null)
  const nowMin = useClock()
  const soFar = r.kind === "timer" ? hms(seconds) : dur(Math.max(0, nowMin - (r.started ? toMin(r.started) : nowMin)))
  // Only names give way, a long one far before a short one ("Lunch" whole beside "Prep: PHYS 1112 Prel…"); the dot and
  // the time keep their room. Its parts sit in the pill's own row (display: contents), so each shrinks on its own.
  return (
    <span data-going={r.kind} style={{ display: "contents" }}>
      {r.kind === "meal" ? <Icon name={MEAL_ICON[r.meal ?? ""] ?? "fork-knife"} size={13} style={{ flex: "none", color: "var(--color-accent-300)" }} /> : <Pulse color={r.main ? dot : "var(--color-neutral-400)"} />}
      <span className={`fr-h fr-going-name${r.title.length <= 12 ? " is-short" : ""}`} style={{ ["--shrink" as string]: r.title.length ** 3, fontSize: 14, lineHeight: 1.1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", color: r.main ? "var(--color-text)" : "var(--color-neutral-300)" }}>
        {r.title}
      </span>
      <span className="tnum" style={{ flex: "none", fontSize: 12, whiteSpace: "nowrap", color: r.kind === "timer" ? "var(--color-accent-200)" : "var(--color-neutral-400)" }}>
        {soFar}
      </span>
    </span>
  )
}

function Pulse({ color }: { color: string }) {
  return <span data-pulse style={{ flex: "none", width: 8, height: 8, margin: RING, borderRadius: "50%", background: color, boxShadow: `0 0 0 ${RING}px color-mix(in srgb, ${color} 30%, transparent)` }} />
}

function IconButton({ icon, label, on, small, onClick }: { icon: string; label: string; on?: boolean; small?: boolean; onClick: () => void }) {
  return (
    <button
      className="btn btn-icon btn-secondary"
      onClick={onClick}
      aria-label={label}
      title={label}
      style={{ boxShadow: "none", background: on ? "color-mix(in srgb, var(--color-accent) 18%, transparent)" : "var(--fr-chip-bg)", ...(small ? { width: 26, height: 26 } : {}) }}
    >
      <Icon name={icon} size={small ? 13 : 15} />
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

/** Something else timed at the same time as what you're on: its own seconds, Done and Stop; the plan stays. */
function Alongside({ timer }: { timer: Schemas["TimerOut"] }) {
  const seconds = useElapsed(timer.elapsed_s ?? 0)
  const stop = useCommand("stop", { label: (o) => o.result.message ?? "Stopped" })
  const id = timer.item_id ?? undefined
  return (
    <div data-testid="alongside" style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 14px 6px 18px", fontSize: 12.5, borderBottom: "1px solid color-mix(in srgb, var(--color-text) 6%, transparent)" }}>
      <Pulse color="var(--color-neutral-400)" />
      <span style={{ color: "var(--color-neutral-400)", whiteSpace: "nowrap" }}>Also timing</span>
      <span title={timer.title ?? ""} style={{ ...dim, color: "var(--color-text)", flex: 1, minWidth: 0, whiteSpace: "nowrap" }}>
        {timer.title}
      </span>
      <span className="tnum" style={{ color: "var(--color-accent-200)" }}>
        {hms(seconds)}
      </span>
      <IconButton icon="check" label={`Done: stop it and mark ${timer.title} done`} small onClick={() => stop({ id, done: true })} />
      <IconButton icon="stop" label={`Stop timing ${timer.title}; what you're on goes on`} small onClick={() => stop({ id })} />
    </div>
  )
}

/** Other things to do now, safe for every deadline, best first; starting one moves the timer, not the plan, and
 * while you time something, + starts one alongside it instead. */
function Swaps({ options, timing, onClose }: { options: Fit[]; timing: boolean; onClose: () => void }) {
  const start = useCommand("start", { label: (o) => o.result.message ?? "Switched" })
  return (
    <div style={{ display: "flex", gap: 6, alignItems: "center", padding: "0 14px 12px 18px", flexWrap: "wrap" }}>
      <span style={{ fontSize: 12, color: "var(--color-neutral-400)", marginRight: 4 }}>
        {options.length ? "Instead, with nothing going late:" : "Nothing else fits right now without something going late."}
      </span>
      {options.slice(0, 3).map((s) => (
        // One chip, two buttons: the title switches to it, + starts it alongside what you're on (2 Nov)
        <span key={s.item_id} style={{ display: "inline-flex", borderRadius: "var(--radius-md)", background: "color-mix(in srgb, var(--color-text) 6%, transparent)", overflow: "hidden" }}>
          <button
            className="fr-plain fr-hover-accent"
            onClick={() => (start({ id: s.item_id }), onClose())}
            title={timing ? "Switch to it: what you're on stops" : undefined}
            style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 10px" }}
          >
            {s.title}
            <span className="tnum" style={{ color: "var(--color-neutral-500)" }}>
              {dur(s.minutes)}
            </span>
          </button>
          {timing && (
            <button
              className="fr-plain fr-hover-accent"
              onClick={() => (start({ id: s.item_id, alongside: true }), onClose())}
              aria-label={`Start ${s.title} alongside`}
              title="Alongside: keep timing what you're on too"
              style={{ display: "flex", alignItems: "center", padding: "5px 8px", borderLeft: "1px solid color-mix(in srgb, var(--color-text) 12%, transparent)", color: "var(--color-accent-300)" }}
            >
              <Icon name="plus" size={13} />
            </button>
          )}
        </span>
      ))}
    </div>
  )
}

/** Until when you're free and what comes then, from one fact: the free time's end, as its length counts it. Busy time
 * on a calendar you hid ends it unnamed (24 Nov, the agreement check: "Free until" the next visible thing's time, beside
 * the shorter length to the hidden meeting). */
export function freeLine(now: { free_until?: string | null; next?: { start: string; title: string } | null }): { until: string | null; next: string | null } {
  const until = now.free_until ?? now.next?.start ?? null
  const hidden = !!now.free_until && !!now.next && now.free_until < now.next.start
  return { until, next: hidden ? "busy" : (now.next?.title ?? null) }
}
