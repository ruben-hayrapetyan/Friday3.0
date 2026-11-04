// Time you worked on a task without the timer (3 Nov: `log` had no button): which day, from when to when.

import { dayLabel } from "@/lib/format"
import { addDays } from "@/lib/time"

/** Today and the six days before it, newest first, said the way you'd say them. */
export function recentDays(today: string): { value: string; label: string }[] {
  return Array.from({ length: 7 }, (_, n) => {
    const day = addDays(today, -n)
    return { value: day, label: n === 0 ? "Today" : n === 1 ? "Yesterday" : dayLabel(day) }
  })
}

/** The hour before `now` ("HH:MM"), on the quarter hour: a guess at a sitting just ended, to put right. */
export function lastHour(now: string): { from: string; to: string } {
  const [h, m] = now.split(":").map(Number)
  const end = Math.floor((h * 60 + m) / 15) * 15
  const start = (end - 60 + 1440) % 1440
  const hhmm = (t: number) => `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`
  return { from: hhmm(start), to: hhmm(end) }
}
