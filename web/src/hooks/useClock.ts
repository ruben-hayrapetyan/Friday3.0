// The Now bar and now line tick on the client (DESIGN §18.2). The clock follows the server's local time, which
// the calendar query reports, so a browser in another zone (or a test server's clock) still agrees with the plan.

import { useEffect, useMemo, useState } from "react"
import { fromMin, toMin } from "@/lib/time"

let offsetMin = 0

function browserMin(): number {
  const d = new Date()
  return Math.floor(d.getTime() / 60000) - d.getTimezoneOffset()
}

export function followServer(serverNow: string): void {
  offsetMin = toMin(serverNow) - browserMin()
}

export function nowMin(): number {
  return browserMin() + offsetMin
}

export function useClock(): number {
  const [now, setNow] = useState(nowMin)
  useEffect(() => {
    const timer = setInterval(() => setNow(nowMin()), 15_000)
    return () => clearInterval(timer)
  }, [])
  return now
}

/** The calendar's date now, turning at midnight (15 Nov: "Split at midnight"): today's column, the now line, the
 * agenda's Today and the mini month's mark follow it. Planning still counts by your planning day (`useShell().today`),
 * which runs on to your day start. */
export function useDate(): string {
  return fromMin(useClock()).slice(0, 10)
}

/** Seconds on a running timer, ticking once a second. `elapsed` is as of its fetch, so every fetch rebases it. */
export function useElapsed(elapsed: number | null | undefined): number {
  const [, tick] = useState(0)
  const base = useMemo(() => ({ at: Date.now(), elapsed: elapsed ?? 0 }), [elapsed])
  useEffect(() => {
    if (elapsed == null) return
    const id = setInterval(() => tick((n) => n + 1), 1000)
    return () => clearInterval(id)
  }, [elapsed])
  return elapsed == null ? 0 : base.elapsed + (Date.now() - base.at) / 1000
}
