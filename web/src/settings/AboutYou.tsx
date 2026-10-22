// About you: things told to Friday once, in your own words ("PHYS labs are done in the lab session"), instead of
// waiting for it to learn them. The AI reads them with every email, calendar entry, document and quick-add line.

import { useState } from "react"
import { Chip, Icon } from "@/components/fr/controls"
import { useSettings } from "@/hooks/queries"
import { useCommand } from "@/hooks/useCommand"
import { SectionHead } from "./SettingsPage"

const EXAMPLES = [
  "PHYS 1110 labs are done during the lab session; they need no homework time",
  "CHEM problem sets take me about 3 hours",
  "Quizzes are in class; don't plan prep for them",
  "I'm in the Tuesday physics section, so use the TWR deadlines",
  "Ignore RA and career-fair emails",
]

/** Your notes, and a way to add one from anywhere (the inbox's "why?"). */
export function useNotes(): { notes: string[]; add: (note: string) => void; remove: (i: number) => void } {
  const notes = ((useSettings().data as Record<string, unknown> | undefined)?.notes ?? []) as string[]
  const save = useCommand("settings_set", { label: () => "Friday will remember that" })
  return {
    notes,
    add: (note) => {
      const text = note.trim()
      if (text && !notes.includes(text)) save({ key: "notes", value: [...notes, text] })
    },
    remove: (i) => save({ key: "notes", value: notes.filter((_, j) => j !== i) }),
  }
}

export function AboutYou() {
  const { notes, add, remove } = useNotes()
  const [text, setText] = useState("")
  const submit = () => {
    add(text)
    setText("")
  }
  return (
    <>
      <SectionHead title="About you" note="Tell Friday something once, in your own words. It reads these with every email, calendar entry and document, so it skips what needs no time, uses your lengths and your section's deadlines." />
      <div style={{ display: "flex", flexDirection: "column", gap: 6, paddingBottom: 18 }}>
        {notes.map((n, i) => (
          <div key={n} className="fr-row" style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 10px", borderRadius: "var(--radius-md)", background: "var(--color-bg)" }}>
            <span style={{ flex: 1, textWrap: "pretty" }}>{n}</span>
            <button className="btn btn-ghost" onClick={() => remove(i)} aria-label={`Forget: ${n}`} style={{ padding: "2px 6px" }}>
              <Icon name="x" />
            </button>
          </div>
        ))}
        {!notes.length && <span className="fr-kicker">Nothing yet. Some things people tell Friday:</span>}
      </div>
      <div style={{ display: "flex", gap: 8, maxWidth: 640 }}>
        <input className="input" value={text} maxLength={300} placeholder="e.g. Lab reports take me about 2 hours" onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} style={{ flex: 1 }} />
        <button className="btn btn-primary" disabled={!text.trim()} onClick={submit}>
          Add
        </button>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, paddingTop: 12 }}>
        {EXAMPLES.filter((e) => !notes.includes(e)).map((e) => (
          <Chip key={e} onClick={() => setText(e)}>
            {e}
          </Chip>
        ))}
      </div>
      <span className="fr-kicker" style={{ paddingTop: 14 }}>
        Notes apply to what Friday reads from now on; what's already in your inbox stays as it was read.
      </span>
    </>
  )
}
