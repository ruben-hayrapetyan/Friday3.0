// Whether the last query was answered from the service worker's copy because fridayd couldn't be reached.

import { useSyncExternalStore } from "react"

const HEADER = "x-friday-offline" // set by sw.ts
let offline = false
const listeners = new Set<() => void>()

export function noteResponse(response: Response): void {
  const now = response.headers.get(HEADER) === "1"
  if (now === offline) return
  offline = now
  for (const listener of listeners) listener()
}

export function useOffline(): boolean {
  return useSyncExternalStore(
    (changed) => {
      listeners.add(changed)
      return () => listeners.delete(changed)
    },
    () => offline,
  )
}
