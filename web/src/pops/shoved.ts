// The time just shoved, for a few seconds: the calendar brings it into view and makes it glow, so you see where your
// time went back (a toast in the corner was all there was).

import { useSyncExternalStore } from "react"

const FOR_MS = 4500

let fresh: ReadonlySet<number> = new Set()
const listeners = new Set<() => void>()

function emit() {
  for (const listener of listeners) listener()
}

export function markShoved(created: readonly number[]) {
  const mine = new Set(created)
  fresh = mine
  emit()
  setTimeout(() => {
    if (fresh !== mine) return // a newer shove owns the glow now
    fresh = new Set()
    emit()
  }, FOR_MS)
}

export function isJustShoved(id: number): boolean {
  return fresh.has(id)
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function useJustShoved(id: number): boolean {
  return useSyncExternalStore(subscribe, () => fresh.has(id))
}
