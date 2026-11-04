// Adding a to-do (v22): type it the way you'd say it; Friday reads the kind, tag, due, length and repeat as you type,
// shown as chips. Click a chip to set it yourself (a pin marks what you set), then Add. `compact` is personal's add
// line at the foot of a to-do section: one ruled line until you type, filling in the section's kind or tag unless
// the line says otherwise, and keeping its place so you can add the next. With a due date, whether you have time for
// it shows under the chips by itself (`components/Fit.tsx`).
//
// Enter on the line, or Shift-Enter anywhere in the box (in a field's picker too), adds it, without a click (28 Oct:
// "i don't like the fact that you have to click into each box"). One with no due date asks first, in the box: Enter or
// Yes adds it as it is (an assignment can have none), or type when it's due ("today") and Enter adds it with that.

import { type KeyboardEvent, useRef, useState } from "react"
import { type CommandInput, query } from "@/api/client"
import { useAreas, useSettings } from "@/hooks/queries"
import { FitLine } from "@/components/Fit"
import { Icon } from "@/components/fr/controls"
import { type Read, readFields, useAdd, useAsk, useParsed } from "@/components/todo/QuickAdd"
import { dur, when } from "@/lib/format"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"
import { DuePicker, LengthPicker, ListPicker, type Repeat, RepeatPicker, repeatLabel } from "./Pickers"

type Field = "preset" | "area" | "due" | "length" | "repeat"
interface Manual {
  preset?: string | null
  area?: string | null
  due?: string | null
  duration_min?: number | null
  repeat?: Repeat
}

export function usePresets(): string[] {
  const settings = useSettings().data as Record<string, unknown> | undefined
  return Object.keys((settings?.presets as Record<string, unknown>) ?? {})
}

interface Props {
  onAdded: (id: number) => void
  inputRef?: (el: HTMLInputElement | null) => void
  longTerm?: boolean
  compact?: boolean
  placeholder?: string
  fill?: { preset?: string; area?: string } // what the section adds to, unless the line or you say otherwise
}

export function AddBox({ onAdded, inputRef, longTerm = false, compact = false, placeholder, fill = {} }: Props) {
  const { today } = useShell()
  const { color } = useLook()
  const [text, setText] = useState("")
  const [focused, setFocused] = useState(false)
  const [manual, setManual] = useState<Manual>({})
  const [open, setOpen] = useState<Field | null>(null)
  const [asking, setAsking] = useState(false) // no due date: add it anyway?
  // What you set, as of now: Shift-Enter in a field sets it and adds in the same moment, before a render.
  const mine = useRef<Manual>({})
  const line = useRef<HTMLInputElement | null>(null)
  const sending = useRef(false)
  const reading = useParsed(text)
  const ai = useAsk(text)
  // What the AI read, when you asked it, stands in for the grammar's reading until the line changes.
  const parsed = readFields(ai.fields ?? reading?.fields ?? {})
  const unread = !!reading && !reading.spans.length && text.trim().split(/\s+/).length > 2 && !ai.fields
  const add = useAdd()
  const presets = usePresets()
  const areas = (useAreas().data ?? []).filter((a) => !a.archived).map((a) => a.name)
  // In a section, its kind stands over Friday's guess from the words; a tag you typed (#psych) stands over its tag.
  const given = (key: string) => (key === "preset" || key === "area" ? (fill[key] ?? null) : null)
  const read = <K extends "preset" | "area" | "due" | "duration_min">(key: K): Read[K] =>
    (key in manual ? (manual[key] ?? null) : key === "preset" ? (given(key) ?? parsed[key]) : (parsed[key] ?? given(key))) as Read[K]
  const preset = read("preset")
  const area = read("area")
  const due = read("due")
  const length = read("duration_min")
  const repeat: Repeat = manual.repeat ?? { every: parsed.every, perWindow: parsed.per_window }
  const set = (change: Manual) => {
    mine.current = { ...mine.current, ...change }
    setManual(mine.current)
  }
  const reset = () => {
    mine.current = {}
    setManual({})
    setOpen(null)
    setAsking(false)
  }
  const payload = (manual: Manual = mine.current) => {
    const fields = {
      ...(fill.preset ? { preset: fill.preset } : {}),
      ...(fill.area && parsed.area == null ? { area: fill.area } : {}),
      ...("preset" in manual ? { preset: manual.preset } : {}),
      ...("area" in manual ? { area: manual.area } : {}),
      ...("due" in manual ? { due: manual.due } : {}),
      ...("duration_min" in manual ? { duration_min: manual.duration_min } : {}),
      ...(manual.repeat ? { every: manual.repeat.every, per_window: manual.repeat.perWindow } : {}),
      ...(longTerm ? { long_term: true } : {}), // added on the Long term list, it belongs there (COMBINED.md 21)
    }
    return ai.fields ? ({ ...ai.fields, ...fields } as CommandInput<"add">) : ({ text, ...fields } as CommandInput<"add">)
  }
  /** Adds the line with what you set (and `extra`, the due typed in the question). With no due date, no repeat and
   * not on the Long term list, it asks first unless `anyway`. */
  const submit = async (extra: Manual = {}, anyway = false) => {
    if (!text.trim() || sending.current) return
    sending.current = true // a second Enter while this one is on its way adds nothing more
    try {
      const manual = { ...mine.current, ...extra }
      if (!anyway && !("due" in manual) && !manual.repeat && !longTerm) {
        // The line as read now, not the reading of a moment ago: "pset due today" and a quick Enter has a due.
        const now = ai.fields ? readFields(ai.fields) : await query("parse", { text }).then((p) => readFields(p.fields ?? {}), () => parsed)
        if (!now.due && !now.every) return setAsking(true)
      }
      const out = await add(payload(manual))
      if (!out) return
      if (out.result.item) onAdded(out.result.item.id)
      setText("")
      reset()
      line.current?.focus()
    } finally {
      sending.current = false
    }
  }
  // Shift-Enter anywhere in the box adds it; a field still being typed (a length) is set as it's left.
  const sendFromAnywhere = (e: KeyboardEvent) => {
    if (e.key !== "Enter" || !e.shiftKey || e.defaultPrevented) return
    e.preventDefault()
    if (document.activeElement instanceof HTMLElement && document.activeElement !== line.current) document.activeElement.blur()
    submit()
  }
  const chips: { field: Field; icon?: string; swatch?: string; text: string; tip: string; manual: boolean }[] = [
    { field: "preset", icon: "shapes", text: preset ?? "Kind", tip: "What sort of work", manual: "preset" in manual },
    { field: "area", swatch: area ? color(area) : undefined, icon: area ? undefined : "tag", text: area ?? "No tag", tip: "What it belongs to", manual: "area" in manual },
    { field: "due", icon: "flag", text: due ? `Due ${when(due, today)}` : "No due date", tip: "When it's due", manual: "due" in manual },
    { field: "length", icon: "clock", text: length ? dur(length) : "Length: Friday guesses", tip: "How long it takes", manual: "duration_min" in manual },
    { field: "repeat", icon: "repeat", text: repeatLabel(repeat), tip: "How often it comes back", manual: !!manual.repeat },
  ]
  const field = (
    <input
      ref={(el) => {
        line.current = el
        inputRef?.(el)
      }}
      value={text}
      onChange={(e) => (setText(e.target.value), setAsking(false))}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.preventDefault(), submit())
        if (e.key === "Escape") (text ? (setText(""), reset()) : e.currentTarget.blur())
      }}
      placeholder={placeholder ?? "Add a to-do, the way you’d say it"}
      aria-label={placeholder ?? "Add a to-do"}
      style={{ flex: 1, minWidth: 0, border: 0, outline: 0, background: "transparent", color: "var(--color-text)", font: "inherit", fontSize: compact ? 13 : 16, padding: 0 }}
    />
  )
  const extras = (
    <>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, paddingLeft: compact ? 24 : 28 }}>
        {chips.map((c) => (
          <button
            key={c.field}
            title={c.tip}
            onMouseDown={(e) => e.preventDefault()} // keeps the line focused
            onClick={() => setOpen(open === c.field ? null : c.field)}
            className="fr-plain"
            style={{
              display: "inline-flex",
              gap: 6,
              alignItems: "center",
              padding: compact ? "2px 7px" : "3px 9px",
              borderRadius: "var(--radius-sm)",
              background: open === c.field ? "color-mix(in srgb, var(--color-accent) 18%, transparent)" : "color-mix(in srgb, var(--color-text) 6%, transparent)",
              boxShadow: open === c.field ? "inset 0 0 0 1px var(--color-accent-500)" : "none",
              color: c.manual || parsedFor(c.field, parsed) || givenFor(c.field, fill) ? "var(--color-text)" : "var(--color-neutral-400)",
              fontSize: compact ? 11 : 12,
            }}
          >
            {c.swatch ? <span className="fr-swatch" style={{ background: c.swatch }} /> : <Icon name={c.icon ?? "tag"} size={12} />}
            {c.text}
            {c.manual && <Icon name="push-pin" size={11} style={{ color: "var(--color-accent-300)" }} />}
            <Icon name="caret-down" size={10} style={{ opacity: 0.6 }} />
          </button>
        ))}
      </div>
      {open && (
        <div style={{ marginLeft: compact ? 24 : 28, padding: "10px 12px", borderRadius: "var(--radius-md)", background: "var(--color-surface)", boxShadow: "0 0 0 1px color-mix(in srgb, var(--color-text) 7%, transparent)", display: "flex", flexDirection: "column", gap: 8 }}>
          <span style={{ fontSize: 12, color: "var(--color-neutral-400)" }}>{chips.find((c) => c.field === open)?.tip}</span>
          {open === "preset" && <ListPicker options={presets.map((p) => ({ value: p as string | null, label: p }))} value={preset} onPick={(v) => (set({ preset: v }), setOpen(null))} />}
          {open === "area" && (
            <ListPicker
              options={[{ value: null as string | null, label: "No tag" }, ...areas.map((a) => ({ value: a as string | null, label: a, swatch: color(a) }))]}
              value={area}
              onPick={(v) => (set({ area: v }), setOpen(null))}
            />
          )}
          {open === "due" && <DuePicker value={due} today={today} onPick={(v) => (set({ due: v }), setOpen(null), line.current?.focus())} onSend={(v) => submit(v === undefined ? {} : { due: v })} />}
          {open === "length" && <LengthPicker value={length} onPick={(v) => set({ duration_min: v })} />}
          {open === "repeat" && <RepeatPicker value={repeat} onPick={(v) => set({ repeat: v })} />}
        </div>
      )}
      {asking && (
        <div
          role="group"
          aria-label="No due date"
          style={{ marginLeft: compact ? 24 : 28, padding: "10px 12px", borderRadius: "var(--radius-md)", background: "var(--color-surface)", boxShadow: "0 0 0 1px color-mix(in srgb, var(--color-accent) 35%, transparent)", display: "flex", flexDirection: "column", gap: 8 }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <span style={{ fontSize: 13 }}>No due date. Add it anyway?</span>
            <button className="btn btn-primary fr-press" onMouseDown={(e) => e.preventDefault()} onClick={() => submit({}, true)} style={{ fontSize: 12, padding: "3px 10px", minHeight: 0 }}>
              Yes, add <span className="fr-mono" style={{ opacity: 0.7, fontSize: 11 }}>↵</span>
            </button>
            <button className="fr-link" onMouseDown={(e) => e.preventDefault()} onClick={() => (setAsking(false), line.current?.focus())} style={{ fontSize: 12 }}>
              Cancel
            </button>
          </div>
          <DuePicker
            value={null}
            today={today}
            placeholder="or type when it's due: today, fri 5pm…"
            onPick={(v) => submit({ due: v }, true)}
            onEnterEmpty={() => submit({}, true)}
            onSend={(v) => submit(v === undefined ? {} : { due: v }, true)}
            onDone={() => (setAsking(false), line.current?.focus())}
          />
        </div>
      )}
      {due && text.trim() && (
        <div style={{ paddingLeft: compact ? 24 : 28 }}>
          <FitLine command="add" input={payload() as Record<string, unknown>} compact={compact} />
        </div>
      )}
      {(unread || ai.fields || ai.error) && (
        <div style={{ paddingLeft: compact ? 24 : 28, display: "flex", gap: 8, alignItems: "center", fontSize: 12 }}>
          {ai.fields ? (
            <span style={{ color: "var(--color-accent-300)" }}>
              <Icon name="sparkle" /> The AI read this line. Add to keep it.
            </span>
          ) : (
            unread && (
              <button className="fr-link" onClick={ai.ask} disabled={ai.busy}>
                <Icon name="sparkle" /> {ai.busy ? "Asking…" : "Ask AI to read this"}
              </button>
            )
          )}
          {ai.error && <span style={{ color: "var(--fr-due)" }}>{ai.error}</span>}
        </div>
      )}
    </>
  )
  if (compact) {
    const ink = longTerm ? "var(--fr-aged)" : "var(--color-accent)"
    return (
      <div onKeyDown={sendFromAnywhere} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <div style={{ display: "flex", alignItems: "center", padding: "7px 0 5px", boxShadow: focused ? `inset 0 -1.5px 0 ${ink}` : "inset 0 -1px 0 var(--fr-rule)", transition: "box-shadow 0.15s" }}>
          <span className="fr-mono" aria-hidden style={{ width: 24, flex: "none", textAlign: "center", fontSize: 12, color: focused ? ink : "var(--color-neutral-500)" }}>
            +
          </span>
          {field}
          {text && (
            <span className="fr-mono" style={{ fontSize: 11, color: "var(--color-neutral-500)", paddingLeft: 8 }}>
              ↵ add · ⇧↵ from any field
            </span>
          )}
        </div>
        {text && extras}
      </div>
    )
  }
  return (
    <div className="fr-well" onKeyDown={sendFromAnywhere} style={{ display: "flex", flexDirection: "column", gap: 10, padding: 14, borderRadius: "var(--radius-lg)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <Icon name="plus" size={18} style={{ color: "var(--color-accent-300)" }} />
        {field}
        <button className="btn btn-primary" onClick={() => submit()} disabled={!text.trim()}>
          Add
        </button>
      </div>
      {extras}
      <div style={{ paddingLeft: 28, fontSize: 12, color: "var(--color-neutral-500)" }}>
        Try <span style={{ color: "var(--color-neutral-300)" }}>reading ch 4 #psych due fri 5pm ~1h</span>. Friday fills in what it can. Click any field to set it yourself.
      </div>
    </div>
  )
}

function givenFor(field: Field, fill: { preset?: string; area?: string }): boolean {
  return (field === "preset" && !!fill.preset) || (field === "area" && !!fill.area)
}

function parsedFor(field: Field, parsed: Read): boolean {
  const key = ({ preset: "preset", area: "area", due: "due", length: "duration_min", repeat: "every" } as const)[field]
  return parsed[key] != null
}
