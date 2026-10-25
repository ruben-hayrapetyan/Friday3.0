// Tags and kinds (v22): each tag's name, colour and hours this week, with its own buffer; kinds in priority order
// (who gets the time when it can't all fit), each with a buffer too, and whether short-term work comes before long.

import { useQuery } from "@tanstack/react-query"
import { Fragment, useState } from "react"
import { query } from "@/api/client"
import { H, Icon, Menu, Seg, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { useAreas, useSettings } from "@/hooks/queries"
import { usePresets } from "@/todo/AddBox"
import { PIGMENTS } from "@/lib/pigments"
import { AUTO_PAINTS, hueOf, paintOf, useLook } from "@/theme/LookProvider"
import { BUFFER_OPTIONS, bufferLabel, useBuffers } from "./buffers"
import { SectionHead } from "./SettingsPage"

// Chroma's paints, and the neutral grey.
const SWATCHES: { id: string; name: string }[] = [...PIGMENTS.map((p) => ({ id: p.id, name: p.name })), { id: "n", name: "Grey" }]

export function TagsKinds() {
  const areas = (useAreas().data ?? []).filter((a) => !a.archived)
  const { light } = useLook()
  const { buffers, set } = useBuffers()
  const add = useCommand("area_add", { label: () => "Tag added" })
  const edit = useCommand("area_edit", { label: () => "Saved" })
  const week = useQuery({ queryKey: ["week_review", "settings"], queryFn: () => query("week_review", {}) }).data
  const hours = new Map((week?.areas ?? []).map((a) => [a.area, a.actual_h]))
  return (
    <>
      <SectionHead title="Tags/Kinds" note="Tags say what something belongs to. Kinds say what sort of work it is. Both can carry their own buffer." />
      {areas.map((a, i) => {
        const hue = hueOf(a.color, i)
        return (
          <div key={a.id} className="fr-row" style={{ display: "grid", gridTemplateColumns: "28px minmax(0,180px) minmax(0,1fr)", gap: "10px 16px", alignItems: "center", padding: "14px 0" }}>
            <span style={{ width: 28, height: 28, borderRadius: 8, background: paintOf(hue, light) }} />
            <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0, gridColumn: "2" }}>
              <NameInput name={a.name} onSave={(name) => edit({ id: a.id, name })} />
              <span className="tnum fr-kicker">{hours.get(a.name) ?? 0} h this week</span>
            </div>
            <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
              {SWATCHES.map((p) => (
                <button
                  key={p.id}
                  onClick={() => edit({ id: a.id, color: p.id })}
                  aria-label={p.name}
                  title={p.name}
                  style={{ width: 22, height: 22, border: 0, borderRadius: 6, background: paintOf(p.id, light), boxShadow: p.id === hue ? "0 0 0 2px var(--color-bg), 0 0 0 3px var(--color-text)" : "none", cursor: "pointer" }}
                />
              ))}
            </div>
            <button className="fr-link" onClick={() => edit({ id: a.id, archived: true })} style={{ fontSize: 11, color: "var(--color-neutral-500)", justifySelf: "start" }}>
              Archive
            </button>
            <span style={{ gridColumn: 3, display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 11, color: "var(--color-neutral-500)" }}>Buffer</span>
              <Seg
                options={[{ value: "default", label: "Default" }, ...BUFFER_OPTIONS.slice(1).map((v) => ({ value: v, label: bufferLabel(v) }))]}
                value={buffers.by_area[a.name] ?? "default"}
                onPick={(v) => {
                  const { [a.name]: _, ...rest } = buffers.by_area
                  set({ by_area: v === "default" ? rest : { ...rest, [a.name]: v } })
                }}
                size="small"
                onBg
              />
            </span>
          </div>
        )
      })}
      <div className="fr-row" style={{ display: "flex", gap: 8, paddingTop: 16 }}>
        <button className="btn btn-secondary" onClick={() => add({ name: `Tag ${areas.length + 1}`, color: AUTO_PAINTS[areas.length % AUTO_PAINTS.length] })}>
          <Icon name="plus" size={15} />
          Add tag
        </button>
        <button className="btn btn-ghost" onClick={() => areas.forEach((a, i) => edit({ id: a.id, color: AUTO_PAINTS[i % AUTO_PAINTS.length] }))}>
          <Icon name="arrow-counter-clockwise" size={15} />
          Auto-assign colors
        </button>
      </div>
      <Kinds />
    </>
  )
}

function NameInput({ name, onSave }: { name: string; onSave: (name: string) => void }) {
  const [value, setValue] = useState(name)
  return (
    <input
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={() => value.trim() && value !== name && onSave(value.trim())}
      onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
      aria-label="Tag name"
      style={{ border: 0, outline: 0, background: "transparent", color: "var(--color-text)", font: "inherit", fontWeight: 500, padding: 0 }}
    />
  )
}

const READ_INTO = ["Assignment", "Exam prep", "Class", "Exam", "Event"] // calendars and mail are read into these

function RemoveKind({ kind, others, onDone }: { kind: string; others: string[]; onDone: () => void }) {
  const remove = useCommand("kind_remove", { label: (o) => o.result.message ?? "Deleted" })
  const [to, setTo] = useState(others[0] ?? "")
  return (
    <div className="fr-well" style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 12px", margin: "6px 0", flexWrap: "wrap" }}>
      <span>Delete {kind}. Anything of this kind becomes</span>
      <Menu options={others.map((o) => ({ value: o, label: o }))} value={to} onPick={setTo} label="Move its items to" />
      <button className="btn btn-primary" onClick={async () => (await remove({ name: kind, move_to: to })) && onDone()} style={{ fontSize: 12 }}>
        Delete
      </button>
      <button className="btn btn-ghost" onClick={onDone} style={{ fontSize: 12 }}>
        Cancel
      </button>
    </div>
  )
}

function AddKind({ presets }: { presets: string[] }) {
  const add = useCommand("kind_add", { label: (o) => o.result.message ?? "Added" })
  const [name, setName] = useState("")
  const [like, setLike] = useState("Assignment")
  return (
    <div className="fr-row" style={{ display: "flex", alignItems: "center", gap: 8, padding: "12px 0", flexWrap: "wrap" }}>
      <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="New kind, e.g. Lab report" style={{ width: 200, padding: "5px 8px", minHeight: 0 }} />
      <span className="fr-kicker">works like</span>
      <Menu options={presets.map((p) => ({ value: p, label: p }))} value={like} onPick={setLike} label="Starts as a copy of" />
      <button className="btn btn-secondary" disabled={!name.trim()} onClick={async () => (await add({ name: name.trim(), like })) && setName("")} style={{ fontSize: 12 }}>
        Add kind
      </button>
    </div>
  )
}

function Kinds() {
  const presets = usePresets()
  const settings = useSettings().data as Record<string, unknown> | undefined
  const order = (settings?.kind_order as string[]) ?? []
  const save = useCommand("settings_set", { label: () => "Order saved" })
  const saveShort = useCommand("settings_set", { label: () => "Saved" })
  const { buffers, set } = useBuffers()
  const ranked = [...order.filter((p) => presets.includes(p)), ...presets.filter((p) => !order.includes(p))]
  const [removing, setRemoving] = useState<string | null>(null)
  const move = (i: number, by: number) => {
    const next = [...ranked]
    const j = i + by
    if (j < 0 || j >= next.length) return
    ;[next[i], next[j]] = [next[j], next[i]]
    save({ key: "kind_order", value: next })
  }
  return (
    <>
      <div style={{ display: "flex", flexDirection: "column", gap: 4, paddingTop: 34, paddingBottom: 10 }}>
        <H size={22}>Kinds, in priority order</H>
        <span className="fr-kicker" style={{ textWrap: "pretty" }}>
          When things genuinely can’t all fit before their deadlines, kinds higher on the list get the time first. Order doesn’t matter when everything fits.
        </span>
      </div>
      <div className="fr-row" style={{ display: "flex", alignItems: "center", gap: 14, padding: "12px 0" }}>
        <span style={{ display: "flex", flexDirection: "column", gap: 2, flex: 1, minWidth: 0 }}>
          <span style={{ fontWeight: 500 }}>Short term before long term</span>
          <span className="fr-kicker">Your Long term list gets only the time your Short term list leaves.</span>
        </span>
        <Switch on={!!settings?.short_term_first} onToggle={() => saveShort({ key: "short_term_first", value: !settings?.short_term_first })} label="Short term before long term" />
      </div>
      {ranked.map((k, i) => (
        <Fragment key={k}>
        <div className="fr-row" style={{ display: "grid", gridTemplateColumns: "24px 22px minmax(0,1fr) auto 28px", gap: 14, alignItems: "center", padding: "12px 0" }}>
          <span className="fr-h tnum" style={{ fontSize: 18, color: "var(--color-neutral-400)" }}>
            {i + 1}
          </span>
          <span style={{ display: "flex", flexDirection: "column" }}>
            <button className="fr-plain" onClick={() => move(i, -1)} disabled={i === 0} aria-label="Move up" style={{ height: 13, color: "var(--color-neutral-300)", opacity: i === 0 ? 0.3 : 1 }}>
              <Icon name="caret-up" size={13} />
            </button>
            <button className="fr-plain" onClick={() => move(i, 1)} disabled={i === ranked.length - 1} aria-label="Move down" style={{ height: 13, color: "var(--color-neutral-300)", opacity: i === ranked.length - 1 ? 0.3 : 1 }}>
              <Icon name="caret-down" size={13} />
            </button>
          </span>
          <span style={{ fontWeight: 500 }}>{k}</span>
          <span style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
            <span style={{ fontSize: 11, color: "var(--color-neutral-500)" }}>Buffer</span>
            <Seg
              options={[{ value: "default", label: "Default" }, ...BUFFER_OPTIONS.slice(1).map((v) => ({ value: v, label: bufferLabel(v) }))]}
              value={buffers.by_preset[k] ?? "default"}
              onPick={(v) => {
                const { [k]: _, ...rest } = buffers.by_preset
                set({ by_preset: v === "default" ? rest : { ...rest, [k]: v } })
              }}
              size="small"
              onBg
            />
          </span>
          {READ_INTO.includes(k) ? (
            <span title="Calendars and mail are read into this kind" />
          ) : (
            <button className="btn btn-icon btn-ghost" onClick={() => setRemoving(removing === k ? null : k)} aria-label={`Delete ${k}`} style={{ width: 28, height: 28, color: "var(--color-neutral-500)" }}>
              <Icon name="trash" />
            </button>
          )}
        </div>
        {removing === k && <RemoveKind kind={k} others={ranked.filter((o) => o !== k)} onDone={() => setRemoving(null)} />}
        </Fragment>
      ))}
      <AddKind presets={presets} />
      <span className="fr-kicker" style={{ paddingTop: 10 }}>
        When a block’s tag and kind both have a buffer, the larger one is used. “Default” uses the buffer from Schedule.
      </span>
    </>
  )
}
