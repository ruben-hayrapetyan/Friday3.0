// One to-do's detail (v22 To-do aside): tag, kind, due, how hard the deadline is, the estimate, the sessions planned
// for it and why, and Start, Done, See on plan, Delete.

import { useCallback, useState } from "react"
import { useNavigate } from "react-router"
import type { Block } from "@/api/client"
import { Icon, Seg, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useAreas, useItem, useNow, useWhy } from "@/hooks/queries"
import { clock, dur, weekday, when } from "@/lib/format"
import { toMin } from "@/lib/time"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"
import { usePresets } from "./AddBox"
import { progress } from "./groups"
import { DuePicker, LengthPicker, LengthStepper, ListPicker } from "./Pickers"

const TRAVEL = [0, 10, 15, 30] // minutes each way

const FIRMNESS = [
  { value: "hard", label: "Hard" },
  { value: "soft", label: "Soft" },
  { value: "none", label: "None" },
]

export function TodoDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { today, select, place, setPlace } = useShell()
  const navigate = useNavigate()
  // "See on plan": the calendar shows that block's day, and the block is selected there.
  const seeOnPlan = (b: Block) => (setPlace({ view: place.view === "month" ? 1 : place.view, first: b.start.slice(0, 10) }), navigate("/"), select(b))
  const { color } = useLook()
  const detail = useItem(id).data
  const now = useNow().data
  const presets = usePresets()
  const areas = (useAreas().data ?? []).filter((a) => !a.archived).map((a) => a.name)
  const [pick, setPick] = useState<"area" | "preset" | "due" | "length" | null>(null)
  const firstKey = detail?.blocks[0]?.key ?? null
  const why = useWhy(firstKey).data
  const edit = useCommand("edit", { label: () => "Saved" })
  const saveLength = useCallback((min: number) => edit({ id, duration_min: min }), [edit, id])
  const done = useCommand("done", { label: () => "Done" })
  const reopen = useCommand("reopen", { label: () => "Open again" })
  const start = useCommand("start", { label: () => "Started" })
  // How much is done, set by hand: a click along the bar, or Start over (27 Oct: no way to reset it).
  const setProgress = useCommand("progress", { label: () => "Progress set" })
  const drop = useCommand("drop", { label: () => "Deleted" })
  const deleteSeries = useCommand("series_delete", { label: (o) => o.result.message ?? "Deleted" })
  const [asking, setAsking] = useState(false)
  if (!detail) return <aside />
  const item = detail.item
  const p = progress(item)
  const isDone = item.status === "done"
  const toggle = (k: typeof pick) => setPick(pick === k ? null : k)
  const length = item.duration_min
  // The same each way here; an item given different times before and after shows neither chip.
  const travel = (item.buffer_before_min ?? 0) === (item.buffer_after_min ?? 0) ? item.buffer_before_min ?? 0 : null
  const button = (k: typeof pick, content: React.ReactNode) => (
    <button
      onClick={() => toggle(k)}
      className="fr-plain fr-well tnum"
      style={{ justifySelf: "start", display: "inline-flex", gap: 6, alignItems: "center", padding: "4px 10px", borderRadius: "var(--radius-sm)", fontSize: 12 }}
    >
      {content}
      <Icon name="caret-down" size={10} style={{ opacity: 0.6 }} />
    </button>
  )
  const panel = (content: React.ReactNode) => (
    <div className="fr-well" style={{ gridColumn: "1 / -1", padding: 12 }}>
      {content}
    </div>
  )
  return (
    <aside style={{ overflowY: "auto", minHeight: 0, padding: "20px 22px 140px", boxShadow: "inset 1px 0 0 color-mix(in srgb, var(--color-text) 7%, transparent)", display: "flex", flexDirection: "column", gap: 18 }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 6, minWidth: 0 }}>
          <span style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, color: "var(--color-neutral-400)" }}>
            <span style={{ width: 10, height: 10, borderRadius: 3, background: color(item.area, item.preset) }} />
            {item.area ?? "No tag"}
          </span>
          <span className="fr-h" style={{ fontSize: 30, lineHeight: 1 }}>
            {item.title}
          </span>
        </div>
        <button className="btn btn-icon btn-ghost" onClick={onClose} aria-label="Close" style={{ width: 28, height: 28, color: "var(--color-neutral-400)" }}>
          <Icon name="x" />
        </button>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <div className="tnum" style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
          <span style={{ color: "var(--color-neutral-300)" }}>{p.text}</span>
          <span style={{ display: "flex", gap: 8, color: "var(--color-neutral-500)" }}>
            {item.remaining_min != null ? `${dur(item.remaining_min)} left${item.done_min ? ` · ${dur(item.done_min)} done` : ""}` : ""}
            {!!item.done_min && !isDone && (
              <button className="fr-link" onClick={() => setProgress({ id: item.id, share: 0 })} title="Count nothing as done yet: Friday plans all of it again" style={{ fontSize: 12 }}>
                Start over
              </button>
            )}
          </span>
        </div>
        <div
          role="slider"
          aria-label="How much is done"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={p.pct}
          title={isDone ? undefined : "Click to say how much is done"}
          tabIndex={isDone || item.remaining_min == null ? undefined : 0}
          // ← and → a twentieth at a time, Home and End none and all (the audit, 31 Oct: no keyboard way)
          onKeyDown={(e) => {
            if (isDone || item.remaining_min == null) return
            const now = p.pct / 100
            const share = e.key === "ArrowRight" || e.key === "ArrowUp" ? now + 0.05 : e.key === "ArrowLeft" || e.key === "ArrowDown" ? now - 0.05 : e.key === "Home" ? 0 : e.key === "End" ? 1 : null
            if (share === null) return
            e.preventDefault()
            setProgress({ id: item.id, share: Math.min(1, Math.max(0, Math.round(share * 20) / 20)) })
          }}
          onClick={(e) => {
            if (isDone || item.remaining_min == null) return
            const box = e.currentTarget.getBoundingClientRect()
            const share = Math.min(1, Math.max(0, Math.round(((e.clientX - box.left) / box.width) * 20) / 20))
            setProgress({ id: item.id, share })
          }}
          style={{ height: 10, padding: "2px 0", cursor: isDone ? undefined : "pointer" }}
        >
          <div style={{ height: 6, borderRadius: 3, background: "color-mix(in srgb, var(--color-text) 8%, transparent)", overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${p.pct}%`, background: color(item.area, item.preset) }} />
          </div>
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "96px minmax(0,1fr)", gap: "12px 14px", alignItems: "center" }}>
        <span className="fr-kicker">Tag</span>
        {button("area", (
          <>
            <span className="fr-swatch" style={{ background: color(item.area, item.preset) }} />
            {item.area ?? "No tag"}
          </>
        ))}
        {pick === "area" &&
          panel(<ListPicker options={[{ value: null as string | null, label: "No tag" }, ...areas.map((a) => ({ value: a as string | null, label: a, swatch: color(a) }))]} value={item.area} onPick={(v) => (edit({ id, area: v }), setPick(null))} />)}
        <span className="fr-kicker">Kind</span>
        {button("preset", (
          <>
            <Icon name="shapes" size={12} />
            {item.preset ?? "To-do"}
          </>
        ))}
        {pick === "preset" && panel(<ListPicker options={presets.map((p) => ({ value: p as string | null, label: p }))} value={item.preset} onPick={(v) => (edit({ id, preset: v }), setPick(null))} />)}
        <span className="fr-kicker">Due</span>
        {button("due", (
          <>
            <Icon name="flag" size={12} />
            {item.due ? when(item.due, today) : "No due date"}
          </>
        ))}
        {pick === "due" && panel(<DuePicker value={item.due} today={today} onPick={(v) => edit({ id, due: v })} stacked />)}
        <span className="fr-kicker">Deadline</span>
        <Seg options={FIRMNESS} value={item.firmness} onPick={(v) => edit({ id, firmness: v as "hard" | "soft" | "none" })} />
        <span className="fr-kicker" title="Never planned after its due: pointless once late (COMBINED.md 50)">After it's due</span>
        <span style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <Seg
            options={[
              { value: "pointless", label: "⏳ Pointless" },
              { value: "late", label: "Still worth doing" },
            ]}
            value={item.pointless_late ? "pointless" : "late"}
            onPick={(v) => edit({ id, expires: v === "pointless" })}
            size="small"
          />
          <span className="fr-kicker">
            {item.expires == null ? (item.pointless_late ? "As for all exam prep. " : "") : "Your choice for this one. "}
            {item.pointless_late ? "Never planned after it's due." : "Planned late if it can't be on time."}
          </span>
        </span>
        <span className="fr-kicker" title="Laundry, a long simulation, a download: you start it, then it runs while you do other work">
          Runs by itself
        </span>
        <span style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <Switch on={!!item.background} onToggle={() => edit({ id, background: !item.background })} label="Runs by itself" />
          <span className="fr-kicker">
            {item.background ? "Friday holds 15 minutes to start it, then plans other work on top while it runs." : "Off: you work on it the whole time."}
          </span>
        </span>
        <span className="fr-kicker">Estimate</span>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <LengthStepper key={id} value={length} onSave={saveLength} />
          {item.guess_min ? <span className="fr-kicker">{item.guess_min === length ? "Friday’s guess" : `Friday guessed ${dur(item.guess_min)}`}</span> : null}
          <button onClick={() => toggle("length")} className="btn btn-ghost" style={{ padding: "2px 8px", fontSize: 12 }}>
            Set
          </button>
        </div>
        {pick === "length" && panel(<LengthPicker value={length} onPick={(v) => v && edit({ id, duration_min: v })} />)}
        {(item.cushion ?? 1) > 1 && length && (
          <span className="fr-kicker" style={{ gridColumn: "2" }} title="Settings → Advanced → estimate.cushion turns this off">
            Friday plans {dur(Math.ceil((length * (item.cushion ?? 1)) / 15) * 15)}: you run about {(item.cushion ?? 1).toFixed(1)}× on{" "}
            {item.area ?? item.preset ?? "work like this"}.
          </span>
        )}
        <span className="fr-kicker" title="Kept clear of other work before and after it">
          Getting there
        </span>
        <span style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <Seg
            options={TRAVEL.map((m) => ({ value: m, label: m ? `${m} min` : "None" }))}
            value={travel}
            onPick={(m) => edit({ id, buffer_before_min: m || null, buffer_after_min: m || null, ...(item.series_id != null ? { from_date: today } : {}) })}
            size="small"
          />
          <span className="fr-kicker">
            {travel === null
              ? `${item.buffer_before_min ?? 0} min kept free before, ${item.buffer_after_min ?? 0} after`
              : travel
                ? `${travel} min kept free before and after, to get there and back`
                : "Work can sit right up against it"}
            {item.series_id != null && travel !== null ? `, every ${item.title} from today.` : "."}
          </span>
        </span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <span className="fr-h" style={{ fontSize: 16 }}>
            Planned sessions
          </span>
          <span className="fr-kicker">{detail.blocks.length || ""}</span>
        </div>
        {detail.blocks.map((b) => (
          <button
            key={b.key}
            onClick={() => seeOnPlan(b)}
            className="fr-plain"
            style={{
              display: "grid",
              gridTemplateColumns: "72px minmax(0,1fr) auto",
              gap: 10,
              alignItems: "center",
              padding: "8px 10px",
              borderRadius: "var(--radius-md)",
              background: "var(--color-bg)",
              boxShadow: now?.current?.key === b.key ? "inset 0 0 0 1px var(--color-accent)" : undefined,
            }}
          >
            <span className="tnum">
              {weekday(b.start.slice(0, 10))} {Number(b.start.slice(8, 10))}
            </span>
            <span style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
              <span className="tnum">
                {clock(b.start)}–{clock(b.end)}
              </span>
              <span style={{ fontSize: 11, color: "var(--color-neutral-500)" }}>{b.pinned === "locked" ? "Locked · won’t move" : b.pinned ? "Pinned here · resists moving" : b.tentative ? "Tentative · could fit here" : "Planned · Friday decides"}</span>
            </span>
            <span className="tnum" style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>
              {dur(toMin(b.end) - toMin(b.start))}
            </span>
          </button>
        ))}
        {!detail.blocks.length && <span className="fr-kicker">Nothing planned. Friday will find time once it has a due date or an estimate.</span>}
      </div>
      {why && (
        <div style={{ padding: 12, borderRadius: "var(--radius-md)", background: "color-mix(in srgb, var(--color-accent) 8%, var(--color-bg))", display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 12, color: "var(--color-accent-300)" }}>Why these times</span>
          <span style={{ textWrap: "pretty" }}>{why.sentence}</span>
        </div>
      )}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {!isDone && item.when !== "fixed" && now?.current?.item_id !== id && (
          <button className="btn btn-primary" onClick={() => start({ id })}>
            <Icon name="play" />
            {item.done_min ? "Resume" : "Start now"}
          </button>
        )}
        <button className="btn btn-secondary" onClick={() => (isDone ? reopen({ id }) : done({ id }))}>
          <Icon name="check" />
          {isDone ? "Open again" : "Mark done"}
        </button>
        {detail.blocks[0] && (
          <button className="btn btn-ghost" onClick={() => seeOnPlan(detail.blocks[0])}>
            <Icon name="calendar-dots" />
            See on plan
          </button>
        )}
        {asking && item.series_id != null ? (
          <span style={{ marginLeft: "auto", display: "flex", gap: 6, alignItems: "center" }}>
            <button className="btn btn-ghost" onClick={() => (drop({ id }), onClose())}>
              Just this one
            </button>
            <button className="btn btn-ghost" onClick={() => (deleteSeries({ id: item.series_id as number }), onClose())} style={{ color: "var(--fr-due)" }}>
              Every one
            </button>
          </span>
        ) : (
          <button className="btn btn-ghost" onClick={() => (item.series_id != null ? setAsking(true) : (drop({ id }), onClose()))} style={{ marginLeft: "auto", color: "var(--fr-due)" }}>
            <Icon name="trash" />
            Delete
          </button>
        )}
      </div>
    </aside>
  )
}
