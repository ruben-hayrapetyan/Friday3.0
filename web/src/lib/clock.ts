// Your clock (settings `clock`, Settings → Appearance → Clock): every time Friday shows is on it, 12-hour unless you
// chose 24-hour. The server keeps it, so its own sentences, the command line and Siri follow it too; Root sets it
// here each render from your settings (useClock in App.tsx), so the pure helpers that write times (lib/time.ts
// clockTime) follow it without each asking. The last one seen is kept on this device, so a 24-hour Friday doesn't
// open on 12-hour times while its settings load.

export type Clock = "12h" | "24h"

const KEY = "friday-clock"
let current: Clock = remembered()

function remembered(): Clock {
  try {
    return typeof window !== "undefined" && window.localStorage.getItem(KEY) === "24h" ? "24h" : "12h"
  } catch {
    return "12h"
  }
}

/** The clock in effect. */
export const clockSetting = (): Clock => current

/** Your settings' clock; anything else (settings not loaded yet) leaves the one in effect. */
export function setClock(clock: unknown): void {
  if (clock !== "12h" && clock !== "24h") return
  if (clock === current) return
  current = clock
  try {
    window.localStorage.setItem(KEY, clock)
  } catch {
    // private mode: it lasts this visit
  }
}
