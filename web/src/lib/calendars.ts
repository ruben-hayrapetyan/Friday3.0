// The calendars a new event can be saved to (27 Oct: "i want new events to go to you@gmail.com"):
// Google's, through your accounts, and the Mac's, through the Mac app. A calendar on both is offered once, the way
// Friday reads it: your Gmail calendar comes in through the Mac, so a new event goes there through the Mac, and the
// Mac's own sync doesn't bring it back as a second one.

export interface Listed {
  id: string
  name: string
  writable?: boolean
  on: boolean // Friday reads it
  account?: string | null
  color?: string | null
}

export interface Target {
  id: string
  name: string
  via: "google" | "mac"
  account: string | null
  color: string | null
}

/** "Family (Google)", as Friday names one of two Mac calendars called Family, is the calendar "Family". */
const bare = (name: string) => name.replace(/\s*\((?:Google|iCloud|Exchange|On My Mac|Other|CalDAV|Local)\)\s*\d*$/i, "").trim().toLowerCase()

export function newEventTargets(google: Listed[], mac: Listed[]): Target[] {
  const chosen = new Map<string, Target & { on: boolean }>()
  const consider = (c: Listed, via: Target["via"]) => {
    if (!c.writable) return
    const key = bare(c.name)
    const had = chosen.get(key)
    // The one Friday reads wins; with neither read, Google's, which needs no Mac app.
    if (had && (had.on || !c.on)) return
    chosen.set(key, { id: c.id, name: c.name, via, account: c.account ?? null, color: c.color ?? null, on: c.on })
  }
  google.forEach((c) => consider(c, "google"))
  mac.forEach((c) => consider(c, "mac"))
  return [...chosen.values()].map(({ on: _, ...t }) => t)
}

/** The paint of the first category whose pattern finds an event's title, as the server reads it (core/calendars.py
 * `category_of`: in order, without regard to case), so an event just made wears it before the server answers. */
export function categoryPaint(title: string, categories: { color: string; pattern: string }[]): string | null {
  for (const c of categories) {
    try {
      if (c.pattern.trim() && new RegExp(c.pattern, "i").test(title)) return c.color
    } catch {
      // A pattern JavaScript reads differently from Python: the server's answer says.
    }
  }
  return null
}
