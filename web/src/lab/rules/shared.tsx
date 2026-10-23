// What every rules-lab page shares: the preview (a warm solve that saves nothing), the comparison against a fresh
// solve under your current rules, a small week to draw plans in, and the one Apply button that does save.

import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { type ReactNode, useEffect, useState } from "react"
import { Link, useSearchParams } from "react-router"
import type { Schemas } from "@/api/client"
import { Icon, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useCalendar, useHorizon, useSettings, useStatus } from "@/hooks/queries"
import { clock, weekday, when } from "@/lib/format"
import { type Axis, dayRange, fromMin, hourMarks, layout, toMin } from "@/lib/time"
import { useShell } from "@/shell/ShellContext"
import { applyChanges, diffPlans, lateTotal, type Move, type PlanMap, planMap, type RuleSpec, shapeChanges, shapeOf } from "./model"

// The preview_weights input, with rules typed as the lab builds them.
export type PreviewBody = Omit<Schemas["PreviewWeightsInput"], "rules"> & { rules?: RuleSpec[] }
export type Changes = Schemas["ChangeOut"]

async function preview(body: PreviewBody): Promise<Changes> {
  const response = await fetch("/api/q/preview_weights", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })
  const out = await response.json()
  if (!response.ok) throw new Error(out.message ?? `${response.status} ${response.statusText}`)
  return out
}

/** A preview of `body`, asked again once it stops changing; null asks nothing. Each is a solve (about 1–5 s). */
export function usePreview(asked: PreviewBody | null, settleMs = 400) {
  const steady = useSteady()
  const body = asked && !steady ? { ...asked, off: [...(asked.off ?? []), STEADY] } : asked
  const wanted = JSON.stringify(body)
  const key = useSettled(wanted, settleMs) // a string, so a new object with the same content doesn't restart the wait
  const planId = useHorizon().data?.plan_id // a new plan makes every old preview stale
  const q = useQuery({
    queryKey: ["lab-preview", planId, key],
    queryFn: () => preview(JSON.parse(key) as PreviewBody),
    enabled: key !== "null" && planId !== undefined,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    retry: false,
  })
  return { changes: q.data, error: q.error, busy: q.isFetching || wanted !== key }
}

// Keeping the plan steady (a wellbeing rule) outranks every preference, so on a light week it holds blocks where they
// are and most rule changes show nothing until new work arrives. Previews switch it off unless you ask for it.
const STEADY = "minimize_changes"
const useSteady = () => useSearchParams()[0].get("steady") === "1"

function useSettled(value: string, ms: number): string {
  const [settled, setSettled] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), ms)
    return () => clearTimeout(timer)
  }, [value, ms])
  return settled
}

/** Your rules as settings hold them, with every field the engine reads. */
export function useRuleSpecs(): RuleSpec[] | undefined {
  return useSettings().data?.rules as RuleSpec[] | undefined
}

export const useOwnedByFile = () => (useStatus().data?.config_keys ?? []).includes("rules")

/**
 * The saved plan, and the plan a fresh solve under your current rules makes. Previews are compared with the
 * fresh one: a warm solve can land a little differently from the saved plan even with nothing changed.
 */
export function useBaseline() {
  const horizon = useHorizon().data
  const fresh = usePreview({}, 0).changes
  const saved = horizon ? planMap(horizon.blocks) : undefined
  return { saved, fixed: horizon?.fixed ?? [], fresh, baseline: saved && fresh ? applyChanges(saved, fresh) : undefined }
}

export interface Comparison {
  plan: PlanMap
  moves: Move[]
  lines: string[]
  lateDelta: number
}

export function compare(saved: PlanMap, fresh: Changes, baseline: PlanMap, changes: Changes): Comparison {
  const plan = applyChanges(saved, changes)
  const lateDelta = lateTotal(changes.late_hours) - lateTotal(fresh.late_hours)
  return { plan, moves: diffPlans(baseline, plan), lines: shapeChanges(shapeOf(baseline), shapeOf(plan)), lateDelta }
}

export function LabHead({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="fr-page-head">
      <Link to="/lab/rules" className="fr-link" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
        <Icon name="flask" size={16} />
        Rules lab
      </Link>
      <Icon name="caret-right" size={12} style={{ color: "var(--color-neutral-600)" }} />
      <span className="fr-h fr-title">{title}</span>
      <div style={{ flex: 1 }} />
      {children ?? <span className="fr-kicker">Prototype · nothing is saved unless a button says so</span>}
      <SteadySwitch />
    </div>
  )
}

function SteadySwitch() {
  const [params, setParams] = useSearchParams()
  const steady = params.get("steady") === "1"
  return (
    <span style={{ display: "inline-flex", gap: 8, alignItems: "center", fontSize: 12, color: "var(--color-neutral-400)" }} title="On: previews keep the plan steady, as a real replan would. Off: they plan from scratch, so you see what each rule itself does.">
      <Switch on={steady} onToggle={() => setParams(steady ? {} : { steady: "1" })} label="Keep the plan steady in previews" />
      Keep plan steady
    </span>
  )
}

export function Page({ title, idea, children, wide }: { title: string; idea: ReactNode; children: ReactNode; wide?: boolean }) {
  return (
    <>
      <LabHead title={title} />
      <div className="fr-panel" style={{ overflowY: "auto" }}>
        <div style={{ maxWidth: wide ? 1400 : 1000, padding: "24px 40px 140px", display: "flex", flexDirection: "column", gap: 24 }}>
          <span style={{ color: "var(--color-neutral-400)", textWrap: "pretty", maxWidth: 760 }}>{idea}</span>
          {children}
        </div>
      </div>
    </>
  )
}

/** What a preview changes against a fresh solve: the plan's shape in words, lateness, and each moved item. */
export function Outcome({ comparison, busy, error, limit = 8 }: { comparison?: Comparison; busy: boolean; error?: Error | null; limit?: number }) {
  const { today } = useShell()
  if (error) return <span style={{ color: "var(--fr-due)" }}>{error.message}</span>
  if (!comparison) return <span className="fr-kicker">{busy ? "Planning the week with this change…" : ""}</span>
  const { moves, lines, lateDelta } = comparison
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, opacity: busy ? 0.55 : 1, transition: "opacity .2s" }}>
      <span style={{ fontWeight: 500 }}>
        {moves.length ? `${moves.length} ${moves.length === 1 ? "thing moves" : "things move"}` : "Nothing moves"}
        {lateDelta > 0.05 ? ` · ${lateDelta.toFixed(1)} h more late work` : lateDelta < -0.05 ? ` · ${(-lateDelta).toFixed(1)} h less late work` : ""}
        {busy && <span className="fr-kicker"> · updating…</span>}
      </span>
      {lines.length > 0 && (
        <ul style={{ margin: 0, paddingLeft: 18, color: "var(--color-neutral-300)" }}>
          {lines.map((l) => (
            <li key={l}>{l[0].toUpperCase() + l.slice(1)}</li>
          ))}
        </ul>
      )}
      {moves.slice(0, limit).map((m) => (
        <div key={m.itemId} style={{ display: "flex", justifyContent: "space-between", gap: 12, fontSize: 12 }}>
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{m.title}</span>
          <span className="tnum" style={{ color: "var(--color-neutral-500)", whiteSpace: "nowrap" }}>
            {m.before[0] ? when(m.before[0][0], today) : "not planned"} → {m.after[0] ? when(m.after[0][0], today) : "off the plan"}
          </span>
        </div>
      ))}
      {moves.length > limit && <span className="fr-kicker">and {moves.length - limit} more</span>}
    </div>
  )
}

export function ApplyRules({ rules, current, label }: { rules: RuleSpec[]; current: RuleSpec[]; label?: string }) {
  const save = useCommand("settings_set", { label: () => "Rules saved; Friday is replanning" })
  const owned = useOwnedByFile()
  const same = JSON.stringify(rules) === JSON.stringify(current)
  if (owned) return <span className="fr-kicker">Your rules are set in friday.toml, so this can only preview.</span>
  return (
    <button className="btn btn-primary" disabled={same} onClick={() => save({ key: "rules", value: rules })} title="Runs settings_set with the whole rules list; undoable">
      {label ?? "Apply: save these rules (settings_set)"}
    </button>
  )
}

const PX = 0.42 // per minute in the lab's small week

interface WeekProps {
  plan: PlanMap
  compareTo?: PlanMap // moved items are lit, and where they were is drawn dashed
  fixed?: Schemas["ItemOut"][]
  days?: number
  pickedItem?: number | null
  onPickBlock?: (itemId: number, start: string) => void
  onPickTime?: (local: string) => void
}

/** A compact week: fixed items faint, planned work solid, moved work lit. */
export function MiniWeek({ plan, compareTo, fixed = [], days = 7, pickedItem, onPickBlock, onPickTime }: WeekProps) {
  const { today } = useShell()
  const calendar = useCalendar(today, days).data
  const axis: Axis = calendar ? { startMin: calendar.axis_start_min, endMin: calendar.axis_end_min } : { startMin: 7 * 60, endMin: 26 * 60 }
  const dates = dayRange(today, days)
  const moved = new Set(compareTo ? diffPlans(compareTo, plan).map((m) => m.itemId) : [])
  const blocks = [...plan].flatMap(([itemId, e]) => e.spans.map(([start, end]) => ({ itemId, title: e.title, start, end })))
  const ghosts = compareTo ? [...compareTo].filter(([id]) => moved.has(id)).flatMap(([itemId, e]) => e.spans.map(([start, end]) => ({ itemId, title: e.title, start, end }))) : []
  const timed = fixed.filter((f): f is Schemas["ItemOut"] & { start: string; end: string } => !!f.start && !!f.end && !f.start.endsWith("T00:00"))
  const height = (axis.endMin - axis.startMin) * PX
  const cols = `40px repeat(${days}, minmax(0,1fr))`
  return (
    <div className="fr-well" style={{ padding: "8px 8px 12px", overflow: "hidden" }}>
      <div style={{ display: "grid", gridTemplateColumns: cols, gap: 2, marginBottom: 6 }}>
        <span />
        {dates.map((d) => (
          <span key={d} className="fr-kicker" style={{ textAlign: "center", color: d === today ? "var(--color-accent-300)" : undefined }}>
            {weekday(d)} {Number(d.slice(8))}
          </span>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: cols, gap: 2 }}>
        <div style={{ position: "relative", height }}>
          {hourMarks(axis)
            .filter((_, i) => i % 3 === 0)
            .map((m) => (
              <span key={m.top} className="tnum" style={{ position: "absolute", right: 4, top: m.top * PX - 6, fontSize: 10, color: "var(--color-neutral-600)" }}>
                {m.label}
              </span>
            ))}
        </div>
        {dates.map((date) => (
          <div
            key={date}
            style={{ position: "relative", height, borderRadius: 4, background: "color-mix(in srgb, var(--color-text) 3%, transparent)", cursor: onPickTime ? "crosshair" : undefined }}
            onClick={(e) => {
              if (!onPickTime) return
              const y = e.clientY - e.currentTarget.getBoundingClientRect().top
              const minute = Math.round((y / PX + axis.startMin) / 15) * 15
              onPickTime(fromMin(toMin(date) + minute))
            }}
          >
            {layout(timed, date, axis).map((p) => (
              <Bar key={`f${p.item.id}${p.item.start}`} p={p} title={`${p.item.title} ${clock(p.item.start)}–${clock(p.item.end)}`} tone="fixed" />
            ))}
            {layout(ghosts, date, axis).map((p) => (
              <Bar key={`g${p.item.itemId}${p.item.start}`} p={p} title={`${p.item.title} was here`} tone="ghost" />
            ))}
            {layout(blocks, date, axis).map((p) => (
              <Bar
                key={`b${p.item.itemId}${p.item.start}`}
                p={p}
                title={`${p.item.title} ${clock(p.item.start)}–${clock(p.item.end)}`}
                tone={pickedItem === p.item.itemId ? "picked" : moved.has(p.item.itemId) ? "moved" : "block"}
                onClick={onPickBlock ? () => onPickBlock(p.item.itemId, p.item.start) : undefined}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

const TONES = {
  fixed: { background: "color-mix(in srgb, var(--color-text) 9%, transparent)", color: "var(--color-neutral-500)" },
  block: { background: "color-mix(in srgb, var(--color-accent) 30%, transparent)", color: "var(--color-text)" },
  moved: { background: "var(--fr-warn)", color: "#1a1a1a" },
  picked: { background: "var(--color-accent)", color: "white" },
  ghost: { background: "transparent", color: "var(--color-neutral-500)", outline: "1px dashed var(--fr-warn)" },
}

function Bar({ p, title, tone, onClick }: { p: { top: number; height: number; column: number; columns: number }; title: string; tone: keyof typeof TONES; onClick?: () => void }) {
  const width = 100 / p.columns
  return (
    <div
      title={title}
      onClick={
        onClick &&
        ((e) => {
          e.stopPropagation()
          onClick()
        })
      }
      style={{
        position: "absolute",
        top: p.top * PX,
        height: Math.max(p.height * PX - 1, 4),
        left: `calc(${p.column * width}% + 1px)`,
        width: `calc(${width}% - 2px)`,
        borderRadius: 3,
        fontSize: 9,
        lineHeight: "11px",
        padding: "1px 3px",
        overflow: "hidden",
        cursor: onClick ? "pointer" : undefined,
        ...TONES[tone],
      }}
    >
      {p.height >= 40 && title.split(" ").slice(0, 4).join(" ")}
    </div>
  )
}
