// Your Google calendars (M12b), alphabetized: each one read or not, its events read per event or all as one kind,
// and trusted (straight to the plan) or through the Inbox. The list is what the last sync saw, folded under one line
// saying how many are read; with several Google accounts, each account's calendars come under its address. The Mac's
// calendars (COMBINED.md 4), which the Mac app sends, list the same way.

import { useQuery } from "@tanstack/react-query"
import { Fragment, useState } from "react"
import { query } from "@/api/client"
import { Icon, Menu, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { when } from "@/lib/format"
import { useShell } from "@/shell/ShellContext"
import { usePresets } from "@/todo/AddBox"
import { ACCOUNTS, PRIVACY } from "./MacAccounts"
import { accountName, offline, readable, useGoogleAccess } from "./GoogleConnect"

export const useCalendars = () => useQuery({ queryKey: ["google_calendars"], queryFn: () => query("google_calendars") })
export const useMacCalendars = () => useQuery({ queryKey: ["mac_calendars"], queryFn: () => query("mac_calendars") })

const COLUMNS = "36px minmax(150px,1fr) 150px 72px 72px"

export function Calendars({ mac = false }: { mac?: boolean }) {
  const google = useCalendars().data
  const onMac = useMacCalendars().data
  const calendars = (mac ? onMac : google) ?? []
  const [open, setOpen] = useState(false)
  if (!calendars.length)
    return (
      <span className="fr-kicker" style={{ textWrap: "pretty" }}>
        {mac ? (
          <>
            Friday's Mac app sends this Mac's calendars once it runs and you allow it to read them:{" "}
            <a className="fr-link" href={PRIVACY}>
              Privacy & Security → Calendars
            </a>
            . To bring in Google's, add your Google account to the Mac:{" "}
            <a className="fr-link" href={ACCOUNTS}>
              Internet Accounts
            </a>
            .
          </>
        ) : (
          "Google's calendars list here after the first sync with Google connected (Settings → Integrations → More). In the Mac app, Google's calendars can come in through the Mac instead, above."
        )}
      </span>
    )
  const reading = calendars.filter((c) => c.on)
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <button className="fr-plain fr-hover" onClick={() => setOpen(!open)} aria-expanded={open} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 10px", margin: "0 -10px", borderRadius: "var(--radius-md)", textAlign: "left" }}>
        <Icon name={open ? "caret-down" : "caret-right"} size={13} style={{ color: "var(--color-neutral-400)" }} />
        <span style={{ fontWeight: 500 }}>{mac ? "On this Mac" : "Calendars"}</span>
        <span className="fr-kicker" style={{ flex: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {reading.length} of {calendars.length} read{reading.length ? `: ${reading.map((c) => c.name).join(", ")}` : ""}
        </span>
      </button>
      {open && <List calendars={calendars} mac={mac} />}
    </div>
  )
}

type Listed = NonNullable<ReturnType<typeof useCalendars>["data"]>

/** Google's calendars by account, in the order the accounts were added, when there's more than one; else one group. */
function byAccount(calendars: Listed, order: string[]): [string | null, Listed][] {
  const accounts = [...new Set(calendars.map((c) => c.account ?? ""))]
  if (accounts.length < 2) return [[null, calendars]]
  const place = (a: string) => (order.includes(a) ? order.indexOf(a) : order.length)
  return accounts.sort((a, b) => place(a) - place(b)).map((a) => [a, calendars.filter((c) => (c.account ?? "") === a)])
}

function List({ calendars, mac }: { calendars: Listed; mac: boolean }) {
  const { today } = useShell()
  const presets = usePresets()
  const order = (useGoogleAccess()?.accounts ?? []).map((a) => a.email)
  const save = useCommand("calendar_set", { label: (o) => o.result.message ?? "Saved" })
  const set = (change: { id: string; on?: boolean; kind?: string; trusted?: boolean; editable?: boolean }) => save({ ...change, mac })
  const kinds = [{ value: "auto", label: "Per event" }, ...presets.map((p) => ({ value: p, label: p }))]
  const groups: [string | null, Listed][] = mac ? [[null, calendars]] : byAccount(calendars, order)
  return (
    <>
      <div className="fr-kicker" style={{ display: "grid", gridTemplateColumns: COLUMNS, gap: 12, padding: "6px 0 4px" }}>
        <span />
        <span>Calendar</span>
        <span>Read events as</span>
        <span title="Its events go straight into the plan">Skip Inbox</span>
        <span title="Changes you make to its events in Friday are saved back to it">Edit here</span>
      </div>
      {groups.map(([account, list]) => (
        <Fragment key={account ?? "all"}>
          {account !== null && (
            <span className="fr-kicker" style={{ padding: "12px 0 2px", fontWeight: 500, color: "var(--color-neutral-300)", overflowWrap: "anywhere" }}>
              {accountName(account)}
            </span>
          )}
          {list.map((c) => (
            <div key={c.id} className="fr-row" style={{ display: "grid", gridTemplateColumns: COLUMNS, gap: 12, alignItems: "center", padding: "8px 0" }}>
              <Switch on={c.on} onToggle={() => set({ id: c.id, on: !c.on })} label={`Read ${c.name}`} />
              <span style={{ display: "flex", flexDirection: "column", gap: 1, minWidth: 0, opacity: c.on ? 1 : 0.6 }}>
                <span title={c.name} style={{ fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {c.name}
                  {c.primary && <span className="fr-kicker"> · primary</span>}
                  {mac && c.account && c.account !== c.name && <span className="fr-kicker"> · {c.account}</span>}
                </span>
                <span title={c.error ?? undefined} style={{ fontSize: 12, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", color: c.on && c.error ? (offline(c.error) ? "var(--fr-warn)" : "var(--fr-due)") : "var(--color-neutral-500)" }}>
                  {!c.on ? (c.also_google ? "Not read: Friday reads it from Google" : "Not read") : (c.error ? readable(c.error) : (c.last_sync ? `Read ${when(c.last_sync, today)}` : "Reading now"))}
                </span>
              </span>
              <Menu options={kinds} value={c.kind} onPick={(kind) => set({ id: c.id, kind })} label={`How ${c.name} is read`} disabled={!c.on} />
              <span style={{ opacity: c.on ? 1 : 0.4 }}>
                <Switch on={c.trusted} onToggle={() => c.on && set({ id: c.id, trusted: !c.trusted })} label={`${c.name} straight to the plan`} />
              </span>
              <span style={{ opacity: c.on && c.writable ? 1 : 0.4 }} title={c.writable ? undefined : `${mac ? "The Mac" : "Google"} doesn't let you change this calendar's events`}>
                <Switch on={!!c.editable} onToggle={() => c.on && c.writable && set({ id: c.id, editable: !c.editable })} label={`Save changes to ${c.name}`} />
              </span>
            </div>
          ))}
        </Fragment>
      ))}
      <span className="fr-kicker" style={{ paddingTop: 8, textWrap: "pretty" }}>
        {mac
          ? "A calendar Friday also reads from Google, a subscription or birthdays starts off, so nothing comes in twice. “Edit here” saves what you change in Friday (times, a new title, deleting) back to the calendar on your Mac, which passes it on to Google or iCloud; your notes stay in Friday. "
          : "“Edit here” saves what you change in Friday (times, a new title, deleting) back to Google; your notes stay in Friday. "}
        “Per event” reads due dates, exams (with prep), classes and other commitments from each event’s title; a kind reads every event as that kind. Turning a calendar off withdraws what it suggested that you haven’t answered; what you accepted stays.
      </span>
    </>
  )
}
