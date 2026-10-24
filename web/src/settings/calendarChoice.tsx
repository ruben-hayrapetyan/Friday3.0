// One choice per calendar, the same in Setup and Settings: shown and planned around, shown but free to plan over
// (drawn dashed), or hidden until you switch it on under Show. Two switches ("Toggle", "Busy") read as two ways to
// hide it, and a calendar meant to be hidden stayed on, dashed.

import { Seg } from "@/components/fr/controls"

export type Choice = "around" | "over" | "hidden"

export const CHOICES = [
  { value: "around", label: "Plan around it" },
  { value: "over", label: "Just show it" },
  { value: "hidden", label: "Hide" },
] as const

export function choiceOf(shown: boolean, busy: boolean): Choice {
  return !shown ? "hidden" : busy ? "around" : "over"
}

/** What a choice sets. Hidden is left out of planning too: what you can't see shouldn't move your work. */
export function fromChoice(choice: Choice): { shown: boolean; busy: boolean } {
  return { shown: choice !== "hidden", busy: choice === "around" }
}

export function saying(shown: boolean, busy: boolean): string {
  if (!shown) return busy ? "Hidden, but Friday still keeps work off its events" : "Hidden until you switch it on under Show"
  return busy ? "Shown; Friday keeps work off its events" : "Shown dashed; Friday may plan work over it"
}

export function CalendarChoice({ name, shown, busy, onPick }: { name: string; shown: boolean; busy: boolean; onPick: (change: { shown: boolean; busy: boolean }) => void }) {
  return <Seg options={CHOICES} value={choiceOf(shown, busy)} onPick={(c) => onPick(fromChoice(c))} label={`${name} on your calendar`} />
}
