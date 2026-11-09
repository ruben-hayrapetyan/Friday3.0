// The calendars on this Mac (COMBINED.md 4): Friday's Mac app sends every calendar the Mac's Calendar app has, Google's
// too once its account is added in System Settings. Setup's "Bring in" step and Settings → Integrations show them.

import type { Schemas } from "@/api/client"
import { Icon } from "@/components/fr/controls"

/** Whether this is the Mac app's window (it names itself in its user agent), where the Mac's calendars come in. */
export const inMacApp = () => typeof navigator !== "undefined" && navigator.userAgent.includes("FridayMac")

// System Settings, from the Mac app's window: Internet Accounts, where Google is added; Calendars' privacy pane.
export const ACCOUNTS = "x-apple.systempreferences:com.apple.Internet-Accounts-Settings.extension"
export const PRIVACY = "x-apple.systempreferences:com.apple.preference.security?Privacy_Calendars"

type MacCalendar = Schemas["GoogleCalendarOut"]

/** The Mac's calendars by account ("iCloud", an address), each account's names in order. */
export function byAccount(calendars: MacCalendar[]): [string, MacCalendar[]][] {
  const out = new Map<string, MacCalendar[]>()
  for (const c of calendars) out.set(c.account || "On this Mac", [...(out.get(c.account || "On this Mac") ?? []), c])
  return [...out].sort(([, x], [, y]) => Number(!x.some((c) => c.on)) - Number(!y.some((c) => c.on))) // all left off: last
}

/** The Mac's calendars Friday reads, by account; the ones it leaves off (birthdays, subscriptions) said as a count. */
export function Accounts({ calendars }: { calendars: MacCalendar[] }) {
  return (
    <div className="st-accounts">
      {byAccount(calendars).map(([account, list]) => {
        const on = list.filter((c) => c.on)
        const off = list.filter((c) => !c.on)
        return (
          <div key={account} className="st-account">
            <Icon name={/@gmail\.com$|google/i.test(account) ? "google-logo" : /icloud/i.test(account) ? "cloud" : "calendar-blank"} size={15} />
            <span>
              <b>{account}</b> {on.map((c) => c.name).join(", ")}
              {off.length > 0 && (
                <span className="st-source-note">
                  {on.length ? " · " : ""}
                  {off.map((c) => c.name).join(", ")} left off
                </span>
              )}
            </span>
          </div>
        )
      })}
    </div>
  )
}

