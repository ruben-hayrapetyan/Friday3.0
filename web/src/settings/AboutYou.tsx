// Notes about you: things told to Friday once, in your own words ("PHYS labs are done in the lab session"), instead
// of waiting for it to learn them. The AI reads them with every email, calendar entry, document and quick-add line.
// Kept and shown on the Rules page (12 Nov), beside the rules: rules change the plan, notes change what's read.

import { useSettings } from "@/hooks/queries"
import { useCommand } from "@/hooks/useCommand"

export const NOTE_EXAMPLES = [
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
