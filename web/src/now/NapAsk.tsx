// Starting a nap while something is being timed asks whether to stop timing it (16 Nov: "when you are starting a nap,
// if you are still in the middle of recording a task, ask whether to stop that task or not"). Until then a nap stopped
// the timer itself, and only the one started last. Every Nap (the Now bar, its More, Search, Insights → Sleep) asks
// here: `ask` opens it, NapAsk (mounted once in the shell) shows it.

import { useSyncExternalStore } from "react"
import { Icon } from "@/components/fr/controls"
import { Modal } from "@/dialogs/Dialogs"

export interface Timed {
  item_id: number | null
  title?: string | null
}

interface Asking {
  timed: Timed[]
  answer: (stop: boolean | null) => void // null: no nap after all
}

let asking: Asking | null = null
const listeners = new Set<() => void>()
const tell = () => listeners.forEach((l) => l())

/** Ask about these, then `answer` with whether to stop timing them, or null when the nap is called off. */
export function ask(timed: Timed[], answer: (stop: boolean | null) => void): void {
  asking = { timed, answer }
  tell()
}

function close(): void {
  asking = null
  tell()
}

/** The things being timed, said as a list: "PS5", "PS5 and Laundry", "PS5, Laundry and Reading". */
export function named(timed: Timed[]): string {
  const titles = timed.map((t) => t.title || "a task")
  return titles.length < 2 ? (titles[0] ?? "") : `${titles.slice(0, -1).join(", ")} and ${titles.at(-1)}`
}

export function NapAsk() {
  const now = useSyncExternalStore(
    (l) => (listeners.add(l), () => listeners.delete(l)),
    () => asking,
  )
  if (!now) return null
  const pick = (stop: boolean | null) => (close(), now.answer(stop))
  const them = now.timed.length > 1 ? "them" : "it"
  return (
    <Modal onClose={() => pick(null)} width={420} label="Taking a nap">
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <span className="fr-h" style={{ fontSize: 20, display: "flex", gap: 8, alignItems: "center" }}>
          <Icon name="bed" size={18} />
          Taking a nap
        </span>
        <span style={{ color: "var(--color-neutral-300)", textWrap: "pretty" }}>
          You're timing {named(now.timed)}. Stop timing {them} while you nap?
        </span>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className="btn btn-primary" onClick={() => pick(true)} autoFocus>
            Stop timing and nap
          </button>
          <button className="btn btn-secondary" onClick={() => pick(false)} title={`Something that runs by itself: ${them === "it" ? "its timer goes" : "their timers go"} on while you sleep`}>
            Nap, keep timing
          </button>
          <button className="btn btn-ghost" onClick={() => pick(null)}>
            Cancel
          </button>
        </div>
      </div>
    </Modal>
  )
}
