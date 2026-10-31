// What setup's last card counts with (Setup.tsx): the time kept yours, and numbers counting up. The questions' own
// pictures are the walk now (walk/World.ts).

import { useEffect, useState } from "react"
import type { Schemas } from "@/api/client"
import { bedOf, wakeOf } from "../setupWeek"

type Answers = Schemas["SetupInput"]

export function minutesOf(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number)
  return h * 60 + m
}

/** Which part of a weekday evening (or a weekend day) is yours, in minutes from midnight; null when none. */
export function freeSpan(a: Answers, weekend: boolean): [number, number] | null {
  const day = weekend ? 5 : 0
  const bed = bedOf(a, day)
  if (weekend) {
    if (a.weekend_free <= 0) return null
    if (a.weekend_free >= 13) return [wakeOf(a, day), bed]
    return [Math.max(wakeOf(a, day), bed - a.weekend_free * 60), bed]
  }
  if (a.evening_free <= 0) return null
  const from = minutesOf(a.evening_from)
  return [from, a.evening_free >= 5 ? bed : Math.min(bed, from + a.evening_free * 60)]
}

/** A number counting up to `to` when it appears. */
export function Count({ to, ms = 1100, suffix = "" }: { to: number; ms?: number; suffix?: string }) {
  const [now, setNow] = useState(0)
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return setNow(to)
    const start = performance.now()
    let raf = 0
    const tick = (t: number) => {
      const s = Math.min(1, (t - start) / ms)
      setNow(to * (1 - Math.pow(1 - s, 3)))
      if (s < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [to, ms])
  return (
    <>
      {Number.isInteger(to) ? Math.round(now) : Math.round(now * 2) / 2}
      {suffix}
    </>
  )
}
