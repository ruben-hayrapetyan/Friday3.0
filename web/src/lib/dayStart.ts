// When the planning day starts (settings time.day_start): anything before it belongs to the night before, as the
// server counts days. Root sets it each render from your settings (useDayStart), so the pure helpers that place
// things by day (fitAxis, when, the rules lab's shapeOf) follow it without each asking; 4am until settings load.

const DEFAULT = 4 * 60
let current = DEFAULT

/** "06:30" as 390; anything unreadable as the default, 4am. */
export function minutesOf(clock: string | null | undefined): number {
  const m = /^(\d{1,2}):(\d{2})$/.exec(clock ?? "")
  if (!m) return DEFAULT
  const minutes = Number(m[1]) * 60 + Number(m[2])
  return minutes < 24 * 60 ? minutes : DEFAULT
}

/** The day start, in minutes after midnight. */
export const dayStartMin = (): number => current

/** The day start as a clock, "04:00". */
export function dayStartClock(): string {
  return `${String(Math.floor(current / 60)).padStart(2, "0")}:${String(current % 60).padStart(2, "0")}`
}

export function setDayStart(clock: string | null | undefined): void {
  current = minutesOf(clock)
}
