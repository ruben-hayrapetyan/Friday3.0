// One project (v22): its steps in order (move them, tick them, set what each waits on and how long it takes), and a
// timeline of when each is planned against the due date, and a way to the other projects. Shown in the Projects page's
// popup (17 Nov): the popup has its close at the top right, so there's no way back of its own.

import { useRef, useState } from "react"
import { createPortal } from "react-dom"
import type { Item } from "@/api/client"
import { Check, H, Icon, Menu } from "@/components/fr/controls"
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
  // the steps move at once, the server's answer after (17 Nov: "make the reordering instant")
  const reorder = useCommand("reorder", {
    label: () => "Reordered",
    optimistic: (client, input) =>
      client.setQueryData<Project[]>(["projects"], (list) =>
        list?.map((x) => {
          if (x.item.id !== input.parent_id) return x
          const at = new Map(input.ids.map((id, n) => [id, n]))
          const placed = x.children.filter((c) => at.has(c.id)).sort((a, b) => (at.get(a.id) as number) - (at.get(b.id) as number))
          let n = 0
          return { ...x, children: x.children.map((c) => (at.has(c.id) ? placed[n++] : c)) }
        }),
      ),
  })
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
            {/* no steps: worked on as a whole, a to-do of its own (17 Nov, proposal (h)) */}
            {steps.length ? `${doneSteps} of ${steps.length} steps done · ${dur(total)} in all` : `Worked on as a whole · ${dur(total)} · Add steps to split it up`}
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
          <span style={{ textAlign: "right" }}>Length</span>
          {!layout.tight && <span style={{ textAlign: "right" }}>Planned</span>}
          <span />
        </div>
        {steps.map((s, i) => (
          <div key={s.id} style={{ display: "contents" }}>
            {i > 0 && <Then step={s} above={steps[i - 1]} project={p} />}
            <Step step={s} linked={i > 0} first={i === 0} last={i === steps.length - 1} next={blocks.find((b) => b.item_id === s.id)?.start ?? null} later={p.step_finish?.[String(s.id)] ?? null} waitsFor={steps.find((x) => x.id === p.waits_for?.[String(s.id)])?.title ?? null} onMove={(by) => move(i, by)} />
          </div>
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
const cols = (tight: boolean) => (tight ? "22px 18px minmax(0,1fr) auto 28px" : "22px 18px minmax(0,1fr) 96px 124px 28px")

/** A step's link to the one above it, said on the step it belongs to, over its name: "after <the step above>", it
 * waits for that one, as steps do; or "doesn't wait". A click switches it, at once (17 Nov, your choice: a project's
 * order is its chain, no "Waits on" of its own). 19 Nov, a user's notes: "then" and "any time" between two steps read
 * as the upper one's ("4 any time → 5" taken for 4 and 5 together after 3); your choice: "Say it on the waiting step". */
function Then({ step, above, project }: { step: Item; above: Item; project: Project }) {
  const anyTime = (project.any_time ?? []).includes(step.id)
  const set = useCommand("step_any_time", {
    label: (o) => `${step.title}: ${o.result.message === "Any time" ? "doesn't wait" : `after ${above.title}`}`,
    optimistic: (client, input) =>
      client.setQueryData<Project[]>(["projects"], (list) =>
        list?.map((x) => (x.item.id !== project.item.id ? x : { ...x, any_time: input.any_time ? [...(x.any_time ?? []).filter((id) => id !== input.id), input.id] : (x.any_time ?? []).filter((id) => id !== input.id) })),
      ),
  })
  return (
    // the dividing line above it, the step below it: the line had run through it (20 Nov, a user's notes: "dependence
    // relationship between sub-tasks is placed directly on the separating line"); its step's row draws no line of its own
    <button
      className="fr-plain fr-hover-text fr-row"
      data-step-link
      onClick={() => set({ id: step.id, any_time: !anyTime })}
      aria-label={anyTime ? `${step.title} doesn't wait for ${above.title}. Make it wait` : `${step.title} waits: after ${above.title}. Make it not wait`}
      title={anyTime ? `${step.title} doesn't wait for ${above.title}: it can be done before it. Click to make it wait` : `${step.title} starts once ${above.title} is done. Click so it doesn't wait`}
      style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 0 0 46px", marginBottom: -6, minHeight: 18, fontSize: 11, color: anyTime ? "var(--color-neutral-500)" : "var(--color-neutral-400)", alignSelf: "stretch", maxWidth: "100%", minWidth: 0, textAlign: "left" }}
    >
      <Icon name={anyTime ? "arrows-split" : "arrow-down"} size={11} style={{ flex: "none" }} />
      <span style={{ overflowWrap: "anywhere" }}>{anyTime ? "doesn't wait" : `after ${above.title}`}</span>
    </button>
  )
}

function Step({ step, linked, first, last, next, later, waitsFor, onMove }: { step: Item; linked?: boolean; first: boolean; last: boolean; next: string | null; later: string | null; waitsFor: string | null; onMove: (by: number) => void }) {
  const { today, layout } = useShell()
  const done = useCommand("done", { label: () => `${step.title}: done` })
  const reopen = useCommand("reopen", { label: () => "Open again" })
  const edit = useCommand("edit", { label: () => "Saved" })
  const drop = useCommand("drop", { label: () => "Deleted" })
  const isDone = step.status === "done"
  const length = step.duration_min ?? 60
  // planned past the plan's two weeks, nearer its due, isn't "not planned" (17 Nov: "open subtasks say not planned
  // even with ample time")
  // waiting for a step that has no room before its due says so, not "No room" of its own (19 Nov, a user's notes)
  const planned = isDone ? "Done" : next ? when(next, today) : later ? `Later, by ${when(later, today)}` : waitsFor ? `Waits for ${waitsFor}, which has no room before its due` : "No room before its due"
  return (
    <div className="fr-row" data-step-row style={{ display: "grid", gridTemplateColumns: cols(layout.tight), gap: 12, alignItems: "center", padding: "10px 0", opacity: isDone ? 0.55 : 1, boxShadow: linked ? "none" : undefined }}>
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
        {layout.tight && (
          <span style={{ display: "flex", flexWrap: "wrap", alignItems: "center", columnGap: 10, rowGap: 2, paddingTop: 2, minWidth: 0 }}>
            <span className="tnum" style={{ flex: "none", fontSize: 12, color: "var(--color-neutral-400)" }}>
              {planned}
            </span>
          </span>
        )}
      </span>
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
    </div>
  )
}
