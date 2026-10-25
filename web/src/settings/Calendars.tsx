// Your Google calendars (M12b), alphabetized: each one read or not, its events read per event or all as one kind,
// and trusted (straight to the plan) or through the Inbox. The list is what the last sync saw, folded under one line
// saying how many are read. The Mac's calendars (COMBINED.md 4), which the Mac app sends, list the same way.

import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { query } from "@/api/client"
import { Icon, Menu, Switch } from "@/components/fr/controls"
import { useCommand } from "@/hooks/useCommand"
import { when } from "@/lib/format"
import { useShell } from "@/shell/ShellContext"
import { usePresets } from "@/todo/AddBox"

export const useCalendars = () => useQuery({ queryKey: ["google_calendars"], queryFn: () => query("google_calendars") })
export const useMacCalendars = () => useQuery({ queryKey: ["mac_calendars"], queryFn: () => query("mac_calendars") })

const COLUMNS = "36px minmax(150px,1fr) 150px 72px 72px"

export function Calendars({ mac = false }: { mac?: boolean }) {
  const google = useCalendars().data
  const onMac = useMacCalendars().data
  const calendars = (mac ? onMac : google) ?? []
  const [open, setOpen] = useState(false)
  if (!calendars.length)
    return <span className="fr-kicker">{mac ? "The Mac app sends this Mac’s calendars once it runs and you allow it to read them." : "Your calendars list here after the first sync with Google connected."}</span>
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

function List({ calendars, mac }: { calendars: NonNullable<ReturnType<typeof useCalendars>["data"]>; mac: boolean }) {
  const { today } = useShell()
  const presets = usePresets()
  const save = useCommand("calendar_set", { label: (o) => o.result.message ?? "Saved" })
  const set = (change: { id: string; on?: boolean; kind?: string; trusted?: boolean; editable?: boolean }) => save({ ...change, mac })
  const kinds = [{ value: "auto", label: "Per event" }, ...presets.map((p) => ({ value: p, label: p }))]
  return (
    <>
      <div className="fr-kicker" style={{ display: "grid", gridTemplateColumns: COLUMNS, gap: 12, padding: "6px 0 4px" }}>
        <span />
        <span>Calendar</span>
        <span>Read events as</span>
        <span title="Its events go straight into the plan">Skip Inbox</span>
        <span title="Changes you make to its events in Friday are saved back to it">Edit here</span>
      </div>
      {calendars.map((c) => (
        <div key={c.id} className="fr-row" style={{ display: "grid", gridTemplateColumns: COLUMNS, gap: 12, alignItems: "center", padding: "8px 0" }}>
          <Switch on={c.on} onToggle={() => set({ id: c.id, on: !c.on })} label={`Read ${c.name}`} />
          <span style={{ display: "flex", flexDirection: "column", gap: 1, minWidth: 0, opacity: c.on ? 1 : 0.6 }}>
            <span title={c.name} style={{ fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {c.name}
              {c.primary && <span className="fr-kicker"> · primary</span>}
              {c.account && c.account !== c.name && <span className="fr-kicker"> · {c.account}</span>}
            </span>
            <span title={c.error ?? undefined} style={{ fontSize: 12, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", color: c.on && c.error ? "var(--fr-due)" : "var(--color-neutral-500)" }}>
              {!c.on ? (c.also_google ? "Not read: Friday reads it from Google" : "Not read") : (c.error ?? (c.last_sync ? `Read ${when(c.last_sync, today)}` : "Reading now"))}
            </span>
          </span>
          <Menu options={kinds} value={c.kind} onPick={(kind) => set({ id: c.id, kind })} label={`How ${c.name} is read`} disabled={!c.on} />
          <span style={{ opacity: c.on ? 1 : 0.4 }}>
            <Switch on={c.trusted} onToggle={() => c.on && set({ id: c.id, trusted: !c.trusted })} label={`${c.name} straight to the plan`} />
          </span>
          <span style={{ opacity: c.on && c.writable && !mac ? 1 : 0.4 }} title={mac ? "Friday doesn't change the Mac's calendars yet" : c.writable ? undefined : "Google doesn't let you change this calendar's events"}>
            <Switch on={!!c.editable} onToggle={() => c.on && c.writable && !mac && set({ id: c.id, editable: !c.editable })} label={`Save changes to ${c.name}`} />
          </span>
        </div>
      ))}
      <span className="fr-kicker" style={{ paddingTop: 8, textWrap: "pretty" }}>
        {mac
          ? "A calendar Friday also reads from Google, a subscription or birthdays starts off, so nothing comes in twice. Friday doesn’t change the Mac’s calendars yet. "
          : "“Edit here” saves what you change in Friday (title, times, notes, deleting) back to Google. "}
        “Per event” reads due dates, exams (with prep), classes and other commitments from each event’s title; a kind reads every event as that kind. Turning a calendar off withdraws what it suggested that you haven’t answered; what you accepted stays.
      </span>
    </>
  )
}
