// A new exam: its name, day, start and length, its course's tag, about how much prep it needs, and how many days
// before it only this class's work is planned (its exam focus, as its popup sets it after). The exam goes on the
// calendar; the prep is a task due when it starts, which Friday never plans after it. Escape or a click outside closes
// it.

import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useRef, useState } from "react"
import { command, errorWords, query } from "@/api/client"
import { useToast } from "@/components/Toasts"
import { Chip, H } from "@/components/fr/controls"
import { undoAll } from "@/hooks/useCommand"
import { useAreas, useSettings } from "@/hooks/queries"
import { Choices, DropField } from "@/projects-v2/Rows"
import { useRules } from "@/rules/RulesPage"
import { type FocusPick, focusChoices, focusOf, focusValue } from "./examFocus"
import { dur } from "@/lib/format"
import { addDays, fromMin, toMin } from "@/lib/time"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"
import { TimeInput } from "@/components/fr/TimeInput"
import { EXAM_HOURS } from "@/lib/ampm"
import { LengthField, LengthInput } from "@/todo/Pickers"

// The usual lengths a click away, and a box for any other, typed as you'd say it (15 Nov, a client: a 2h 30m final
// had no way in)
const LENGTHS = [45, 60, 90, 120, 150, 180]

export function NewExam({ onClose }: { onClose: (made?: boolean) => void }) {
  const { today } = useShell()
  const { color } = useLook()
  const areas = (useAreas().data ?? []).filter((a) => !a.archived).map((a) => a.name)
  const [title, setTitle] = useState("")
  const [day, setDay] = useState(addDays(today, 7))
  const [time, setTime] = useState("09:00")
  const [length, setLength] = useState(90)
  const [area, setArea] = useState<string | null>(null)
  const [prep, setPrep] = useState(240) // minutes; typed or a step of an hour at a time
  // its exam focus (19 Nov, a user's notes: "add dropdown for customizing the exam focus ... e.g. start focusing on
  // that class's work 3 days before"): as your rule gives an exam of this name, unless you pick its own
  const [focus, setFocus] = useState<FocusPick>("rule")
  const named = title.trim()
  const ruleDays = useQuery({ queryKey: ["exam_focus_for", named], queryFn: () => query("exam_focus_for", { title: named }), placeholderData: keepPreviousData }).data?.days ?? null
  const ruleOn = (useRules().data ?? []).some((r) => r.type === "exam_focus" && r.enabled)
  const each = ((useSettings().data as Record<string, unknown> | undefined)?.exam_focus_each ?? {}) as Record<string, number | null>
  const days = focusOf(focus, ruleDays)
  const focusShown = `${focusValue(days)}${focus === "rule" && ruleOn ? " (your rule)" : ""}`
  useEffect(() => {
    const escape = (e: KeyboardEvent) => e.key === "Escape" && onClose()
    window.addEventListener("keydown", escape, true)
    return () => window.removeEventListener("keydown", escape, true)
  }, [onClose])
  const client = useQueryClient()
  const toast = useToast()
  const start = `${day}T${time}`
  // Once: a second click while the first is on its way made a second exam and prep (audit, 12 Nov).
  const sending = useRef(false)
  const [busy, setBusy] = useState(false)
  // The exam and its prep are one action: one toast, and Undo takes back both.
  const create = async () => {
    if (sending.current) return
    sending.current = true
    setBusy(true)
    const ids: number[] = []
    try {
      const made = await command("add", { title, preset: "Exam", start, end: fromMin(toMin(start) + length), area })
      if (made.command_id !== null) ids.push(made.command_id)
      const id = made.result.item?.id
      if (id && prep) {
        const prepped = await command("add", { title: `Prep: ${title}`, preset: "Exam prep", due: start, duration_min: prep, area, before: [id] })
        if (prepped.command_id !== null) ids.push(prepped.command_id)
      }
      if (id && focus !== "rule") {
        const set = await command("settings_set", { key: "exam_focus_each", value: { ...each, [String(id)]: focus === "none" ? null : focus } })
        if (set.command_id !== null) ids.push(set.command_id)
      }
      toast({ message: prep ? "Exam and its prep added" : "Exam added", action: { label: "Undo", run: () => undoAll(client, toast, ids) } })
      onClose(true)
    } catch (error) {
      toast({ message: errorWords(error), tone: "error" })
      if (ids.length) onClose(true) // the exam was made; only its prep wasn't
    } finally {
      sending.current = false
      setBusy(false)
      client.invalidateQueries()
    }
  }
  return (
    <div className="fr-scrim">
      <div onClick={() => onClose()} style={{ position: "absolute", inset: 0 }} />
      <div role="dialog" aria-modal="true" aria-label="New exam" className="fr-float fr-dialog" style={{ width: "min(560px, 100%)" }}>
        <H size={26}>New exam</H>
        <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Name, e.g. MATH 2940 Prelim 2" style={{ fontSize: 15 }} autoFocus />
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "flex-start" }}>
          <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span className="fr-kicker">Day</span>
            <input className="input" type="date" value={day} min={today} onChange={(e) => e.target.value && setDay(e.target.value)} />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span className="fr-kicker">Starts</span>
            <TimeInput value={time} step={300} onChange={(t) => t && setTime(t)} label="Starts" expect={{ hours: EXAM_HOURS }} />
          </label>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, flex: "1 1 260px", minWidth: 0 }}>
            <span className="fr-kicker">Length</span>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
              {LENGTHS.map((m) => (
                <Chip key={m} on={length === m} onClick={() => setLength(m)}>
                  {dur(m)}
                </Chip>
              ))}
              {/* on the buttons' row, as narrow as a length needs (19 Nov, a user's notes: "move text box for length of
                  the exam to the same line as the others ... make it less wide"): its placeholder had widened it */}
              <LengthInput value={length} onPick={(m) => m && setLength(m)} width={84} placeholder="e.g. 2h 15m" />
            </div>
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <span className="fr-kicker">Course</span>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            <Chip on={area === null} onClick={() => setArea(null)}>
              No tag
            </Chip>
            {areas.map((a) => (
              <Chip key={a} on={area === a} swatch={color(a)} onClick={() => setArea(a)}>
                {a}
              </Chip>
            ))}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span className="fr-kicker" style={{ width: 120 }}>
            Prep it needs
          </span>
          {/* a value that opens common amounts and a box to type any (16 Nov: "what if i need 100 hours, i just want to type it") */}
          <LengthField value={prep || null} onPick={(m) => setPrep(m ?? 0)} label="Prep it needs" none="None" amounts={[60, 120, 240, 360, 600, 1200]} />
          <span className="fr-kicker" style={{ flexBasis: "100%" }}>
            Friday plans it in the days before, never after. Add study guides or practice exams on the card after.
          </span>
        </div>
        {/* said as the exam's popup says it, on a row of its own with what it does (20 Nov, the user, of "Focus on its
            class": "not sure what that means") */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span className="fr-kicker" style={{ width: 120 }}>
            Before this exam
          </span>
          <DropField label="Before this exam" value={focusShown}>
            {(close) => <Choices label="Before this exam" value={focus} onPick={(d: FocusPick) => (setFocus(d), close())} options={focusChoices(ruleDays, ruleOn)} />}
          </DropField>
          <span className="fr-kicker" style={{ flexBasis: "100%" }}>
            Work for other classes due after it can wait until it's over.
          </span>
        </div>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", alignItems: "center", flexWrap: "wrap" }}>
          <button className="btn btn-ghost" onClick={() => onClose()}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={create} disabled={!title.trim() || busy}>
            Add exam
          </button>
        </div>
      </div>
    </div>
  )
}
