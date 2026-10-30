// What setup's last card shows (Setup.tsx): your week building itself, and its numbers counting up. The questions'
// own pictures are the walk now (walk/World.ts).

import { type CSSProperties, useEffect, useState } from "react"
import type { Schemas } from "@/api/client"
import { type Bit, bedOf, VIEW, wakeOf, weekOf } from "../setupWeek"

type Answers = Schemas["SetupInput"]
const vars = (v: Record<string, string | number | undefined>) => v as CSSProperties

export function minutesOf(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number)
  return h * 60 + m
}

const DAYS = ["M", "T", "W", "T", "F", "S", "S"]

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

const KIND: Record<string, string> = { sleep: "var(--ob-night)", class: "var(--ob-class)", work: "var(--ob-work)", heavy: "var(--ob-work)", free: "var(--ob-free)", essay: "var(--ob-gold)", brief: "var(--ob-gold)", event: "var(--ob-lilac)" }

/** Your week, building itself: each day's blocks arriving in turn. */
export function WeekGrid({ a }: { a: Answers }) {
  const bits = weekOf(a, "ready").bits.filter((b) => b.kind !== "due")
  const pct = (t: number) => ((Math.min(Math.max(t, VIEW.from), VIEW.to) - VIEW.from) / (VIEW.to - VIEW.from)) * 100
  return (
    <div className="ob-week" aria-hidden>
      {DAYS.map((d, day) => (
        <div key={day} className="ob-week-day">
          <span>{d}</span>
          <div className="ob-week-col">
            {bits
              .filter((b: Bit) => b.day === day)
              .map((b, k) => (
                <i key={b.id} data-kind={b.kind} style={vars({ top: `${pct(b.start)}%`, height: `${Math.max(1.2, pct(b.end) - pct(b.start))}%`, "--c": KIND[b.kind], "--d": `${day * 110 + k * 45}ms` })} />
              ))}
          </div>
        </div>
      ))}
    </div>
  )
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
