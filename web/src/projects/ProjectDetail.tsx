// One project (v22): its steps in order (move them, tick them, set what each waits on and how long it takes), and a
// timeline of when each is planned against the due date, and a way to the other projects. Shown in the Projects page's
// popup (17 Nov): the popup has its close at the top right, so there's no way back of its own.

import { useRef, useState } from "react"
import { createPortal } from "react-dom"
import type { Item } from "@/api/client"
import { Box, Check, H, Icon, Menu } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useHorizon, useSettings } from "@/hooks/queries"
import { dur, when } from "@/lib/format"
import { LengthField } from "@/todo/Pickers"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"
import { Bar, PROJECT_STATUS, type Project, projectPct, StatusTag, TagMenu, TONE, useTag } from "./parts"
import { Timeline } from "./Timeline"
import { usePopupStrip } from "@/projects-v2/Rows"

export function ProjectDetail({ p, all, onPick, top, after }: { p: Project; all: Project[]; onPick: (id: number) => void; top?: React.ReactNode; after?: React.ReactNode }) {
  const { today, layout } = useShell()
  const { color } = useLook()
  const blocks = useHorizon().data?.blocks ?? []
  const add = useCommand("add", { label: () => "Step added" })
  const reorder = useCommand("reorder", { label: () => "Reordered" })
  // A project you'll do again, as a template New project offers (3 Nov: `template_save` had no button)
  const saveTemplate = useCommand("template_save", { label: (o) => `${o.result.message ?? "Saved"}: New project offers it` })
  // One of that name already saved is asked about here, not written over (15 Nov, your choice on a client's notes)
  const templates = ((useSettings().data as Record<string, unknown> | undefined)?.templates ?? {}) as Record<string, unknown>
  const [asked, setAsked] = useState<number | null>(null) // the project it's asking for, so another doesn't show it
  const replacing = asked === p.item.id
  const save = () => (setAsked(null), saveTemplate({ name: p.item.title, project_id: p.item.id }))
  const retag = useTag(p.item.id, p.item.title)
  const tag = p.item.area
  const [text, setText] = useState("")
  const sending = useRef(false) // ↩ twice adds the step once
  const addStep = async () => {
    if (!text.trim() || sending.current) return
    sending.current = true
    try {
      if (await add({ text, parent_id: p.item.id, area: tag })) setText("")
    } finally {
      sending.current = false
    }
  }
  const steps = p.children.filter((c) => c.parent_id === p.item.id)
  const total = p.done_min + p.remaining_min
  const [label, tone] = PROJECT_STATUS[p.status]
  const doneSteps = steps.filter((s) => s.status === "done").length
  const move = (i: number, by: number) => {
    const ids = steps.map((s) => s.id)
    const j = i + by
    if (j < 0 || j >= ids.length) return
    ;[ids[i], ids[j]] = [ids[j], ids[i]]
    reorder({ parent_id: p.item.id, ids })
  }
  const strip = usePopupStrip()
  const tools = (
    <>
      {steps.length > 0 && replacing && (
        <span style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap", fontSize: 12.5 }}>
          <span>A template called “{p.item.title}” is saved already. Replace it?</span>
          <button className="btn btn-ghost" onClick={save} style={{ fontSize: 12.5 }}>
            Replace
          </button>
          <button className="btn btn-ghost" onClick={() => setAsked(null)} style={{ fontSize: 12.5 }}>
            Keep it
          </button>
        </span>
      )}
      {steps.length > 0 && !replacing && (
        <button className="btn btn-ghost" onClick={() => (Object.keys(templates).includes(p.item.title) ? setAsked(p.item.id) : save())} aria-label="Save as template" title="Its steps, in this order and with their share of the hours, for the next project like it" style={{ fontSize: 12.5 }}>
          <Icon name="copy-simple" size={13} />
          {!layout.tight && "Save as template" /* a narrow window: its icon, as the page's header buttons are */}
        </button>
      )}
      {all.length > 1 && <Menu label="Project" value={String(p.item.id)} onPick={(v) => onPick(Number(v))} options={all.map((o) => ({ value: String(o.item.id), label: o.item.title }))} />}
    </>
  )
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24, minWidth: 0 }}>
      {/* its tools on the popup's top strip, beside its close (✕); in a row of their own anywhere else */}
      {strip ? createPortal(tools, strip) : (steps.length > 0 || all.length > 1) && <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 12, flexWrap: "wrap" }}>{tools}</div>}
      <div style={{ display: "flex", alignItems: "flex-end", gap: 20, flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: "min(260px, 100%)", display: "flex", flexDirection: "column", gap: 8 }}>
          <span className="fr-eyebrow" style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span className="fr-swatch" style={{ background: color(tag, p.item.preset) }} />
            <TagMenu title={p.item.title} value={tag} onPick={retag} /> · {p.item.preset ?? "Project"}
          </span>
          <H size={layout.tight ? 28 : 32} style={{ overflowWrap: "anywhere" }}>
            {p.item.title}
          </H>
          <span className="tnum" style={{ color: "var(--color-neutral-300)" }}>
            {p.item.due && !top ? `Due ${when(p.item.due, today)} · ` : ""}
            {doneSteps} of {steps.length} steps done · {dur(total)} in all
          </span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, width: layout.tight ? "100%" : 240 }}>
          <div className="tnum" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, fontSize: 12 }}>
            <span style={{ color: "var(--color-neutral-300)" }}>
              {dur(p.done_min)} of {dur(total)}
            </span>
            <StatusTag label={label} tone={tone} />
          </div>
          <Bar pct={projectPct(p)} color={color(tag, p.item.preset)} />
        </div>
      </div>
      {top /* what a page adds over its steps (the Projects page: its due and how firm) */}
      <div style={{ display: "flex", flexDirection: "column" }}>
        <div style={{ display: "grid", gridTemplateColumns: cols(layout.tight), gap: 12, padding: "0 0 6px", fontSize: 11, color: "var(--color-neutral-500)" }}>
          <span />
          <span />
          <span>Step</span>
          {!layout.tight && <span>Waits on</span>}
          <span style={{ textAlign: "right" }}>Length</span>
          {!layout.tight && <span style={{ textAlign: "right" }}>Planned</span>}
          <span />
        </div>
        {steps.map((s, i) => (
          <Step key={s.id} step={s} steps={steps} first={i === 0} last={i === steps.length - 1} next={blocks.find((b) => b.item_id === s.id)?.start ?? null} later={p.step_finish?.[String(s.id)] ?? null} onMove={(by) => move(i, by)} />
        ))}
        <div className="fr-row" style={{ display: "flex", gap: 8, alignItems: "center", padding: "10px 0" }}>
          <Icon name="plus" style={{ color: "var(--color-neutral-500)", marginLeft: 40 }} />
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addStep()}
            placeholder="Add a step ~2h"
            aria-label="Add a step"
            style={{ flex: 1, minWidth: 0, border: 0, outline: 0, background: "transparent", color: "var(--color-text)", font: "inherit" }}
          />
        </div>
      </div>
      <Timeline p={p} steps={steps} tone={TONE[tone]} />
      {after /* what a page adds under it (the new layout: notes and options) */}
    </div>
  )
}

// The steps' columns; a narrow window keeps the name and length, with when it's planned and what it waits on
// under the name.
const cols = (tight: boolean) => (tight ? "22px 18px minmax(0,1fr) auto 28px" : "22px 18px minmax(0,1fr) 170px 96px 124px 28px")

function Step({ step, steps, first, last, next, later, onMove }: { step: Item; steps: Item[]; first: boolean; last: boolean; next: string | null; later: string | null; onMove: (by: number) => void }) {
  const { today, layout } = useShell()
  const [open, setOpen] = useState(false)
  const done = useCommand("done", { label: () => `${step.title}: done` })
  const reopen = useCommand("reopen", { label: () => "Open again" })
  const edit = useCommand("edit", { label: () => "Saved" })
  const drop = useCommand("drop", { label: () => "Deleted" })
  const depend = useCommand("depend", { label: () => "Now waits on it" })
  const undepend = useCommand("undepend", { label: () => "No longer waits" })
  const isDone = step.status === "done"
  const waits = step.waiting_on ?? []
  const names = waits.map((id) => steps.find((s) => s.id === id)?.title).filter(Boolean)
  // Waiting on something that (through its own waits) waits on this one would make a loop.
  const loops = (target: number): boolean => {
    const seen = new Set<number>()
    const stack = [target]
    while (stack.length) {
      const at = stack.pop() as number
      if (at === step.id) return true
      if (seen.has(at)) continue
      seen.add(at)
      stack.push(...(steps.find((s) => s.id === at)?.waiting_on ?? []))
    }
    return false
  }
  const length = step.duration_min ?? 60
  // planned past the plan's two weeks, nearer its due, isn't "not planned" (17 Nov: "open subtasks say not planned
  // even with ample time")
  const planned = isDone ? "Done" : next ? when(next, today) : later ? `Later, by ${when(later, today)}` : "No room before its due"
  const waitsOn = (
    <button onClick={() => setOpen(!open)} className="fr-plain" title={names.join(", ") || "Nothing"} style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 8px", borderRadius: "var(--radius-md)", background: "var(--color-bg)", boxShadow: open ? "inset 0 0 0 1px var(--color-accent-500)" : "0 0 0 1px color-mix(in srgb, var(--color-text) 7%, transparent)", color: names.length ? "var(--color-text)" : "var(--color-neutral-500)", fontSize: 12, minWidth: 0, ...(layout.tight ? { padding: 0, background: "none", boxShadow: "none", maxWidth: "100%" } : {}) }}>
      <span style={{ flex: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{layout.tight ? `Waits on ${names.join(", ") || "nothing"}` : names.join(", ") || "Nothing"}</span>
      <Icon name="caret-down" size={10} style={{ opacity: 0.6 }} />
    </button>
  )
  return (
    <div className="fr-row" style={{ display: "grid", gridTemplateColumns: cols(layout.tight), gap: 12, alignItems: "center", padding: "10px 0", opacity: isDone ? 0.55 : 1 }}>
      <span style={{ display: "flex", flexDirection: "column" }}>
        <button className="fr-plain" onClick={() => onMove(-1)} aria-label="Move up" style={{ height: 12, color: "var(--color-neutral-400)", opacity: first ? 0.25 : 1 }}>
          <Icon name="caret-up" size={12} />
        </button>
        <button className="fr-plain" onClick={() => onMove(1)} aria-label="Move down" style={{ height: 12, color: "var(--color-neutral-400)", opacity: last ? 0.25 : 1 }}>
          <Icon name="caret-down" size={12} />
        </button>
      </span>
      <Check done={isDone} onToggle={() => (isDone ? reopen({ id: step.id }) : done({ id: step.id }))} />
      <span style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
        <span style={{ fontWeight: 500, textDecoration: isDone ? "line-through" : undefined, overflowWrap: "anywhere" }}>{step.title}</span>
        {names.length > 0 && !isDone && (
          <span style={{ fontSize: 12, color: "var(--fr-warn)" }}>
            <Icon name="hourglass-medium" size={11} /> Waiting on {names.join(", ")}
          </span>
        )}
        {layout.tight && (
          <span style={{ display: "flex", flexWrap: "wrap", alignItems: "center", columnGap: 10, rowGap: 2, paddingTop: 2, minWidth: 0 }}>
            <span className="tnum" style={{ flex: "none", fontSize: 12, color: "var(--color-neutral-400)" }}>
              {planned}
            </span>
            {waitsOn}
          </span>
        )}
      </span>
      {!layout.tight && waitsOn}
      <span className="tnum" style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 4, fontSize: 12 }}>
        <LengthField value={length} onPick={(m) => m && m !== length && edit({ id: step.id, duration_min: m })} label={`Length of ${step.title}`} amounts={[15, 30, 60, 120, 240, 480]} />
      </span>
      {!layout.tight && (
        <span className="tnum" style={{ textAlign: "right", fontSize: 12, color: "var(--color-neutral-300)" }}>
          {planned}
        </span>
      )}
      <button className="btn btn-icon btn-ghost" onClick={() => drop({ id: step.id })} aria-label="Delete step" title="Delete step" style={{ width: 28, height: 28, color: "var(--color-neutral-500)" }}>
        <Icon name="trash" />
      </button>
      {open && (
        <div style={{ gridColumn: "3 / -1", display: "flex", flexDirection: "column", gap: 2, padding: "8px 10px", borderRadius: "var(--radius-md)", background: "var(--color-bg)" }}>
          <span style={{ fontSize: 11, color: "var(--color-neutral-500)", paddingBottom: 4 }}>{step.title} waits on</span>
          {steps
            .filter((s) => s.id !== step.id)
            .map((s) => {
              const on = waits.includes(s.id)
              const cyc = !on && loops(s.id)
              return (
                <button key={s.id} disabled={cyc} onClick={() => (on ? undepend({ item_id: step.id, depends_on_id: s.id }) : depend({ item_id: step.id, depends_on_id: s.id }))} className="fr-plain fr-hover-soft" style={{ display: "flex", alignItems: "center", gap: 10, padding: "5px 4px", fontSize: 12, opacity: cyc ? 0.4 : 1 }}>
                  <Box on={on} />
                  {s.title}
                  {cyc && <span style={{ fontSize: 11, color: "var(--color-neutral-500)" }}>would loop</span>}
                </button>
              )
            })}
          <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: 4 }}>
            <button className="btn btn-ghost" onClick={() => setOpen(false)} style={{ fontSize: 12, padding: "3px 10px" }}>
              Done
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
