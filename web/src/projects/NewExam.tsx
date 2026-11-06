// A new exam: its name, day, start and length, its course's tag, and about how much prep it needs. The exam goes on
// the calendar; the prep is a task due when it starts, which Friday never plans after it. Escape or a click outside
// closes it.

import { useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { ApiError, command } from "@/api/client"
import { useToast } from "@/components/Toasts"
import { Chip, H, Icon, Seg } from "@/components/fr/controls"
import { undoAll } from "@/hooks/useCommand"
import { useAreas } from "@/hooks/queries"
import { dur } from "@/lib/format"
import { addDays, fromMin, toMin } from "@/lib/time"
import { useLook } from "@/theme/LookProvider"
import { useShell } from "@/shell/ShellContext"
import { TimeInput } from "@/components/fr/TimeInput"
import { EXAM_HOURS } from "@/lib/ampm"

const LENGTHS = [
  { value: 60, label: "1h" },
  { value: 90, label: "1h 30m" },
  { value: 120, label: "2h" },
  { value: 180, label: "3h" },
]

export function NewExam({ onClose }: { onClose: (made?: boolean) => void }) {
  const { today } = useShell()
  const { color } = useLook()
  const areas = (useAreas().data ?? []).filter((a) => !a.archived).map((a) => a.name)
  const [title, setTitle] = useState("")
  const [day, setDay] = useState(addDays(today, 7))
  const [time, setTime] = useState("09:00")
  const [length, setLength] = useState(90)
  const [area, setArea] = useState<string | null>(null)
  const [prep, setPrep] = useState(4)
  useEffect(() => {
    const escape = (e: KeyboardEvent) => e.key === "Escape" && onClose()
    window.addEventListener("keydown", escape, true)
    return () => window.removeEventListener("keydown", escape, true)
  }, [onClose])
  const client = useQueryClient()
  const toast = useToast()
  const start = `${day}T${time}`
  // The exam and its prep are one action: one toast, and Undo takes back both.
  const create = async () => {
    const ids: number[] = []
    try {
      const made = await command("add", { title, preset: "Exam", start, end: fromMin(toMin(start) + length), area })
      if (made.command_id !== null) ids.push(made.command_id)
      const id = made.result.item?.id
      if (id && prep) {
        const prepped = await command("add", { title: `Prep: ${title}`, preset: "Exam prep", due: start, duration_min: prep * 60, area, before: [id] })
        if (prepped.command_id !== null) ids.push(prepped.command_id)
      }
      toast({ message: prep ? "Exam and its prep added" : "Exam added", action: { label: "Undo", run: () => undoAll(client, toast, ids) } })
      onClose(true)
    } catch (error) {
      toast({ message: error instanceof ApiError ? error.message : String(error), tone: "error" })
      if (ids.length) onClose(true) // the exam was made; only its prep wasn't
    } finally {
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
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span className="fr-kicker">Length</span>
            <Seg options={LENGTHS} value={length} onPick={setLength} label="Length" />
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
          <button className="btn btn-icon btn-secondary" onClick={() => setPrep(Math.max(0, prep - 1))} aria-label="Less prep" style={{ width: 26, height: 26 }}>
            <Icon name="minus" />
          </button>
          <span className="tnum" style={{ width: 56, flex: "none", whiteSpace: "nowrap", textAlign: "center" }}>
            {prep ? dur(prep * 60) : "None"}
          </span>
          <button className="btn btn-icon btn-secondary" onClick={() => setPrep(prep + 1)} aria-label="More prep" style={{ width: 26, height: 26 }}>
            <Icon name="plus" />
          </button>
          <span className="fr-kicker" style={{ flexBasis: "100%" }}>
            Friday plans it in the days before, never after. Add study guides or practice exams on the card after.
          </span>
        </div>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button className="btn btn-ghost" onClick={() => onClose()}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={create} disabled={!title.trim()}>
            Add exam
          </button>
        </div>
      </div>
    </div>
  )
}
