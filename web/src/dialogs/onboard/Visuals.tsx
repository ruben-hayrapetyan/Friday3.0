// The pictures above setup's questions (29 Oct: "look at how opal the app on the app store does its intro and take
// inspiration but for friday"): each one is the answer, drawn and moving. The sky rises to your alarm and falls to
// your bedtime, the week's work stands as glass bars, a focus dial runs as long as your sittings, the essay's line
// shows the day you're done, the evening and the Saturday show the part that's yours. Friday's ring, in its colours,
// is the hero where Opal has its gem; your week builds itself at the end. Smooth, not pixel: CSS and SVG, eased, and
// flat (29 Oct: "i don't want gradients in the startup page").

import { type CSSProperties, useEffect, useState } from "react"
import type { Schemas } from "@/api/client"
import { ampm } from "@/lib/format"
import { type Bit, bedOf, VIEW, wakeOf, weekOf } from "../setupWeek"

type Answers = Schemas["SetupInput"]
const vars = (v: Record<string, string | number | undefined>) => v as CSSProperties

export function minutesOf(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number)
  return h * 60 + m
}

/** The sky's colour at a time of day (the first), and a second the older pictures used: night, dawn, morning, day,
 * late afternoon, dusk. */
export function skyColors(minutes: number): [string, string] {
  const h = (((minutes % 1440) + 1440) % 1440) / 60
  if (h < 5 || h >= 21.5) return ["#05060f", "#151a3a"]
  if (h < 6.5) return ["#1b1f4a", "#c0707e"]
  if (h < 8) return ["#4b6fc4", "#f6b48a"]
  if (h < 17) return ["#2f74d8", "#9fd0f6"]
  if (h < 19) return ["#3b4fa8", "#f2a36b"]
  return ["#141a44", "#8a4a7a"]
}

/** Where the sun (or moon) is over the horizon at a time: 0 left to 1 right, and how high, 0 to 1. */
export function sunAt(minutes: number): { x: number; up: number; night: boolean } {
  const h = (((minutes % 1440) + 1440) % 1440) / 60
  const day = h >= 5.5 && h < 20.5
  const share = day ? (h - 5.5) / 15 : (((h + 24 - 20.5) % 24) / 9)
  return { x: share, up: Math.sin(Math.min(1, Math.max(0, share)) * Math.PI), night: !day }
}

/** The sky at your alarm or your bedtime, the sun or moon where it'd be, stars at night. */
export function Sky({ minutes, caption }: { minutes: number; caption?: string }) {
  const [top, bottom] = skyColors(minutes)
  const sun = sunAt(minutes)
  return (
    <div className="ob-visual ob-sky" style={vars({ "--top": top, "--bottom": bottom })} aria-hidden>
      <div className="ob-stars" data-on={sun.night || undefined} />
      <div className="ob-sun" data-night={sun.night || undefined} style={vars({ "--x": sun.x, "--up": sun.up })} />
      <svg className="ob-hills" viewBox="0 0 400 80" preserveAspectRatio="none">
        <path d="M0 50 C 60 20, 110 40, 160 32 S 260 10, 320 30 S 380 44, 400 36 L 400 80 L 0 80 Z" />
        <path d="M0 64 C 80 44, 140 66, 220 52 S 340 46, 400 58 L 400 80 L 0 80 Z" />
      </svg>
      {caption && <span className="ob-caption">{caption}</span>}
    </div>
  )
}

const DAYS = ["M", "T", "W", "T", "F", "S", "S"]

/** A week's work as glass bars: a normal day's hours each weekday, half at weekends, and a heavy day on Thursday. */
export function WeekBars({ normal, most, heavy }: { normal: number; most: number; heavy: boolean }) {
  const top = 12
  return (
    <div className="ob-visual ob-bars" aria-hidden>
      {DAYS.map((d, i) => {
        const weekend = i >= 5
        const base = weekend ? normal / 2 : normal
        const extra = heavy && i === 3 ? Math.max(0, most - normal) : 0
        return (
          <div key={i} className="ob-bar" style={vars({ "--i": i })}>
            <div className="ob-bar-track">
              {extra > 0 && <div className="ob-bar-extra" style={vars({ "--h": Math.min(1, (base + extra) / top) })} />}
              <div className="ob-bar-fill" style={vars({ "--h": Math.min(1, base / top) })} />
            </div>
            <span>{d}</span>
          </div>
        )
      })}
      <span className="ob-caption">
        <b>{Math.round(normal * 5 + normal)}h</b> of work in a normal week{heavy && most > normal ? `, up to ${most}h on a heavy day` : ""}
      </span>
    </div>
  )
}

/** A focus dial: it fills over a sitting as long as yours (in seconds here), then a break, again. */
export function FocusDial({ hours }: { hours: number }) {
  const [phase, setPhase] = useState<"work" | "break">("work")
  const sitting = Math.max(1.6, hours * 1.4) // seconds the picture's sitting takes
  useEffect(() => {
    setPhase("work")
    let on = true
    let timer: ReturnType<typeof setTimeout>
    const loop = (p: "work" | "break") => {
      timer = setTimeout(() => on && (setPhase(p === "work" ? "break" : "work"), loop(p === "work" ? "break" : "work")), (p === "work" ? sitting : 1.4) * 1000)
    }
    loop("work")
    return () => ((on = false), clearTimeout(timer))
  }, [sitting])
  const label = hours < 1 ? `${Math.round(hours * 60)}m` : `${hours}h`
  return (
    <div className="ob-visual ob-focus" aria-hidden>
      <svg viewBox="0 0 120 120" className="ob-dial" data-phase={phase} style={vars({ "--secs": `${sitting}s` })}>
        <circle cx="60" cy="60" r="50" className="ob-dial-track" />
        <circle key={`${phase}${sitting}`} cx="60" cy="60" r="50" className="ob-dial-fill" pathLength={100} />
      </svg>
      <div className="ob-dial-text">
        <b>{phase === "work" ? label : "Break"}</b>
        <span>{phase === "work" ? "focused" : "a quarter hour"}</span>
      </div>
    </div>
  )
}

/** The week up to an essay due Friday at 5pm: the day you'd be done glows, the work before it filled in. */
export function DeadlineLine({ early }: { early: number }) {
  const done = Math.max(0, 4 - Math.max(0, Math.min(4, early)))
  return (
    <div className="ob-visual ob-deadline" aria-hidden>
      <div className="ob-line">
        <div className="ob-line-fill" style={vars({ "--to": done / 4 })} />
        {["Mon", "Tue", "Wed", "Thu", "Fri"].map((d, i) => (
          <div key={d} className="ob-stop" data-done={i === done || undefined} data-due={i === 4 || undefined} style={vars({ "--at": i / 4 })}>
            <i />
            <span>{d}</span>
          </div>
        ))}
        <div className="ob-flag" style={vars({ "--at": 1 })}>
          Due 5pm
        </div>
        <div className="ob-done" style={vars({ "--at": done / 4 })}>
          Done
        </div>
      </div>
      <span className="ob-caption">{early === 0 ? "Finished by the deadline itself" : `Finished ${early === 1 ? "a day" : `${early} days`} before it's due, with room to spare`}</span>
    </div>
  )
}

/** A day's hours on a line, the part that's yours glowing, and the time running along it. */
function Span({ from, to, free, label }: { from: number; to: number; free: [number, number] | null; label: string }) {
  const at = (m: number) => Math.max(0, Math.min(1, (m - from) / Math.max(1, to - from)))
  return (
    <div className="ob-span">
      <div className="ob-span-track">
        {free && <div className="ob-span-free" style={vars({ "--a": at(free[0]), "--b": at(free[1]) })} />}
        <div className="ob-span-now" />
      </div>
      <div className="ob-span-ends">
        <span>{ampm(clock(from))}</span>
        <span>{label}</span>
        <span>{ampm(clock(to))}</span>
      </div>
    </div>
  )
}

function clock(minutes: number): string {
  const m = ((Math.round(minutes) % 1440) + 1440) % 1440
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`
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

/** A weekday evening, five o'clock to bed, at dusk. */
export function Evening({ a }: { a: Answers }) {
  const free = freeSpan(a, false)
  const hours = free ? Math.round(((free[1] - free[0]) / 60) * 2) / 2 : 0
  return (
    <div className="ob-visual ob-evening" aria-hidden>
      <Span from={17 * 60} to={bedOf(a, 0)} free={free} label={free ? `${hours}h yours` : "work until bed"} />
      <span className="ob-caption">{free ? `From ${ampm(clock(free[0]))}, the evening is yours` : "No evening kept free: work may run until bed"}</span>
    </div>
  )
}

/** A Saturday, up to bed, the sun crossing it. */
export function Weekend({ a }: { a: Answers }) {
  const free = freeSpan(a, true)
  const hours = free ? Math.round(((free[1] - free[0]) / 60) * 2) / 2 : 0
  return (
    <div className="ob-visual ob-weekend" aria-hidden>
      <div className="ob-arc" />
      <Span from={wakeOf(a, 5)} to={bedOf(a, 5)} free={free} label={free ? `${hours}h yours` : "open for work"} />
      <span className="ob-caption">{a.weekend_free >= 13 ? "Weekends are all yours" : free ? `${hours} hours of each weekend day kept free` : "Weekends open for work"}</span>
    </div>
  )
}

/** The morning brief, as it opens: what's planned and what matters. */
export function BriefCard({ on }: { on: boolean }) {
  return (
    <div className="ob-visual ob-brief" data-off={!on || undefined} aria-hidden>
      <div className="ob-brief-card">
        <span className="ob-brief-day">Good morning · Tuesday</span>
        <b>4h of work today, done by 6pm</b>
        <span style={vars({ "--i": 1 })}>
          <i style={vars({ "--c": "var(--ob-class)" })} /> Math 1920 at 9am, then CS 2112
        </span>
        <span style={vars({ "--i": 2 })}>
          <i style={vars({ "--c": "var(--ob-work)" })} /> Psych WA8, due Thursday: 2 sittings
        </span>
        <span style={vars({ "--i": 3 })}>
          <i style={vars({ "--c": "var(--ob-free)" })} /> Your evening is free from 6pm
        </span>
      </div>
    </div>
  )
}

/** Friday's ring, its colours in flat segments, slowly turning: where Opal has its gem. */
export function Ring({ size = 160, fill = 1, glow = 1 }: { size?: number; fill?: number; glow?: number }) {
  return (
    <div className="ob-ring" style={vars({ "--size": `${size}px`, "--fill": fill, "--glow": glow })} aria-hidden>
      <div className="ob-ring-band" />
      <span className="ob-ring-f">F</span>
    </div>
  )
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
